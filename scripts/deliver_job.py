"""Script to evaluate and deliver an ERC-8183 job manually."""

import argparse
import logging
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from eth_account import Account
from agent.addresses import CAMPAIGN_WALLET
from agent.config import load_settings
from agent.jobs import create_erc8183_client, process_single_job

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("deliver_job")


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate and deliver an ERC-8183 job.")
    parser.add_argument("job_id", type=int, help="ERC-8183 Job ID to evaluate/deliver")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--send",
        action="store_true",
        help="Execute real upload and on-chain submission",
    )
    group.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Simulate execution without sending transactions (default)",
    )

    args = parser.parse_args()
    dry_run = not args.send

    cfg = load_settings()
    our_wallet = CAMPAIGN_WALLET
    if cfg.private_key:
        try:
            our_wallet = Account.from_key(cfg.private_key).address
        except Exception:
            pass

    print(f"=== ERC-8183 Job Desk Deliver Tool ===")
    print(f"Target Job ID  : {args.job_id}")
    print(f"Campaign Wallet: {our_wallet}")
    print(f"Execution Mode : {'DRY-RUN (Simulated)' if dry_run else 'LIVE (--send)'}")
    print(f"RPC URL        : {cfg.rpc_url}")
    print("=======================================")

    client = create_erc8183_client(cfg.rpc_url, cfg.private_key)
    try:
        job = client.get_job(args.job_id)
    except Exception as exc:
        print(f"❌ Failed to fetch job {args.job_id} on-chain: {exc}")
        sys.exit(1)

    print(f"Job Details:")
    print(f"  - Status       : {job.status.name} ({job.status.value})")
    print(f"  - Client       : {job.client}")
    print(f"  - Provider     : {job.provider}")
    print(f"  - Budget       : {job.budget} wei ({job.budget / 10**18:.4f} U)")
    print(f"  - Expired At   : {job.expired_at}")
    print(f"  - Submitted At : {job.submitted_at}")

    if job.provider.lower() != our_wallet.lower():
        print(
            f"\n⚠️  Skipping job {args.job_id}: Provider on-chain ({job.provider}) "
            f"does not match our campaign wallet ({our_wallet})."
        )
        print("This job is addressed to another agent and cannot be serviced by TiltBalance.")
        sys.exit(0)

    # Process job
    result = process_single_job(args.job_id, cfg, dry_run=dry_run)
    print(f"\nProcessing Result:")
    for k, v in result.items():
        print(f"  - {k}: {v}")

    if result.get("error"):
        print(f"\n⚠️  Job not completed: {result['error']}")
    else:
        print(f"\n✅ Job processed successfully. Status: {result.get('status')}")


if __name__ == "__main__":
    main()
