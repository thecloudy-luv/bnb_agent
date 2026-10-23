"""Tests for strategy loop, status endpoint, and rebalance-analysis skill."""

from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
import pytest
from agent.addresses import CAMPAIGN_WALLET
from agent.config import load_settings
from agent.executor import ExecResult
from agent.loop import (
    get_last_check,
    get_recent_logs,
    record_journal_entry,
    run_strategy_cycle,
    start_strategy_loop,
    stop_strategy_loop,
)
from agent.server import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_loop_does_not_start_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUN_LOOPS", "0")
    with patch("threading.Thread") as mock_thread:
        start_strategy_loop()
        mock_thread.assert_not_called()
        stop_strategy_loop()


def test_run_strategy_cycle_no_swap() -> None:
    cfg = load_settings({})

    mock_w3 = MagicMock()
    mock_balances = {"native_bnb": 0.5, "wbnb": 0.5, "busd": 200.0}
    mock_reserves = {"reserve_wbnb": 10.0, "reserve_busd": 4000.0}

    with patch("agent.loop.fetch_bnb_closes", return_value=[600.0, 600.0]), \
         patch("agent.loop.get_web3", return_value=mock_w3), \
         patch("agent.loop.get_wallet_balances", return_value=mock_balances), \
         patch("agent.loop.get_pair_reserves", return_value=mock_reserves), \
         patch("agent.loop.execute") as mock_exec:
        entry = run_strategy_cycle(cfg)
        assert entry["action"] == "none"
        assert entry["status"] == "none"
        mock_exec.assert_not_called()

        last = get_last_check()
        assert last is not None
        assert last["action"] == "none"


def test_run_strategy_cycle_successful_swap() -> None:
    cfg = load_settings({})

    mock_w3 = MagicMock()
    # High WBNB creates drift > 0.03
    mock_balances = {"native_bnb": 0.5, "wbnb": 1.5, "busd": 100.0}
    mock_reserves = {"reserve_wbnb": 10.0, "reserve_busd": 4000.0}

    mock_exec_res = ExecResult(
        ok=True,
        tx_hash="0x1234567890abcdef",
        status=1,
        gas_used=120000,
        simulated=False,
    )

    with patch("agent.loop.fetch_bnb_closes", return_value=[600.0, 600.0]), \
         patch("agent.loop.get_web3", return_value=mock_w3), \
         patch("agent.loop.get_wallet_balances", return_value=mock_balances), \
         patch("agent.loop.get_pair_reserves", return_value=mock_reserves), \
         patch("agent.loop.execute", return_value=mock_exec_res):
        entry = run_strategy_cycle(cfg)
        assert entry["action"] == "sell_wbnb"
        assert entry["status"] == "success"
        assert entry["tx_hash"] == "0x1234567890abcdef"


def test_status_endpoint(client: TestClient) -> None:
    # Record a test entry
    record_journal_entry({
        "timestamp": "2026-10-19T12:00:00Z",
        "momentum": 0.02,
        "target_weight": 0.56,
        "current_weight": 0.50,
        "drift": -0.06,
        "action": "buy_wbnb",
        "amount_in": 1000,
        "reason": "drift threshold exceeded",
        "decision_hash": "0x1111",
        "tx_hash": "0x9999",
        "status": "success",
    })

    res = client.get("/status")
    assert res.status_code == 200
    data = res.json()

    assert data["status"] == "online"
    assert data["wallet"] == CAMPAIGN_WALLET
    assert "loops_enabled" in data
    assert data["last_check"] is not None
    assert len(data["recent_logs"]) >= 1
    assert data["recent_logs"][0]["explorer_url"] == "https://testnet.bscscan.com/tx/0x9999"


def test_skill_rebalance_analysis_custom_weight(client: TestClient) -> None:
    # Test skill with user's own 70/30 weight
    mock_reserves = {"reserve_wbnb": 10.0, "reserve_busd": 4000.0}

    with patch("agent.a2a.fetch_bnb_closes", return_value=[600.0, 600.0]), \
         patch("agent.a2a.get_web3"), \
         patch("agent.a2a.get_pair_reserves", return_value=mock_reserves):
        payload = {
            "jsonrpc": "2.0",
            "id": "analysis-1",
            "method": "message/send",
            "params": {
                "skill": "rebalance-analysis",
                "bnb_weight": 0.70,
            },
        }

        res = client.post("/a2a", json=payload)
        assert res.status_code == 200
        result = res.json()["result"]
        analysis = result["analysis"]

        assert analysis["current_bnb_weight"] == 0.70
        assert analysis["target_bnb_weight"] == 0.50
        assert analysis["drift"] == 0.20
        assert analysis["recommended_action"] == "sell_wbnb"
        assert "selling WBNB" in analysis["reason"]


def test_skill_rebalance_analysis_agent_portfolio(client: TestClient) -> None:
    # Test skill without params (analyzes agent's own portfolio)
    mock_balances = {"native_bnb": 0.5, "wbnb": 0.5, "busd": 200.0}
    mock_reserves = {"reserve_wbnb": 10.0, "reserve_busd": 4000.0}

    with patch("agent.a2a.fetch_bnb_closes", return_value=[600.0, 600.0]), \
         patch("agent.a2a.get_web3"), \
         patch("agent.a2a.get_wallet_balances", return_value=mock_balances), \
         patch("agent.a2a.get_pair_reserves", return_value=mock_reserves):
        payload = {
            "jsonrpc": "2.0",
            "id": "analysis-2",
            "method": "message/send",
            "params": {
                "skill": "rebalance-analysis",
            },
        }

        res = client.post("/a2a", json=payload)
        assert res.status_code == 200
        analysis = res.json()["result"]["analysis"]

        assert analysis["current_bnb_weight"] == 0.50
        assert analysis["target_bnb_weight"] == 0.50
        assert analysis["drift"] == 0.0
        assert analysis["recommended_action"] == "none"
