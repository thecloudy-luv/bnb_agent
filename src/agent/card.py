"""Agent card generation conforming to A2A specification."""

from typing import Any
from agent.profile import (
    AGENT_DESCRIPTION,
    AGENT_NAME,
    CATEGORY,
    EXAMPLES,
    ICON_PATH,
    VERSION,
)


def build_agent_card(base_url: str) -> dict[str, Any]:
    """Build the A2A Agent Card metadata dictionary."""
    normalized_base_url = base_url.rstrip("/")
    return {
        "name": AGENT_NAME,
        "description": AGENT_DESCRIPTION,
        "version": VERSION,
        "category": CATEGORY,
        "iconUrl": f"{normalized_base_url}{ICON_PATH}",
        "url": f"{normalized_base_url}/a2a",
        "skills": [
            {
                "id": "negotiate-erc8183-job",
                "name": "Quote Portfolio Rebalance Analysis",
                "description": "Request a wallet-signed price quote (0.1 U) for an autonomous portfolio rebalance analysis.",
                "examples": [
                    "Quote a portfolio rebalance analysis",
                    "Request signed quotation for BNB tilt allocation review",
                ],
            },
            {
                "id": "notify_funded",
                "name": "Notify Funded Job",
                "description": "Receives notification when an ERC-8183 job is funded and triggers immediate background execution.",
                "examples": [
                    "notify_funded for job_id 1543",
                ],
            },
            {
                "id": "erc8183-job-status",
                "name": "ERC-8183 Job Status",
                "description": "Query snapshot of an on-chain ERC-8183 job by job ID.",
                "examples": [
                    "Check status of job 1",
                    "Query on-chain state of job 42",
                ],
            },
            {
                "id": "rebalance-analysis",
                "name": "Rebalance Analysis",
                "description": "Analyze portfolio BNB/stable split and recommend rebalancing based on momentum.",
                "examples": [
                    "Analyse my 60/40 BNB/stable split and tell me how to rebalance",
                    "Give me today's BNB tilt target and the swap you would make",
                    "Analyze current TiltBalance agent portfolio state",
                ],
            },
        ],
        "examples": EXAMPLES,
    }
