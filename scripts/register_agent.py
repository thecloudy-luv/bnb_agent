"""ERC-8004 Identity Registration script for TiltBalance.

Defaults to dry-run. Pass --send to broadcast on-chain registration.
Pass --update <agentId> --send to update an existing agent's URI.
"""

import argparse
import base64
import json
import logging
import sys
from urllib.parse import urlparse
from eth_account import Account
import httpx
from web3 import Web3
from bnbagent.erc8004 import ERC8004Agent
from bnbagent.erc8004.agent_uri import AgentURIGenerator
from bnbagent.erc8004.models import AgentEndpoint
from bnbagent.wallets import EVMWalletProvider
from agent.addresses import CAMPAIGN_WALLET, IDENTITY_REGISTRY
from agent.config import load_settings
from agent.profile import AGENT_DESCRIPTION, AGENT_NAME, CATEGORY

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("register_agent")


def validate_public_endpoints(base_url: str) -> None:
    """Verify that logo and agent card return HTTP 200 before writing on-chain."""
    logo_url = f"{base_url}/logo.png"
    card_url = f"{base_url}/.well-known/agent-card.json"

    logger.info("Validating public endpoint accessibility: %s", logo_url)
    try:
        with httpx.Client(timeout=10.0) as client:
            logo_resp = client.get(logo_url)
            if logo_resp.status_code != 200:
                raise ValueError(f"Logo URL {logo_url} returned status {logo_resp.status_code}")
            card_resp = client.get(card_url)
            if card_resp.status_code != 200:
                raise ValueError(f"Agent card URL {card_url} returned status {card_resp.status_code}")
    except Exception as exc:
        raise ValueError(f"Failed to verify public endpoints: {exc}") from exc


def main() -> None:
    parser = argparse.ArgumentParser(description="Register TiltBalance on ERC-8004 Identity Registry")
    parser.add_argument("--send", action="store_true", help="Broadcast transaction on-chain (default: dry-run)")
    parser.add_argument("--update", type=int, help="Existing agentId to update (never register twice)")
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
    else:
        if args.send:
            logger.error("PRIVATE_KEY environment variable is not configured for --send")
            sys.exit(1)
        logger.info("[Dry Run] Simulating registration for campaign wallet %s", CAMPAIGN_WALLET)
        wallet_address = CAMPAIGN_WALLET

    base_url = cfg.public_base_url.rstrip("/")
    parsed_url = urlparse(base_url)
    is_localhost = parsed_url.hostname in ("localhost", "127.0.0.1", "0.0.0.0")

    dry_run = not args.send

    if not dry_run:
        if is_localhost:
            logger.error("Cannot register with localhost PUBLIC_BASE_URL: %s", base_url)
            sys.exit(1)
        try:
            validate_public_endpoints(base_url)
        except Exception as exc:
            logger.error("Endpoint validation failed: %s", exc)
            sys.exit(1)

    # Prepare registration metadata
    endpoints = [
        AgentEndpoint(
            name="A2A",
            endpoint=f"{base_url}/.well-known/agent-card.json",
            version="0.3.0",
        )
    ]

    reg_file = AgentURIGenerator.generate_registration_file(
        name=AGENT_NAME,
        description=AGENT_DESCRIPTION,
        image=f"{base_url}/logo.png",
        endpoints=endpoints,
        agent_id=args.update,
        identity_registry=IDENTITY_REGISTRY,
        chain_id=97,
        supported_trust=["erc8183"],
    )
    # Add custom category metadata
    reg_file["category"] = CATEGORY

    canonical_json = json.dumps(reg_file, indent=2)
    b64_content = base64.b64encode(canonical_json.encode("utf-8")).decode("utf-8")
    data_uri = f"data:application/json;base64,{b64_content}"

    print("\n" + "=" * 60)
    print("ERC-8004 REGISTRATION FILE (METADATA)")
    print("=" * 60)
    print(canonical_json)
    print("=" * 60 + "\n")

    if dry_run:
        logger.info("[Dry Run] Registration file generated successfully. No transaction sent.")
        print("Agent URI length:", len(data_uri))
        return

    # Live transaction using SDK
    wallet = EVMWalletProvider(password="reg-pass", private_key=cfg.private_key, persist=False)
    sdk = ERC8004Agent(wallet_provider=wallet, network="bsc-testnet", debug=True)

    if args.update:
        logger.info("Updating existing agentId %d with new agentURI...", args.update)
        sdk.contract.set_agent_uri(args.update, data_uri)
        logger.info("AgentId %d updated successfully on-chain!", args.update)
    else:
        # Check if already registered
        existing = sdk.get_local_agent_info(AGENT_NAME)
        if existing and existing.get("agent_id"):
            logger.warning(
                "Wallet already owns an agent named '%s' (agentId=%s). Use --update <id> instead of re-registering.",
                AGENT_NAME,
                existing["agent_id"],
            )
            sys.exit(1)

        logger.info("Broadcasting new agent registration on BSC Testnet...")
        result = sdk.register_agent(agent_uri=data_uri)
        agent_id = result.get("agentId")
        tx_hash = result.get("transactionHash")
        print("\n" + "=" * 60)
        print("REGISTRATION SUCCESSFUL")
        print(f"Agent ID: {agent_id}")
        print(f"Tx Hash:  {tx_hash}")
        print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
