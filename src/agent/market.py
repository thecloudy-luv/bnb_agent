"""Market data fetcher for BNB prices via Binance Vision API."""

import logging
from typing import Any
import httpx

logger = logging.getLogger(__name__)

BINANCE_VISION_KLINES_URL = "https://data-api.binance.vision/api/v3/klines"


class MarketDataError(Exception):
    """Raised when market data retrieval or parsing fails."""


def fetch_bnb_closes(hours: int = 25, timeout_sec: float = 10.0) -> list[float]:
    """Fetch hourly close prices for BNBUSDT from Binance Vision public API.

    Args:
        hours: Number of hourly candles to retrieve (default: 25, covering 24 hourly changes).
        timeout_sec: Request timeout in seconds.

    Returns:
        List of hourly close prices as floats in chronological order.

    Raises:
        MarketDataError: If network request fails, status code != 200, or payload is invalid.
    """
    params: dict[str, Any] = {
        "symbol": "BNBUSDT",
        "interval": "1h",
        "limit": hours,
    }

    try:
        with httpx.Client(timeout=timeout_sec) as client:
            resp = client.get(BINANCE_VISION_KLINES_URL, params=params)
    except Exception as exc:
        logger.error("Failed to connect to Binance Vision API: %s", exc)
        raise MarketDataError(f"Network error fetching BNB market data: {exc}") from exc

    if resp.status_code != 200:
        logger.error("Binance Vision returned status %d: %s", resp.status_code, resp.text)
        raise MarketDataError(
            f"Binance Vision API returned HTTP {resp.status_code}: {resp.text[:200]}"
        )

    try:
        data = resp.json()
        if not isinstance(data, list) or len(data) == 0:
            raise ValueError(f"Expected non-empty list of candles, got {type(data)}")

        # Binance klines format: [open_time, open, high, low, close, volume, ...]
        closes: list[float] = [float(candle[4]) for candle in data]
        if len(closes) < 2:
            raise ValueError(f"Insufficient candle count: {len(closes)}")
        return closes
    except Exception as exc:
        logger.error("Failed to parse candle data: %s", exc)
        raise MarketDataError(f"Failed to parse Binance kline data: {exc}") from exc
