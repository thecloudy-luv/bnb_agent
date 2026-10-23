"""Tests for BNB market data retrieval from Binance Vision API."""

from unittest.mock import MagicMock, patch
import httpx
import pytest
from agent.market import MarketDataError, fetch_bnb_closes


def test_fetch_bnb_closes_success() -> None:
    # 3 hourly candles: index 4 is the close price string
    mock_candles = [
        [1600000000000, "600.0", "610.0", "595.0", "605.0", "1000", ...],
        [1600003600000, "605.0", "615.0", "602.0", "610.0", "1200", ...],
        [1600007200000, "610.0", "620.0", "608.0", "618.5", "1100", ...],
    ]

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_candles

    with patch("httpx.Client.get", return_value=mock_resp):
        closes = fetch_bnb_closes(hours=3)
        assert len(closes) == 3
        assert closes == [605.0, 610.0, 618.5]


def test_fetch_bnb_closes_http_error() -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.text = "Internal Server Error"

    with patch("httpx.Client.get", return_value=mock_resp):
        with pytest.raises(MarketDataError, match="HTTP 500"):
            fetch_bnb_closes()


def test_fetch_bnb_closes_network_error() -> None:
    with patch("httpx.Client.get", side_effect=httpx.ConnectTimeout("Connection timed out")):
        with pytest.raises(MarketDataError, match="Network error"):
            fetch_bnb_closes()


def test_fetch_bnb_closes_invalid_payload() -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"error": "unexpected object"}

    with patch("httpx.Client.get", return_value=mock_resp):
        with pytest.raises(MarketDataError, match="Failed to parse"):
            fetch_bnb_closes()
