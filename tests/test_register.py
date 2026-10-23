"""Tests for ERC-8004 identity registration and verification scripts."""

import base64
import json
from unittest.mock import MagicMock, patch
from eth_account import Account
import pytest
from agent.addresses import CAMPAIGN_WALLET
from scripts.check_identity import check_identity
from scripts.register_agent import validate_public_endpoints


def test_validate_public_endpoints_success() -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 200

    with patch("httpx.Client.get", return_value=mock_resp):
        # Should complete without raising
        validate_public_endpoints("https://tiltbalance.onrender.com")


def test_validate_public_endpoints_failure() -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 404

    with patch("httpx.Client.get", return_value=mock_resp):
        with pytest.raises(ValueError, match="status 404"):
            validate_public_endpoints("https://tiltbalance.onrender.com")


def test_check_identity_matching_owner() -> None:
    agent_id = 999
    sample_metadata = {
        "name": "TiltBalance",
        "description": "Rebalancing agent",
        "category": "rebalancing",
    }
    encoded_uri = "data:application/json;base64," + base64.b64encode(
        json.dumps(sample_metadata).encode("utf-8")
    ).decode("utf-8")

    mock_w3 = MagicMock()
    mock_contract = MagicMock()
    mock_contract.functions.ownerOf.return_value.call.return_value = CAMPAIGN_WALLET
    mock_contract.functions.tokenURI.return_value.call.return_value = encoded_uri
    mock_w3.eth.contract.return_value = mock_contract

    with patch("scripts.check_identity.get_web3", return_value=mock_w3):
        res = check_identity(agent_id, "http://localhost:8545")
        assert res["agent_id"] == 999
        assert res["owner"] == CAMPAIGN_WALLET
        assert res["owner_matches_campaign_wallet"] is True
        assert res["parsed_metadata"]["name"] == "TiltBalance"


def test_check_identity_mismatched_owner() -> None:
    other_wallet = "0x1111111111111111111111111111111111111111"
    mock_w3 = MagicMock()
    mock_contract = MagicMock()
    mock_contract.functions.ownerOf.return_value.call.return_value = other_wallet
    mock_contract.functions.tokenURI.return_value.call.return_value = ""
    mock_w3.eth.contract.return_value = mock_contract

    with patch("scripts.check_identity.get_web3", return_value=mock_w3):
        res = check_identity(123, "http://localhost:8545")
        assert res["owner_matches_campaign_wallet"] is False
