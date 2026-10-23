"""Tests for dashboard and campaign counting metrics."""

from fastapi.testclient import TestClient
import pytest

from agent.addresses import CAMPAIGN_WALLET
from agent.progress import count_campaign_metrics
from agent.server import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_index_dashboard_returns_html(client: TestClient) -> None:
    """Verify GET / returns 200 with HTML dashboard."""
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "TiltBalance" in response.text
    assert "Campaign" in response.text or "Set and Earn" in response.text


def test_progress_endpoint(client: TestClient) -> None:
    """Verify GET /progress returns campaign progress structure."""
    response = client.get("/progress")
    assert response.status_code == 200
    data = response.json()
    assert "hires" in data
    assert "swaps" in data
    assert "campaign_ready" in data
    assert "wallet" in data


def test_count_campaign_metrics_excludes_self_and_checker() -> None:
    """Verify counting logic ignores self wallet and configured checker addresses."""
    our_wallet = CAMPAIGN_WALLET
    checker_wallet = "0x9999999999999999999999999999999999999999"
    legit_client_1 = "0x1111111111111111111111111111111111111111"
    legit_client_2 = "0x2222222222222222222222222222222222222222"

    completed_jobs = [
        {"id": 1, "client": our_wallet, "status": "COMPLETED", "budget": 10**17},  # self
        {"id": 2, "client": checker_wallet, "status": "COMPLETED", "budget": 10**17},  # checker
        {"id": 3, "client": legit_client_1, "status": "COMPLETED", "budget": 10**17},  # valid
        {"id": 4, "client": legit_client_2, "status": "COMPLETED", "budget": 2 * 10**17},  # valid
        {"id": 5, "client": "0x3333333333333333333333333333333333333333", "status": "FUNDED", "budget": 10**17},  # not completed
    ]

    swaps = [
        {"tx_hash": "0x1", "timestamp": "2026-10-01T12:00:00Z"},
        {"tx_hash": "0x2", "timestamp": "2026-10-02T12:00:00Z"},
    ]

    metrics = count_campaign_metrics(
        swaps=swaps,
        completed_jobs=completed_jobs,
        excluded_clients=(checker_wallet,),
        our_wallet=our_wallet,
    )

    hires = metrics["hires"]
    assert hires["qualifying_count"] == 2
    assert legit_client_1.lower() in hires["qualifying_distinct_clients"]
    assert legit_client_2.lower() in hires["qualifying_distinct_clients"]
    assert our_wallet.lower() not in hires["qualifying_distinct_clients"]
    assert checker_wallet.lower() not in hires["qualifying_distinct_clients"]
    assert hires["passed"] is False  # need 3


def test_count_campaign_metrics_distinct_utc_days() -> None:
    """Verify distinct UTC days calculation across timestamps."""
    our_wallet = CAMPAIGN_WALLET

    # 5 swaps, but all on the same day -> days_passed is False
    same_day_swaps = [
        {"tx_hash": f"0x{i}", "timestamp": 1790000000 + i * 100}
        for i in range(5)
    ]

    metrics = count_campaign_metrics(
        swaps=same_day_swaps,
        completed_jobs=[],
        excluded_clients=(),
        our_wallet=our_wallet,
    )
    assert metrics["swaps"]["total_swaps"] == 5
    assert metrics["swaps"]["passed"] is True
    assert metrics["swaps"]["distinct_days_count"] == 1
    assert metrics["swaps"]["days_passed"] is False


def test_count_campaign_metrics_all_ready() -> None:
    """Verify campaign_ready is True when all criteria are satisfied."""
    our_wallet = CAMPAIGN_WALLET

    completed_jobs = [
        {"id": 1, "client": "0x1111111111111111111111111111111111111111", "status": "COMPLETED", "budget": 10**17},
        {"id": 2, "client": "0x2222222222222222222222222222222222222222", "status": "COMPLETED", "budget": 10**17},
        {"id": 3, "client": "0x3333333333333333333333333333333333333333", "status": "COMPLETED", "budget": 10**17},
    ]

    # 5 swaps across 3 distinct UTC days
    swaps = [
        {"tx_hash": "0x1", "utc_day": "2026-10-01"},
        {"tx_hash": "0x2", "utc_day": "2026-10-01"},
        {"tx_hash": "0x3", "utc_day": "2026-10-02"},
        {"tx_hash": "0x4", "utc_day": "2026-10-03"},
        {"tx_hash": "0x5", "utc_day": "2026-10-03"},
    ]

    metrics = count_campaign_metrics(
        swaps=swaps,
        completed_jobs=completed_jobs,
        excluded_clients=(),
        our_wallet=our_wallet,
    )

    assert metrics["hires"]["passed"] is True
    assert metrics["swaps"]["passed"] is True
    assert metrics["swaps"]["days_passed"] is True
    assert metrics["campaign_ready"] is True
