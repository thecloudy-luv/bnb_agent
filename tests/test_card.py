"""Tests for A2A agent card."""

from fastapi.testclient import TestClient
from agent.card import build_agent_card
from agent.profile import (
    AGENT_DESCRIPTION,
    AGENT_NAME,
    CATEGORY,
    EXAMPLES,
    ICON_PATH,
    VERSION,
)
from agent.server import app


def test_build_agent_card() -> None:
    """Verify build_agent_card builds complete metadata with base_url."""
    base_url = "https://agent.example.com"
    card = build_agent_card(base_url)

    assert card["name"] == AGENT_NAME
    assert card["description"] == AGENT_DESCRIPTION
    assert card["version"] == VERSION
    assert card["category"] == CATEGORY
    assert card["iconUrl"] == f"{base_url}{ICON_PATH}"
    assert card["url"] == f"{base_url}/a2a"
    assert card["examples"] == EXAMPLES

    skill_ids = [s["id"] for s in card["skills"]]
    assert len(skill_ids) == 3
    assert "negotiate-erc8183-job" in skill_ids
    assert "erc8183-job-status" in skill_ids
    assert "rebalance-analysis" in skill_ids

    # Each skill must have id, name, description, examples
    for s in card["skills"]:
        assert s["id"]
        assert s["name"]
        assert s["description"]
        assert isinstance(s["examples"], list)


def test_agent_card_endpoint() -> None:
    """Test GET /.well-known/agent-card.json via FastAPI."""
    client = TestClient(app)
    response = client.get("/.well-known/agent-card.json")
    assert response.status_code == 200

    data = response.json()
    assert data["name"] == AGENT_NAME
    assert data["category"] == CATEGORY
    assert "iconUrl" in data
    assert "examples" in data
    assert len(data["skills"]) == 3
