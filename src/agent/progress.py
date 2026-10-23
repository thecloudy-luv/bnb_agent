"""Progress tracking module for campaign criteria and on-chain verification."""

from datetime import datetime, timezone
import logging
import time
from typing import Any
from web3 import Web3

from agent.addresses import CAMPAIGN_WALLET, PAIR_WBNB_BUSD, PANCAKESWAP_V2_ROUTER
from agent.chain import get_web3
from agent.config import Settings, load_settings
from agent.jobs import get_tracked_jobs
from agent.loop import get_recent_logs

logger = logging.getLogger(__name__)

# Minimal ABI for Pair Swap events
PAIR_SWAP_ABI = [
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "sender", "type": "address"},
            {"indexed": False, "name": "amount0In", "type": "uint256"},
            {"indexed": False, "name": "amount1In", "type": "uint256"},
            {"indexed": False, "name": "amount0Out", "type": "uint256"},
            {"indexed": False, "name": "amount1Out", "type": "uint256"},
            {"indexed": True, "name": "to", "type": "address"},
        ],
        "name": "Swap",
        "type": "event",
    }
]

# Cache for on-chain progress
_PROGRESS_CACHE: dict[str, Any] | None = None
_PROGRESS_CACHE_TIME: float = 0.0
_CACHE_TTL_SEC: float = 15.0


def count_campaign_metrics(
    swaps: list[dict[str, Any]],
    completed_jobs: list[dict[str, Any]],
    excluded_clients: tuple[str, ...] | list[str],
    our_wallet: str,
) -> dict[str, Any]:
    """Pure counting logic evaluating BNB Chain Set & Earn campaign goals.

    Criteria:
    1. Independent hires: >= 3 COMPLETED jobs from distinct wallets (excluding self and excluded_clients).
    2. Qualifying DEX swaps: >= 5 swaps.
    3. Distinct days: >= 3 distinct UTC days with swaps.
    """
    excluded_set = {addr.lower() for addr in excluded_clients}
    our_wallet_lower = our_wallet.lower()

    qualifying_clients: set[str] = set()
    total_earned_wei = 0
    valid_completed_jobs: list[dict[str, Any]] = []

    for job in completed_jobs:
        status_str = str(job.get("status", "")).upper()
        if status_str not in ("COMPLETED", "3", "JOBSTATUS.COMPLETED"):
            continue

        client_raw = job.get("client", "")
        if not client_raw:
            continue
        client_addr = client_raw.lower()

        # Exclude our own wallet and excluded checker addresses
        if client_addr == our_wallet_lower:
            continue
        if client_addr in excluded_set:
            continue

        qualifying_clients.add(client_addr)
        budget = int(job.get("budget", 0))
        total_earned_wei += budget
        valid_completed_jobs.append(job)

    # Analyze swaps
    distinct_utc_days: set[str] = set()
    formatted_swaps: list[dict[str, Any]] = []

    for s in swaps:
        ts = s.get("timestamp")
        day_str = s.get("utc_day")

        if not day_str:
            if isinstance(ts, (int, float)):
                day_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
            elif isinstance(ts, str):
                try:
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    day_str = dt.astimezone(timezone.utc).strftime("%Y-%m-%d")
                except Exception:
                    day_str = None

        if day_str:
            distinct_utc_days.add(day_str)

        tx = s.get("tx_hash") or s.get("transactionHash")
        formatted_swaps.append({
            "tx_hash": tx,
            "utc_day": day_str,
            "timestamp": ts,
            "action": s.get("action", "swap"),
            "explorer_url": f"https://testnet.bscscan.com/tx/{tx}" if tx else None,
        })

    hires_passed = len(qualifying_clients) >= 3
    swaps_passed = len(swaps) >= 5
    days_passed = len(distinct_utc_days) >= 3
    all_ready = hires_passed and swaps_passed and days_passed

    return {
        "hires": {
            "completed_count": len(valid_completed_jobs),
            "qualifying_distinct_clients": sorted(list(qualifying_clients)),
            "qualifying_count": len(qualifying_clients),
            "target": 3,
            "passed": hires_passed,
            "total_earned_wei": total_earned_wei,
            "total_earned_u": round(total_earned_wei / 10**18, 4),
        },
        "swaps": {
            "total_swaps": len(swaps),
            "target": 5,
            "passed": swaps_passed,
            "distinct_utc_days": sorted(list(distinct_utc_days)),
            "distinct_days_count": len(distinct_utc_days),
            "days_target": 3,
            "days_passed": days_passed,
            "recent_swaps": formatted_swaps[-10:],
        },
        "campaign_ready": all_ready,
    }


