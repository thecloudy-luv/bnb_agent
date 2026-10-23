"""A2A protocol JSON-RPC handler implementing ERC-8183 skills."""

from decimal import Decimal
import logging
import os
import time
from typing import Any
import uuid
from bnbagent.config import resolve_network
from bnbagent.erc8183 import ERC8183Client, NegotiationHandler
from bnbagent.utils import RateLimitExceeded, SlidingWindowLimiter
from bnbagent.wallets import EVMWalletProvider
from agent.addresses import CAMPAIGN_WALLET
from agent.chain import get_pair_reserves, get_wallet_balances, get_web3
from agent.config import load_settings
from agent.market import fetch_bnb_closes
from agent.profile import PRICE_U
from agent.strategy import current_weight, momentum_24h, pool_price, target_weight

logger = logging.getLogger(__name__)

# Canonical BSC Testnet (chain 97) addresses
COMMERCE_ADDRESS = "0xa206c0517b6371c6638cd9e4a42cc9f02a33b0de"
PAYMENT_TOKEN_ADDRESS = "0xc70B8741B8B07A6d61E54fd4B20f22Fa648E5565"

# Rate limiters for negotiate requests
_rate_limit = int(os.getenv("ERC8183_NEGOTIATE_RATE_LIMIT", "10"))
_global_limit = int(os.getenv("ERC8183_NEGOTIATE_GLOBAL_RATE_LIMIT", "100"))
_rate_window = float(os.getenv("ERC8183_NEGOTIATE_RATE_WINDOW", "60.0"))

ip_limiter = SlidingWindowLimiter(max_requests=_rate_limit, window_seconds=_rate_window)
global_limiter = SlidingWindowLimiter(max_requests=_global_limit, window_seconds=_rate_window)


def jsonrpc_error(req_id: Any, code: int, message: str, data: Any = None) -> dict[str, Any]:
    """Build a standard JSON-RPC 2.0 error response."""
    error_obj: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error_obj["data"] = data
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": error_obj,
    }


def make_a2a_message(data: dict[str, Any]) -> dict[str, Any]:
    """A2A Message envelope with a single data part per A2A protocol spec."""
    return {
        "kind": "message",
        "role": "agent",
        "messageId": str(uuid.uuid4()),
        "parts": [{"kind": "data", "data": data}],
    }


def handle_negotiate(req_id: Any, data: dict[str, Any], client_ip: str) -> dict[str, Any]:
    """Handle negotiate-erc8183-job skill."""
    cfg = load_settings()

    if not cfg.private_key:
        return jsonrpc_error(req_id, -32603, "provider key not configured")

    try:
        global_limiter.check("global")
        ip_limiter.check(client_ip)
    except RateLimitExceeded:
        return jsonrpc_error(req_id, -32000, "Rate limit exceeded")

    task_description = (
        data.get("task_description")
        or data.get("task")
        or data.get("prompt")
        or "Autonomous portfolio rebalancing review"
    )
    raw_terms = data.get("terms")
    terms: dict[str, Any] = dict(raw_terms) if isinstance(raw_terms, dict) else {}
    terms.setdefault("deliverables", "JSON analysis report")
    terms.setdefault(
        "quality_standards",
        "Read-only analysis only. Execute no transaction and move no funds.",
    )
    # Do not mutate terms if client supplied clean terms (to preserve client request_hash)
    if "price" in terms and not (isinstance(terms["price"], str) and terms["price"].isdigit()):
        terms.pop("price", None)

    # Calculate atomic price in token U units (18 decimals)
    atomic_price = str(int(Decimal(PRICE_U) * (10**18)))

    wallet = EVMWalletProvider(
        password="a2a-wallet-password",
        private_key=cfg.private_key,
        persist=False,
    )

    handler = NegotiationHandler(
        service_price=atomic_price,
        currency=PAYMENT_TOKEN_ADDRESS,
        wallet_provider=wallet,
        chain_id=cfg.chain_id,
        verifying_contract=COMMERCE_ADDRESS,
        require_quality_standards=False,
    )

    result = handler.negotiate({
        "task_description": task_description,
        "terms": terms,
    })

    envelope = result.to_dict()
    envelope["provider_address"] = wallet.address
    resp_obj = envelope.get("response", {})
    resp_terms = resp_obj.get("terms", {})

    now_ts = int(time.time())
    negotiated_at = resp_obj.get("negotiated_at") or now_ts

    # Populate all field variants expected by Pokter and other marketplaces
    envelope["negotiated_at"] = negotiated_at
    envelope["price"] = resp_terms.get("price", atomic_price)
    envelope["currency"] = resp_terms.get("currency", PAYMENT_TOKEN_ADDRESS)
    envelope["accepted"] = True
    envelope["terms"] = resp_terms

    resp_obj["accepted"] = True
    resp_obj["negotiated_at"] = negotiated_at
    resp_obj["price"] = resp_terms.get("price", atomic_price)
    resp_obj["currency"] = resp_terms.get("currency", PAYMENT_TOKEN_ADDRESS)
    resp_obj["negotiation_hash"] = envelope.get("negotiation_hash", "")
    resp_obj["provider_sig"] = envelope.get("provider_sig", "")
    resp_terms["price"] = resp_terms.get("price", atomic_price)
    resp_terms["currency"] = resp_terms.get("currency", PAYMENT_TOKEN_ADDRESS)

    message_envelope = make_a2a_message(envelope)

    # Hybrid payload: strictly conforms to A2A spec (result has kind, role, messageId, parts),
    # while merging top-level envelope fields and result.message for any legacy/alternative parser.
    response_payload = {
        **message_envelope,
        **envelope,
        "message": message_envelope,
    }

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "result": response_payload,
    }


