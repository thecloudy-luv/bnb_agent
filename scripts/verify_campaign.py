"""Verification and audit script for BNB Chain Set & Earn campaign criteria."""

import argparse
import logging
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

import httpx
from web3 import Web3

from bnbagent.erc8004 import ERC8004Agent

from agent.addresses import CAMPAIGN_WALLET, IDENTITY_REGISTRY
from agent.config import load_settings
from agent.progress import get_campaign_progress

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("verify_campaign")


ERC8004_READ_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "tokenId", "type": "uint256"}],
        "name": "ownerOf",
        "outputs": [{"name": "", "type": "address"}],
        "type": "function",
    }
]


def verify_agent_identity(
    w3: Web3,
    agent_id: int | None,
    expected_wallet: str,
) -> tuple[bool, str]:
    """Verify ERC-8004 identity on-chain."""
    if agent_id is None:
        return False, "ERC-8004 agentId is not specified (--agent-id or ERC8004_AGENT_ID)"

    try:
        contract = w3.eth.contract(address=IDENTITY_REGISTRY, abi=ERC8004_READ_ABI)
        owner = contract.functions.ownerOf(agent_id).call()
        if owner.lower() == expected_wallet.lower():
            return True, f"agentId {agent_id} ownerOf matches campaign wallet ({owner})"
        return False, f"agentId {agent_id} ownerOf ({owner}) does not match campaign wallet ({expected_wallet})"
    except Exception as exc:
        return False, f"Failed querying ERC-8004 registry for agentId {agent_id}: {exc}"


def verify_health_endpoint(base_url: str) -> tuple[bool, str]:
    """Verify GET /health response."""
    url = f"{base_url.rstrip('/')}/health"
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(url)
            if resp.status_code != 200:
                return False, f"GET {url} returned HTTP {resp.status_code}"
            data = resp.json()
            if data.get("status") == "ok" and data.get("chain_id") == 97:
                return True, f"GET {url} returned status=ok, chain_id=97 (loops_enabled={data.get('loops_enabled')})"
            return False, f"GET {url} unexpected payload: {data}"
    except Exception as exc:
        return False, f"Failed connecting to {url}: {exc}"


def verify_agent_card(base_url: str) -> tuple[bool, str]:
    """Verify GET /.well-known/agent-card.json response."""
    url = f"{base_url.rstrip('/')}/.well-known/agent-card.json"
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(url)
            if resp.status_code != 200:
                return False, f"GET {url} returned HTTP {resp.status_code}"
            data = resp.json()
            name = data.get("name")
            category = data.get("category")
            skills = [s.get("name") for s in data.get("skills", [])]
            if name and category == "rebalancing" and len(skills) >= 2:
                return True, f"Agent card resolved (name='{name}', category='{category}', skills={skills})"
            return False, f"Agent card invalid (name='{name}', category='{category}', skills={skills})"
    except Exception as exc:
        return False, f"Failed connecting to {url}: {exc}"


def audit_campaign_progress(progress_data: dict) -> dict[str, tuple[bool, str]]:
    """Audit campaign progress against targets."""
    hires = progress_data.get("hires", {})
    swaps = progress_data.get("swaps", {})

    # Check 1: >= 3 distinct qualifying completed hires
    qualifying_clients = hires.get("qualifying_distinct_clients", [])
    hires_passed = len(qualifying_clients) >= 3
    hires_msg = (
        f"{len(qualifying_clients)} / 3 qualifying completed hires from distinct clients: "
        f"{qualifying_clients} (earned {hires.get('total_earned_u', 0)} U)"
    )

    # Check 2: >= 5 swaps
    swap_count = swaps.get("total_swaps", 0)
    swaps_passed = swap_count >= 5
    swaps_msg = f"{swap_count} / 5 qualifying DEX swaps recorded on WBNB/BUSD pair"

    # Check 3: >= 3 distinct UTC days
    days = swaps.get("distinct_utc_days", [])
    days_passed = len(days) >= 3
    days_msg = f"{len(days)} / 3 distinct UTC swap days: {days}"

    return {
        "hires": (hires_passed, hires_msg),
        "swaps": (swaps_passed, swaps_msg),
        "days": (days_passed, days_msg),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit and verify BNB Chain Set & Earn campaign status.")
    parser.add_argument("--agent-id", type=int, default=None, help="ERC-8004 Agent ID")
    parser.add_argument("--base-url", type=str, default=None, help="Base URL of agent service")
    args = parser.parse_args()

    cfg = load_settings()
    base_url = args.base_url or cfg.public_base_url or "http://localhost:8000"
    agent_id = args.agent_id or (int(os.environ["ERC8004_AGENT_ID"]) if "ERC8004_AGENT_ID" in os.environ else None)

    print("==================================================================")
    print("        BNB Chain 'Set and Earn' Campaign Verification Audit       ")
    print("==================================================================")
    print(f"Agent Base URL  : {base_url}")
    print(f"Campaign Wallet : {CAMPAIGN_WALLET}")
    print(f"Agent ID        : {agent_id if agent_id is not None else '<TBD - pending registration>'}")
    print(f"Network         : BSC Testnet (Chain ID 97)")
    print("------------------------------------------------------------------")

    results: list[tuple[str, bool, str]] = []

    # 1. Health check
    h_ok, h_msg = verify_health_endpoint(base_url)
    results.append(("Service Health (/health)", h_ok, h_msg))

    # 2. Agent Card
    c_ok, c_msg = verify_agent_card(base_url)
    results.append(("Agent Card & Skills (/agent-card.json)", c_ok, c_msg))

    # 3. ERC-8004 Identity
    from agent.chain import get_web3
    w3 = get_web3(cfg.rpc_url)
    id_ok, id_msg = verify_agent_identity(w3, agent_id, CAMPAIGN_WALLET)
    results.append(("ERC-8004 Identity Ownership", id_ok, id_msg))

    # 4 & 5. Campaign Metrics
    progress_data = get_campaign_progress(cfg)
    audit = audit_campaign_progress(progress_data)
    results.append(("ERC-8183 Independent Hires (>= 3)", audit["hires"][0], audit["hires"][1]))
    results.append(("PancakeSwap DEX Swaps (>= 5)", audit["swaps"][0], audit["swaps"][1]))
    results.append(("Active UTC Swap Days (>= 3)", audit["days"][0], audit["days"][1]))

    all_passed = all(r[1] for r in results)

    print("\nAudit Results:")
    for title, passed, evidence in results:
        status_icon = "[PASS] ✅" if passed else "[FAIL] ❌"
        print(f"  {status_icon} {title}")
        print(f"         Evidence: {evidence}")

    print("\n------------------------------------------------------------------")
    if all_passed:
        print("🎯 OVERALL STATUS: ALL CRITERIA PASSED! Ready for final submission.")
    else:
        print("⏳ OVERALL STATUS: REQUIREMENTS IN PROGRESS.")
    print("==================================================================")


if __name__ == "__main__":
    main()
