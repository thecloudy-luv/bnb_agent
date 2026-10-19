"""A2A protocol JSON-RPC handler implementing ERC-8183 skills."""

from decimal import Decimal
import logging
import os
from typing import Any
from bnbagent.config import resolve_network
from bnbagent.erc8183 import ERC8183Client, NegotiationHandler
from bnbagent.utils import RateLimitExceeded, SlidingWindowLimiter
from bnbagent.wallets import EVMWalletProvider
from agent.config import load_settings
from agent.profile import PRICE_U

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

    task_description = data.get("task_description", "")
    terms = data.get("terms")
    if not isinstance(terms, dict):
        return jsonrpc_error(req_id, -32602, "Invalid params: 'terms' must be an object")

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
    )

    result = handler.negotiate({
        "task_description": task_description,
        "terms": terms,
    })

    envelope = result.to_dict()
    envelope["provider_address"] = wallet.address

    response_payload = {
        "message": {
            "role": "agent",
            "parts": [
                {
                    "kind": "data",
                    "data": envelope,
                }
            ],
        },
        **envelope,
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

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "result": {
            "message": {
                "role": "agent",
                "parts": [
                    {
                        "kind": "data",
                        "data": job_snapshot,
                    }
                ],
            },
            "job": job_snapshot,
        },
    }


def process_a2a_request(payload: Any, client_ip: str) -> dict[str, Any]:
    """Process an incoming A2A JSON-RPC 2.0 request."""
    if not isinstance(payload, dict):
        return jsonrpc_error(None, -32700, "Parse error: request body must be a JSON object")

    req_id = payload.get("id")
    if payload.get("jsonrpc") != "2.0":
        return jsonrpc_error(req_id, -32600, "Invalid Request: jsonrpc must be '2.0'")

    method = payload.get("method")
    if method != "message/send":
        return jsonrpc_error(req_id, -32601, f"Method not found: '{method}'")

    params = payload.get("params")
    if not isinstance(params, dict):
        return jsonrpc_error(req_id, -32602, "Invalid params: params must be an object")

    # Extract data from A2A message parts or direct params
    data: dict[str, Any] = {}
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
    if not skill:
        if "job_id" in data or "jobId" in data:
            skill = "erc8183-job-status"
        elif "task_description" in data or "terms" in data:
            skill = "negotiate-erc8183-job"
        else:
            return jsonrpc_error(req_id, -32602, "Invalid params: unrecognized skill or payload")

    if skill == "negotiate-erc8183-job":
        return handle_negotiate(req_id, data, client_ip)
    elif skill == "erc8183-job-status":
        return handle_job_status(req_id, data)
    else:
        return jsonrpc_error(req_id, -32602, f"Invalid params: unsupported skill '{skill}'")
