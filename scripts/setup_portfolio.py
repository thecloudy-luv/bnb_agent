"""Setup initial 50/50 WBNB/BUSD portfolio on BSC Testnet.

Defaults to dry-run. Pass --send to broadcast real on-chain transactions.
"""

import argparse
import logging
import sys
from eth_account import Account
from web3 import Web3
from agent.addresses import BUSD, CAMPAIGN_WALLET, WBNB
from agent.chain import get_amounts_out, get_wallet_balances, get_web3
from agent.config import load_settings
from agent.executor import wrap_bnb
from agent.strategy import Decision, decision_hash
from agent.executor import execute

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("setup_portfolio")


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize portfolio with WBNB and BUSD")
    parser.add_argument("--bnb", type=float, default=0.1, help="Total tBNB to allocate (default: 0.1)")
    parser.add_argument("--send", action="store_true", help="Broadcast transactions live (default: dry-run)")
    args = parser.parse_args()

    cfg = load_settings()
    if not cfg.private_key:
        logger.error("PRIVATE_KEY environment variable is not configured")
        sys.exit(1)

    account = Account.from_key(cfg.private_key)
    if Web3.to_checksum_address(account.address) != CAMPAIGN_WALLET:
        logger.error(
            "Configured signer %s does not match campaign wallet %s. Aborting.",
            account.address,
            CAMPAIGN_WALLET,
        )
        sys.exit(1)

    dry_run = not args.send
    mode_str = "DRY RUN" if dry_run else "LIVE BROADCAST"
    logger.info("Running setup_portfolio in %s mode for wallet: %s", mode_str, account.address)

    total_wei = Web3.to_wei(args.bnb, "ether")
    balances = get_wallet_balances(get_web3(cfg.rpc_url), account.address)
    if balances["wbnb_wei"] >= total_wei:
        logger.info("Wallet already holds %s WBNB (>= %s requested). Skipping wrap step.", balances["wbnb"], args.bnb)
    else:
        logger.info("Step 1: Wrap %s tBNB -> WBNB", args.bnb)
        wrap_res = wrap_bnb(total_wei, cfg.private_key, cfg.rpc_url, dry_run=dry_run)
        if not wrap_res.ok:
            logger.error("Wrap failed: %s", wrap_res.error)
            sys.exit(1)
        logger.info("Wrap step completed: %s", wrap_res)

    # Half to swap to BUSD
    half_wei = total_wei // 2
    logger.info("Step 2: Swap half (%s WBNB) -> BUSD for 50/50 balance", Web3.from_wei(half_wei, "ether"))

    setup_decision = Decision(
        action="sell_wbnb",
        amount_in=half_wei,
        reason="initial portfolio setup 50/50 allocation",
        inputs={"mode": "initial_setup", "half_wei": half_wei},
    )

    swap_res = execute(setup_decision, cfg.private_key, cfg.rpc_url, dry_run=dry_run)
    if not swap_res.ok:
        logger.error("Swap step failed: %s", swap_res.error)
        sys.exit(1)
    logger.info("Swap step completed: %s", swap_res)

    logger.info("Portfolio setup completed successfully (%s).", mode_str)


if __name__ == "__main__":
    main()