def handle_job_status(req_id: Any, data: dict[str, Any]) -> dict[str, Any]:
    """Handle erc8183-job-status skill."""
    job_id = data.get("job_id")
    if job_id is None:
        job_id = data.get("jobId")
    if job_id is None:
        return jsonrpc_error(req_id, -32602, "Invalid params: 'job_id' is required")

    try:
        int_job_id = int(job_id)
    except (ValueError, TypeError):
        return jsonrpc_error(req_id, -32602, "Invalid params: 'job_id' must be an integer")

    cfg = load_settings()
    from dataclasses import replace

    network = replace(resolve_network("bsc-testnet"), rpc_url=cfg.rpc_url)
    client = ERC8183Client(wallet_provider=None, network=network)

    try:
        job = client.get_job(int_job_id)
    except Exception as exc:
        return jsonrpc_error(req_id, -32603, f"Failed to fetch job: {exc}")

    deliverable_hex = (
        "0x" + job.deliverable.hex() if isinstance(job.deliverable, bytes) else str(job.deliverable)
    )
    job_snapshot = {
        "id": job.id,
        "client": job.client,
        "provider": job.provider,
        "evaluator": job.evaluator,
        "description": job.description,
        "budget": str(job.budget),
        "expired_at": job.expired_at,
        "status": int(job.status),
        "status_name": job.status.name,
        "hook": job.hook,
        "deliverable": deliverable_hex,
        "submitted_at": job.submitted_at,
    }

    message_envelope = make_a2a_message(job_snapshot)
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "result": {
            **message_envelope,
            "job": job_snapshot,
            "message": message_envelope,
        },
    }


def handle_rebalance_analysis(req_id: Any, data: dict[str, Any]) -> dict[str, Any]:
    """Handle rebalance-analysis skill (read-only portfolio review)."""
    cfg = load_settings()

    # 1. Obtain market momentum
    try:
        closes = fetch_bnb_closes(hours=25)
        momentum = momentum_24h(closes)
    except Exception as exc:
        logger.warning("Could not fetch BNB closes for analysis (%s); using 0.0", exc)
        momentum = 0.0

    target = target_weight(momentum)

    # 2. Determine portfolio weights
    bnb_weight_input = data.get("bnb_weight")
    wbnb_input = data.get("wbnb")
    busd_input = data.get("busd")

    w3 = get_web3(cfg.rpc_url)
    reserves = get_pair_reserves(w3)
    price = pool_price(reserves["reserve_wbnb"], reserves["reserve_busd"])

    if bnb_weight_input is not None:
        current = float(bnb_weight_input)
    elif wbnb_input is not None and busd_input is not None:
        current = current_weight(float(wbnb_input), float(busd_input), price)
    else:
        # Default: evaluate agent's own portfolio on BSC Testnet
        balances = get_wallet_balances(w3, CAMPAIGN_WALLET)
        current = current_weight(balances["wbnb"], balances["busd"], price)

    drift = current - target

    if abs(drift) >= 0.03:
        if drift > 0:
            rec_action = "sell_wbnb"
            rec_reason = (
                f"BNB allocation ({current:.1%}) is {abs(drift):.1%} above target ({target:.1%}). "
                "Recommend rebalancing by selling WBNB into BUSD."
            )
        else:
            rec_action = "buy_wbnb"
            rec_reason = (
                f"BNB allocation ({current:.1%}) is {abs(drift):.1%} below target ({target:.1%}). "
                "Recommend rebalancing by selling BUSD into WBNB."
            )
    else:
        rec_action = "none"
        rec_reason = (
            f"BNB allocation ({current:.1%}) is within tolerance band of target ({target:.1%}). "
            "No rebalancing action required."
        )

    explanation = (
        f"Binance 24h BNB momentum is {momentum:+.2%}. TiltBalance calculates a target weight "
        f"of {target:.1%} BNB. Current portfolio weight is {current:.1%} (drift {drift:+.2%})."
    )

    analysis_result = {
        "momentum_24h": round(momentum, 6),
        "target_bnb_weight": round(target, 4),
        "current_bnb_weight": round(current, 4),
        "drift": round(drift, 4),
        "pool_price_busd": round(price, 4),
        "recommended_action": rec_action,
        "reason": rec_reason,
        "explanation": explanation,
    }

    message_envelope = make_a2a_message(analysis_result)
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "result": {
            **message_envelope,
            "analysis": analysis_result,
            "message": message_envelope,
        },
    }


