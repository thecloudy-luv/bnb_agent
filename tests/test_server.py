"""Tests for FastAPI server endpoints."""

import pytest
from fastapi.testclient import TestClient
from agent.server import app


@pytest.fixture
def client() -> TestClient:
    """Fixture providing a FastAPI TestClient."""
    return TestClient(app)


def test_health_default(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify /health returns expected default response."""
    monkeypatch.delenv("CHAIN_ID", raising=False)
    monkeypatch.delenv("RUN_LOOPS", raising=False)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "chain_id": 97,
        "loops_enabled": False,
    }


def test_health_loops_enabled(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify /health reflects loops_enabled when RUN_LOOPS is 1."""
    monkeypatch.setenv("RUN_LOOPS", "1")
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "chain_id": 97,
        "loops_enabled": True,
    }


def test_get_logo(client: TestClient) -> None:
    """Verify /logo.png returns 200 with image/png media type."""
    response = client.get("/logo.png")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert len(response.content) > 100


def test_status_endpoint(client: TestClient) -> None:
    """Verify /status returns expected keys including jobs and recent_logs."""
    response = client.get("/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert "wallet" in data
    assert "loops_enabled" in data
    assert "target_weight" in data
    assert "current_weight" in data
    assert "drift" in data
    assert "recent_logs" in data
    assert "jobs" in data
    assert isinstance(data["jobs"], list)