def query_chain_swaps(
    w3_logs: Web3,
    wallet: str,
    from_block: int,
    to_block: int,
) -> list[dict[str, Any]]:
    """Scan pair Swap events sent to our wallet in chunks <= 1000 blocks."""
    pair_contract = w3_logs.eth.contract(address=PAIR_WBNB_BUSD, abi=PAIR_SWAP_ABI)
    swaps: list[dict[str, Any]] = []

    curr = from_block
    while curr <= to_block:
        chunk_to = min(curr + 999, to_block)
        try:
            logs = pair_contract.events.Swap().get_logs(
                from_block=curr,
                to_block=chunk_to,
                argument_filters={"to": Web3.to_checksum_address(wallet)},
            )
            for log in logs:
                block = w3_logs.eth.get_block(log["blockNumber"])
                ts = block.get("timestamp", int(time.time()))
                swaps.append({
                    "tx_hash": log["transactionHash"].hex(),
                    "block_number": log["blockNumber"],
                    "timestamp": ts,
                    "action": "swap",
                })
        except Exception as exc:
            logger.warning("Failed querying Swap logs in [%d, %d]: %s", curr, chunk_to, exc)
        curr = chunk_to + 1

    return swaps


def get_campaign_progress(cfg: Settings | None = None) -> dict[str, Any]:
    """Return consolidated progress metrics (cached for 15s to respect RPC limits)."""
    global _PROGRESS_CACHE, _PROGRESS_CACHE_TIME
    now = time.time()
    if _PROGRESS_CACHE and (now - _PROGRESS_CACHE_TIME) < _CACHE_TTL_SEC:
        return dict(_PROGRESS_CACHE)

    if cfg is None:
        cfg = load_settings()

    target_wallet = CAMPAIGN_WALLET
    if cfg.private_key:
        try:
            from eth_account import Account
            target_wallet = Account.from_key(cfg.private_key).address
        except Exception:
            pass

    # 1. Retrieve completed jobs from memory tracking
    tracked = get_tracked_jobs()
    completed_jobs = [j for j in tracked if str(j.get("status", "")).upper() == "COMPLETED"]

    # 2. Collect swaps from local journal + on-chain scan if possible
    swaps_dict: dict[str, dict[str, Any]] = {}

    # Local journal successful swaps
    journal = get_recent_logs(limit=200)
    for entry in journal:
        if entry.get("status") == "success" and entry.get("tx_hash"):
            tx = entry["tx_hash"]
            swaps_dict[tx] = {
                "tx_hash": tx,
                "timestamp": entry.get("timestamp"),
                "action": entry.get("action", "swap"),
            }

    # On-chain scan if RPC_LOGS_URL is available
    try:
        w3_logs = get_web3(cfg.rpc_logs_url)
        head = w3_logs.eth.block_number
        start_block = cfg.job_scan_from_block or max(0, head - 10000)
        chain_swaps = query_chain_swaps(w3_logs, target_wallet, start_block, head)
        for s in chain_swaps:
            tx = s["tx_hash"]
            if tx not in swaps_dict:
                swaps_dict[tx] = s
    except Exception as exc:
        logger.warning("Could not query on-chain swaps: %s", exc)

    all_swaps = list(swaps_dict.values())

    metrics = count_campaign_metrics(
        swaps=all_swaps,
        completed_jobs=completed_jobs,
        excluded_clients=cfg.excluded_clients,
        our_wallet=target_wallet,
    )

    metrics["wallet"] = target_wallet
    metrics["chain_id"] = cfg.chain_id
    metrics["timestamp"] = datetime.now(timezone.utc).isoformat()

    _PROGRESS_CACHE = metrics
    _PROGRESS_CACHE_TIME = now
    return dict(metrics)
