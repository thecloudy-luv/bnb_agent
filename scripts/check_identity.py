"""Read-only script to query ERC-8004 Identity Registry for an agentId."""

import argparse
import base64
import json
import logging
import sys
from typing import Any
import httpx
from web3 import Web3
from agent.addresses import CAMPAIGN_WALLET, IDENTITY_REGISTRY
from agent.chain import get_web3
from agent.config import load_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("check_identity")

ERC8004_READ_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "tokenId", "type": "uint256"}],
        "name": "ownerOf",
        "outputs": [{"name": "", "type": "address"}],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [{"name": "tokenId", "type": "uint256"}],
        "name": "tokenURI",
        "outputs": [{"name": "", "type": "string"}],
        "type": "function",
    },
]


def check_identity(agent_id: int, rpc_url: str) -> dict[str, Any]:
    """Inspect on-chain ERC-8004 identity for a given agentId."""
    w3 = get_web3(rpc_url)
    contract = w3.eth.contract(address=IDENTITY_REGISTRY, abi=ERC8004_READ_ABI)

    try:
        owner = contract.functions.ownerOf(agent_id).call()
    except Exception as exc:
        raise ValueError(f"Could not retrieve ownerOf for agentId={agent_id}: {exc}") from exc

    try:
        token_uri = contract.functions.tokenURI(agent_id).call()
    except Exception as exc:
        logger.warning("Could not read tokenURI for agentId=%s: %s", agent_id, exc)
        token_uri = ""

    parsed_data = None
    if token_uri.startswith("data:application/json;base64,"):
        b64_part = token_uri.split(",", 1)[1]
        try:
            raw_bytes = base64.b64decode(b64_part)
            parsed_data = json.loads(raw_bytes.decode("utf-8"))
        except Exception as exc:
            logger.warning("Failed to decode base64 agentURI: %s", exc)
    elif token_uri.startswith("http://") or token_uri.startswith("https://"):
        try:
            with httpx.Client(timeout=10.0) as client:
                r = client.get(token_uri)
                if r.status_code == 200:
                    parsed_data = r.json()
        except Exception as exc:
            logger.warning("Failed to fetch HTTP agentURI: %s", exc)

    owner_matches = (Web3.to_checksum_address(owner) == CAMPAIGN_WALLET)

    return {
        "agent_id": agent_id,
        "owner": Web3.to_checksum_address(owner),
        "owner_matches_campaign_wallet": owner_matches,
        "token_uri": token_uri,
        "parsed_metadata": parsed_data,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Query ERC-8004 identity on BSC Testnet")
    parser.add_argument("agent_id", type=int, help="Agent ID to query on the Identity Registry")
    args = parser.parse_args()

    cfg = load_settings()
    logger.info("Querying identity for agentId=%d on chain 97...", args.agent_id)

    try:
        info = check_identity(args.agent_id, cfg.rpc_url)
    except Exception as exc:
        logger.error("Failed to query identity: %s", exc)
        sys.exit(1)

    print("\n" + "=" * 60)
    print("ERC-8004 IDENTITY DETAILS")
    print("=" * 60)
    print(f"Agent ID:       {info['agent_id']}")
    print(f"Owner Address:  {info['owner']}")
    print(f"Matches Wallet: {'YES (Valid)' if info['owner_matches_campaign_wallet'] else 'NO (Owner mismatch!)'}")
    print(f"Expected Owner: {CAMPAIGN_WALLET}")
    print(f"Token URI:      {info['token_uri'][:80]}..." if len(info['token_uri']) > 80 else f"Token URI: {info['token_uri']}")
    if info["parsed_metadata"]:
        print("\nDecoded Agent Metadata:")
        print(json.dumps(info["parsed_metadata"], indent=2))
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
