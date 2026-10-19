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
                "name": "Negotiate ERC-8183 Job",
                "description": "Request a wallet-signed price quote for an ERC-8183 job.",
                "examples": [
                    "Negotiate a quote for task execution",
                    "Request signed quotation for job creation",
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
        ],
        "examples": EXAMPLES,
    }
