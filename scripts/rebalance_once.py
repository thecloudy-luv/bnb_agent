"""Execute one rebalance check on BSC Testnet.

Defaults to dry-run. Pass --send to broadcast live transactions.
"""

import argparse
from datetime import datetime, timezone
import json
import logging
import sys
from eth_account import Account
from web3 import Web3
from agent.addresses import CAMPAIGN_WALLET
from agent.chain import get_pair_reserves, get_wallet_balances, get_web3
from agent.config import load_settings
from agent.executor import execute
from agent.market import fetch_bnb_closes
from agent.strategy import decide, decision_hash, momentum_24h

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("rebalance_once")


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate strategy and run rebalance once")
    parser.add_argument("--send", action="store_true", help="Broadcast transactions live (default: dry-run)")
    args = parser.parse_args()

    cfg = load_settings()
    if cfg.private_key:
        account = Account.from_key(cfg.private_key)
        wallet_address = Web3.to_checksum_address(account.address)
        if wallet_address != CAMPAIGN_WALLET:
            logger.error(
                "Configured signer %s does not match campaign wallet %s. Aborting.",
                wallet_address,
                CAMPAIGN_WALLET,
            )
            sys.exit(1)
        signer_key = cfg.private_key
    else:
        if args.send:
            logger.error("PRIVATE_KEY is required for live broadcast (--send)")
            sys.exit(1)
        logger.info("[Dry Run] No PRIVATE_KEY configured; simulating for campaign wallet %s", CAMPAIGN_WALLET)
        wallet_address = CAMPAIGN_WALLET
        signer_key = None

    dry_run = not args.send
    mode_str = "DRY RUN" if dry_run else "LIVE BROADCAST"
    logger.info("Starting rebalance check in %s mode for wallet: %s", mode_str, wallet_address)

    # 1. Fetch real market closes from Binance Vision
    logger.info("Fetching BNB market data from Binance Vision API...")
    try:
        closes = fetch_bnb_closes(hours=25)
        momentum = momentum_24h(closes)
        logger.info("BNB 24h momentum: %.4f (from %s closes)", momentum, len(closes))
    except Exception as exc:
        logger.warning("Could not fetch Binance market data (%s); using neutral momentum 0.0", exc)
        momentum = 0.0

    # 2. Connect to BSC Testnet and read on-chain state
    w3 = get_web3(cfg.rpc_url)
    balances = get_wallet_balances(w3, wallet_address)
    reserves = get_pair_reserves(w3)

    logger.info(
        "Wallet balances: tBNB=%.4f, WBNB=%.4f, BUSD=%.4f",
        balances["native_bnb"],
        balances["wbnb"],
        balances["busd"],
    )
    logger.info(
        "Pool reserves: WBNB=%.4f, BUSD=%.4f",
        reserves["reserve_wbnb"],
        reserves["reserve_busd"],
    )

    state = {
        "wbnb_balance": balances["wbnb"],
        "busd_balance": balances["busd"],
        "reserve_wbnb": reserves["reserve_wbnb"],
        "reserve_busd": reserves["reserve_busd"],
        "momentum": momentum,
    }

    now_utc = datetime.now(timezone.utc)
    decision = decide(state, now_utc)
    d_hash = decision_hash(decision)

    print("\n" + "=" * 60)
    print("STRATEGY DECISION SUMMARY")
    print("=" * 60)
    print(f"Action:        {decision.action}")
    print(f"Amount In:     {decision.amount_in} wei")
    print(f"Reason:        {decision.reason}")
    print(f"Decision Hash: 0x{d_hash.hex()}")
    print("Inputs:")
    print(json.dumps(decision.inputs, indent=2))
    print("=" * 60 + "\n")

    exec_result = execute(decision, signer_key, cfg.rpc_url, dry_run=dry_run)
    print("EXECUTION RESULT:")
    print(f"OK:        {exec_result.ok}")
    print(f"Simulated: {exec_result.simulated}")
    print(f"Tx Hash:   {exec_result.tx_hash}")
    print(f"Status:    {exec_result.status}")
    print(f"Gas Used:  {exec_result.gas_used}")
    if exec_result.error:
        print(f"Error:     {exec_result.error}")
    print(f"Details:   {json.dumps(exec_result.details, indent=2)}")


if __name__ == "__main__":
    main()
