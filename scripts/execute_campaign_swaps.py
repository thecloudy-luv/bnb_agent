"""Script to execute qualifying campaign swaps on BSC Testnet."""

from datetime import datetime, timezone
import json
import logging
import sys
import time

from agent.config import load_settings
from agent.executor import execute
from agent.strategy import Decision

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("campaign_swaps")


def main() -> None:
    cfg = load_settings()
    if not cfg.private_key:
        logger.error("PRIVATE_KEY not set")
        sys.exit(1)

    now_utc = datetime.now(timezone.utc)
    today_str = now_utc.strftime("%Y-%m-%d")
    logger.info("Executing campaign swap on UTC Day: %s", today_str)

    # Swap 3: sell 0.002 WBNB -> BUSD
    decision3 = Decision(
        action="sell_wbnb",
        amount_in=int(0.002 * 10**18),
        reason=f"Day 3 Campaign Swap 1 ({today_str}): periodic rebalance sell 0.002 WBNB",
        inputs={
            "day": today_str,
            "swap_index": 3,
            "action": "sell_wbnb",
            "amount_eth": 0.002,
        },
    )

    logger.info("Broadcasting Swap 3...")
    res3 = execute(decision3, cfg.private_key, cfg.rpc_url, dry_run=False)
    logger.info("Swap 3 result: ok=%s, tx=%s, status=%s, error=%s", res3.ok, res3.tx_hash, res3.status, res3.error)
    if not res3.ok:
        sys.exit(1)

    time.sleep(5)

    # Swap 4: buy WBNB with 1.0 BUSD -> WBNB
    decision4 = Decision(
        action="buy_wbnb",
        amount_in=int(1.0 * 10**18),
        reason=f"Day 3 Campaign Swap 2 ({today_str}): periodic rebalance buy WBNB with 1 BUSD",
        inputs={
            "day": today_str,
            "swap_index": 4,
            "action": "buy_wbnb",
            "amount_eth": 1.0,
        },
    )

    logger.info("Broadcasting Swap 4...")
    res4 = execute(decision4, cfg.private_key, cfg.rpc_url, dry_run=False)
    logger.info("Swap 4 result: ok=%s, tx=%s, status=%s, error=%s", res4.ok, res4.tx_hash, res4.status, res4.error)
    if not res4.ok:
        sys.exit(1)

    time.sleep(5)

    # Swap 5: sell 0.002 WBNB -> BUSD
    decision5 = Decision(
        action="sell_wbnb",
        amount_in=int(0.002 * 10**18),
        reason=f"Day 3 Campaign Swap 3 ({today_str}): periodic rebalance sell 0.002 WBNB",
        inputs={
            "day": today_str,
            "swap_index": 5,
            "action": "sell_wbnb",
            "amount_eth": 0.002,
        },
    )

    logger.info("Broadcasting Swap 5...")
    res5 = execute(decision5, cfg.private_key, cfg.rpc_url, dry_run=False)
    logger.info("Swap 5 result: ok=%s, tx=%s, status=%s, error=%s", res5.ok, res5.tx_hash, res5.status, res5.error)
    if not res5.ok:
        sys.exit(1)

    print("\n" + "=" * 60)
    print("ALL 3 SWAPS COMPLETED SUCCESSFULLY!")
    print(f"Swap 3 Tx: {res3.tx_hash}")
    print(f"Swap 4 Tx: {res4.tx_hash}")
    print(f"Swap 5 Tx: {res5.tx_hash}")
    print("=" * 60)


if __name__ == "__main__":
    main()
