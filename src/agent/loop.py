"""Background strategy loop and in-memory execution journal."""

from collections import deque
from datetime import datetime, timezone
import logging
import os
import threading
import time
from typing import Any
from agent.addresses import CAMPAIGN_WALLET
from agent.chain import get_pair_reserves, get_wallet_balances, get_web3
from agent.config import Settings, load_settings
from agent.executor import execute
from agent.market import fetch_bnb_closes
from agent.strategy import decide, decision_hash, momentum_24h

logger = logging.getLogger(__name__)

# Max 200 items in memory journal
_JOURNAL: deque[dict[str, Any]] = deque(maxlen=200)
_JOURNAL_LOCK = threading.Lock()
_LAST_SWAP_DAY: str | None = None
_LAST_CHECK: dict[str, Any] | None = None

_loop_thread: threading.Thread | None = None
_stop_event = threading.Event()


def record_journal_entry(entry: dict[str, Any]) -> None:
    """Thread-safe append of a decision log entry to the in-memory journal."""
    global _LAST_CHECK
    with _JOURNAL_LOCK:
        _JOURNAL.appendleft(entry)
        _LAST_CHECK = {
            "timestamp": entry["timestamp"],
            "momentum": entry["momentum"],
            "target_weight": entry["target_weight"],
            "current_weight": entry["current_weight"],
            "drift": entry["drift"],
            "action": entry["action"],
            "reason": entry["reason"],
            "tx_hash": entry.get("tx_hash"),
        }


def get_recent_logs(limit: int = 20) -> list[dict[str, Any]]:
    """Return the N most recent journal entries with explorer links."""
    with _JOURNAL_LOCK:
        entries = list(_JOURNAL)[:limit]

    formatted: list[dict[str, Any]] = []
    for item in entries:
        copy_item = dict(item)
        tx = copy_item.get("tx_hash")
        copy_item["explorer_url"] = f"https://testnet.bscscan.com/tx/{tx}" if tx else None
        formatted.append(copy_item)
    return formatted


def get_last_check() -> dict[str, Any] | None:
    """Return the snapshot of the most recent strategy evaluation."""
    with _JOURNAL_LOCK:
        return dict(_LAST_CHECK) if _LAST_CHECK else None


def run_strategy_cycle(cfg: Settings) -> dict[str, Any]:
    """Execute one evaluation iteration of the strategy."""
    global _LAST_SWAP_DAY
    now_utc = datetime.now(timezone.utc)
    timestamp_str = now_utc.isoformat()

    try:
        closes = fetch_bnb_closes(hours=25)
        momentum = momentum_24h(closes)
    except Exception as exc:
        logger.warning("Could not fetch BNB market closes (%s); using neutral momentum 0.0", exc)
        momentum = 0.0

    w3 = get_web3(cfg.rpc_url)
    target_wallet = CAMPAIGN_WALLET
    balances = get_wallet_balances(w3, target_wallet)
    reserves = get_pair_reserves(w3)

    state = {
        "wbnb_balance": balances["wbnb"],
        "busd_balance": balances["busd"],
        "reserve_wbnb": reserves["reserve_wbnb"],
        "reserve_busd": reserves["reserve_busd"],
        "momentum": momentum,
    }

    decision = decide(state, now_utc, last_swap_day=_LAST_SWAP_DAY)
    d_hash = "0x" + decision_hash(decision).hex()

    tx_hash: str | None = None
    status_str = "skipped"

    if decision.action != "none":
        logger.info("Executing strategy action: %s (%s)", decision.action, decision.reason)
        res = execute(decision, cfg.private_key, cfg.rpc_url, dry_run=False)
        if res.ok and res.status == 1:
            tx_hash = res.tx_hash
            status_str = "success"
            _LAST_SWAP_DAY = now_utc.strftime("%Y-%m-%d")
            logger.info("Swap executed successfully! tx: %s", tx_hash)
        else:
            status_str = "failed"
            logger.error("Swap execution failed: %s", res.error)
    else:
        status_str = "none"

    entry = {
        "timestamp": timestamp_str,
        "momentum": decision.inputs.get("momentum", momentum),
        "target_weight": decision.inputs.get("target_weight", 0.5),
        "current_weight": decision.inputs.get("current_weight", 0.5),
        "drift": decision.inputs.get("drift", 0.0),
        "action": decision.action,
        "amount_in": decision.amount_in,
        "reason": decision.reason,
        "decision_hash": d_hash,
        "tx_hash": tx_hash,
        "status": status_str,
    }

    record_journal_entry(entry)
    return entry


def _strategy_worker(stop_event: threading.Event) -> None:
    """Worker thread running strategy evaluation every interval."""
    interval = int(os.getenv("STRATEGY_INTERVAL_SEC", "900"))
    logger.info("Strategy worker thread started (interval=%ds)", interval)

    while not stop_event.is_set():
        cfg = load_settings()
        try:
            run_strategy_cycle(cfg)
        except Exception as exc:
            logger.error("Error during strategy cycle: %s", exc, exc_info=True)

        # Sleep in short increments to respond quickly to stop_event
        for _ in range(interval):
            if stop_event.is_set():
                break
            time.sleep(1)

    logger.info("Strategy worker thread stopped")


def start_strategy_loop() -> None:
    """Start background strategy loop if RUN_LOOPS=1."""
    global _loop_thread, _stop_event
    cfg = load_settings()
    if not cfg.run_loops:
        logger.info("Background strategy loop is disabled (RUN_LOOPS != 1)")
        return

    if _loop_thread and _loop_thread.is_alive():
        logger.warning("Strategy loop is already running")
        return

    _stop_event.clear()
    _loop_thread = threading.Thread(target=_strategy_worker, args=(_stop_event,), daemon=True)
    _loop_thread.start()
    logger.info("Started background strategy loop thread")


def stop_strategy_loop() -> None:
    """Stop background strategy loop."""
    global _stop_event, _loop_thread
    _stop_event.set()
    if _loop_thread and _loop_thread.is_alive():
        _loop_thread.join(timeout=3.0)
    _loop_thread = None