def handle_notify_funded(req_id: Any, data: dict[str, Any]) -> dict[str, Any]:
    """Handle notify_funded skill from Pokter/marketplaces."""
    job_id = data.get("job_id") or data.get("jobId")
    logger.info("Received notify_funded for job_id=%s: %s", job_id, data)

    cfg = load_settings()
    if cfg.run_loops and cfg.private_key and job_id:
        try:
            import threading
            from dataclasses import replace
            from bnbagent.config import resolve_network
            from bnbagent.erc8183 import ERC8183Client
            from agent.jobs import process_funded_job

            def _background_deliver(jid: int) -> None:
                try:
                    net = replace(resolve_network("bsc-testnet"), rpc_url=cfg.rpc_url, use_paymaster=False)
                    client = ERC8183Client(wallet_provider=None, network=net)
                    job = client.get_job(jid)
                    process_funded_job(job, client, cfg, dry_run=False)
                except Exception as exc:
                    logger.warning("Background delivery error on notify_funded job %s: %s", jid, exc)

            threading.Thread(target=_background_deliver, args=(int(job_id),), daemon=True).start()
        except Exception as exc:
            logger.warning("Could not launch background thread for notify_funded: %s", exc)

    notify_data = {"status": "accepted", "job_id": job_id}
    message_envelope = make_a2a_message(notify_data)
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "result": {
            **message_envelope,
            **notify_data,
            "message": message_envelope,
        },
    }


def process_a2a_request(payload: Any, client_ip: str) -> dict[str, Any]:
    """Process an incoming A2A JSON-RPC 2.0 request."""
    if not isinstance(payload, dict):
        return jsonrpc_error(None, -32700, "Parse error: request body must be a JSON object")

    req_id = payload.get("id")
    if payload.get("jsonrpc") != "2.0":
        return jsonrpc_error(req_id, -32600, "Invalid Request: jsonrpc must be '2.0'")

    method = payload.get("method", "message/send")
    if method not in ("message/send", "message", "negotiate", "quote", "notify_funded", "notify-funded"):
        return jsonrpc_error(req_id, -32601, f"Method not found: '{method}'")

    params = payload.get("params")
    if not isinstance(params, dict):
        return jsonrpc_error(req_id, -32602, "Invalid params: params must be an object")

    # Extract data from A2A message parts or direct params
    data: dict[str, Any] = {}
    if isinstance(params.get("data"), dict):
        data.update(params["data"])

    msg = params.get("message")
    if isinstance(msg, dict):
        parts = msg.get("parts")
        if isinstance(parts, list):
            for part in parts:
                if isinstance(part, dict) and "data" in part and isinstance(part["data"], dict):
                    data.update(part["data"])
        for k, v in msg.items():
            if k != "parts":
                data.setdefault(k, v)

    for k, v in params.items():
        if k != "message":
            data.setdefault(k, v)

    skill = data.get("skill")
    if method in ("negotiate", "quote"):
        skill = "negotiate-erc8183-job"
    elif method in ("notify_funded", "notify-funded"):
        skill = "notify_funded"

    if not skill:
        if "job_id" in data or "jobId" in data:
            if "status" in str(data).lower():
                skill = "erc8183-job-status"
            else:
                skill = "notify_funded"
        elif "bnb_weight" in data or ("wbnb" in data and "busd" in data):
            skill = "rebalance-analysis"
        elif "task_description" in data or "terms" in data or "task" in data or "prompt" in data:
            skill = "negotiate-erc8183-job"
        else:
            # Default to negotiate for unknown probe payloads so marketplace checks succeed
            skill = "negotiate-erc8183-job"

    skill_str = str(skill).lower()
    if (
        skill in ("negotiate-erc8183-job", "Quote Portfolio Rebalance Analysis", "negotiate", "quote")
        or "quote" in skill_str
        or "negotiat" in skill_str
    ):
        return handle_negotiate(req_id, data, client_ip)
    elif skill in ("notify_funded", "notify-funded") or "notify" in skill_str:
        return handle_notify_funded(req_id, data)
    elif skill == "erc8183-job-status" or "status" in skill_str:
        return handle_job_status(req_id, data)
    elif skill == "rebalance-analysis" or "rebalance" in skill_str:
        return handle_rebalance_analysis(req_id, data)
    else:
        return handle_negotiate(req_id, data, client_ip)
