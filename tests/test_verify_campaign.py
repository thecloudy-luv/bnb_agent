"""Tests for verify_campaign audit logic."""

from unittest.mock import MagicMock, patch
from scripts.verify_campaign import audit_campaign_progress, verify_agent_identity, verify_agent_card, verify_health_endpoint
from agent.addresses import CAMPAIGN_WALLET


def test_audit_campaign_progress_evaluation() -> None:
    """Verify audit_campaign_progress checks hires, swaps, and days."""
    # Sub-case: incomplete
    incomplete_data = {
        "hires": {
            "qualifying_distinct_clients": ["0x111", "0x222"],
            "total_earned_u": 0.2,
        },
        "swaps": {
            "total_swaps": 4,
            "distinct_utc_days": ["2026-10-01", "2026-10-02"],
        },
    }
    audit = audit_campaign_progress(incomplete_data)
    assert audit["hires"][0] is False
    assert audit["swaps"][0] is False
    assert audit["days"][0] is False

    # Sub-case: complete
    complete_data = {
        "hires": {
            "qualifying_distinct_clients": ["0x111", "0x222", "0x333"],
            "total_earned_u": 0.3,
        },
        "swaps": {
            "total_swaps": 5,
            "distinct_utc_days": ["2026-10-01", "2026-10-02", "2026-10-03"],
        },
    }
    audit_ok = audit_campaign_progress(complete_data)
    assert audit_ok["hires"][0] is True
    assert audit_ok["swaps"][0] is True
    assert audit_ok["days"][0] is True


def test_verify_agent_identity() -> None:
    mock_w3 = MagicMock()
    mock_contract = MagicMock()
    mock_w3.eth.contract.return_value = mock_contract

    # Case: matching owner
    mock_contract.functions.ownerOf.return_value.call.return_value = CAMPAIGN_WALLET

    ok, msg = verify_agent_identity(mock_w3, 42, CAMPAIGN_WALLET)
    assert ok is True
    assert "matches campaign wallet" in msg

    # Case: mismatched owner
    mock_contract.functions.ownerOf.return_value.call.return_value = "0x9999999999999999999999999999999999999999"

    ok2, msg2 = verify_agent_identity(mock_w3, 42, CAMPAIGN_WALLET)
    assert ok2 is False
    assert "does not match" in msg2

    # Case: None agent_id
    ok3, msg3 = verify_agent_identity(mock_w3, None, CAMPAIGN_WALLET)
    assert ok3 is False
    assert "not specified" in msg3


@patch("httpx.Client")
def test_verify_health_and_card(mock_httpx: MagicMock) -> None:
    mock_client = MagicMock()
    mock_httpx.return_value.__enter__.return_value = mock_client

    # Health check success
    health_resp = MagicMock()
    health_resp.status_code = 200
    health_resp.json.return_value = {"status": "ok", "chain_id": 97, "loops_enabled": False}
    mock_client.get.return_value = health_resp

    h_ok, h_msg = verify_health_endpoint("http://localhost:8000")
    assert h_ok is True
    assert "status=ok" in h_msg

    # Card check success
    card_resp = MagicMock()
    card_resp.status_code = 200
    card_resp.json.return_value = {
        "name": "TiltBalance",
        "category": "rebalancing",
        "skills": [{"name": "negotiate-erc8183-job"}, {"name": "rebalance-analysis"}],
    }
    mock_client.get.return_value = card_resp

    c_ok, c_msg = verify_agent_card("http://localhost:8000")
    assert c_ok is True
    assert "TiltBalance" in c_msg
