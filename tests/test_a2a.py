"""Tests for A2A protocol and ERC-8183 skills."""

from unittest.mock import MagicMock, patch
from eth_account import Account
from eth_account.messages import encode_defunct
from fastapi.testclient import TestClient
import pytest
from bnbagent.erc8183.types import Job, JobStatus
from agent.server import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_negotiate_success(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test negotiate-erc8183-job skill with a temporary random private key."""
    temp_account = Account.create()
    monkeypatch.setenv("PRIVATE_KEY", temp_account.key.hex())

    request_payload = {
        "jsonrpc": "2.0",
        "id": "req-1",
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                "parts": [
                    {
                        "kind": "data",
                        "data": {
                            "skill": "negotiate-erc8183-job",
                            "task_description": "Execute sample grid trading plan",
                            "terms": {
                                "deliverables": "Execution summary report on IPFS",
                                "quality_standards": "Max slippage 0.5%, zero failed transactions",
                            },
                        },
                    }
                ],
            }
        },
    }

    response = client.post("/a2a", json=request_payload)
    assert response.status_code == 200
    res_json = response.json()

    assert res_json["jsonrpc"] == "2.0"
    assert res_json["id"] == "req-1"
    assert "error" not in res_json
    assert "result" in res_json

    result = res_json["result"]
    assert "response" in result
    assert result["response"]["accepted"] is True

    # 0.1 U with 18 decimals = 100000000000000000
    expected_price = "100000000000000000"
    assert result["response"]["terms"]["price"] == expected_price
    assert result["provider_address"].lower() == temp_account.address.lower()

    # Verify signature recovery
    negotiation_hash = result["negotiation_hash"]
    provider_sig = result["provider_sig"]
    assert negotiation_hash.startswith("0x")
    assert provider_sig.startswith("0x")

    recovered_address = Account.recover_message(
        encode_defunct(text=negotiation_hash),
        signature=provider_sig,
    )
    assert recovered_address.lower() == temp_account.address.lower()


def test_negotiate_missing_key(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test negotiate-erc8183-job when PRIVATE_KEY is not configured."""
    monkeypatch.delenv("PRIVATE_KEY", raising=False)

    request_payload = {
        "jsonrpc": "2.0",
        "id": "req-2",
        "method": "message/send",
        "params": {
            "skill": "negotiate-erc8183-job",
            "task_description": "Test without key",
            "terms": {
                "deliverables": "report",
                "quality_standards": "standard",
            },
        },
    }

    response = client.post("/a2a", json=request_payload)
    assert response.status_code == 200
    res_json = response.json()

    assert "error" in res_json
    assert res_json["error"]["code"] == -32603
    assert "provider key not configured" in res_json["error"]["message"]


def test_unknown_method(client: TestClient) -> None:
    """Test JSON-RPC method not found error (-32601)."""
    payload = {
        "jsonrpc": "2.0",
        "id": "req-3",
        "method": "unknown/action",
        "params": {},
    }
    response = client.post("/a2a", json=payload)
    assert response.status_code == 200
    res_json = response.json()
    assert res_json["error"]["code"] == -32601


def test_parse_error(client: TestClient) -> None:
    """Test JSON-RPC parse error (-32700)."""
    response = client.post(
        "/a2a",
        content="invalid json content {{{",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 200
    res_json = response.json()
    assert res_json["error"]["code"] == -32700


def test_invalid_params(client: TestClient) -> None:
    """Test JSON-RPC invalid params error (-32602)."""
    payload = {
        "jsonrpc": "2.0",
        "id": "req-4",
        "method": "message/send",
        "params": "not a dictionary",
    }
    response = client.post("/a2a", json=payload)
    assert response.status_code == 200
    res_json = response.json()
    assert res_json["error"]["code"] == -32602


def test_erc8183_job_status_mocked(client: TestClient) -> None:
    """Test erc8183-job-status skill with mocked chain reader."""
    mock_job = Job(
        id=42,
        client="0x1111111111111111111111111111111111111111",
        provider="0x2222222222222222222222222222222222222222",
        evaluator="0x3333333333333333333333333333333333333333",
        description="Sample job description",
        budget=100000000000000000,
        expired_at=1730000000,
        status=JobStatus.FUNDED,
        hook="0x0000000000000000000000000000000000000000",
        deliverable=b"\x00" * 32,
        submitted_at=0,
    )

    with patch("bnbagent.erc8183.ERC8183Client.get_job", return_value=mock_job):
        request_payload = {
            "jsonrpc": "2.0",
            "id": "req-5",
            "method": "message/send",
            "params": {
                "skill": "erc8183-job-status",
                "job_id": 42,
            },
        }
        response = client.post("/a2a", json=request_payload)
        assert response.status_code == 200
        res_json = response.json()

        assert "result" in res_json
        job_info = res_json["result"]["job"]
        assert job_info["id"] == 42
        assert job_info["status"] == 1
        assert job_info["status_name"] == "FUNDED"
        assert job_info["budget"] == "100000000000000000"
