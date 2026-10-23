"""Tests for pure strategy calculations."""

from datetime import datetime, timezone
import pytest
from agent.strategy import (
    current_weight,
    decide,
    decision_hash,
    momentum_24h,
    pool_price,
    target_weight,
)


def test_momentum_24h() -> None:
    # 10% gain
    assert pytest.approx(momentum_24h([100.0, 105.0, 110.0]), 1e-6) == 0.10
    # 5% loss
    assert pytest.approx(momentum_24h([100.0, 95.0]), 1e-6) == -0.05
    # Flat
    assert pytest.approx(momentum_24h([100.0, 100.0]), 1e-6) == 0.0

    with pytest.raises(ValueError):
        momentum_24h([100.0])
    with pytest.raises(ValueError):
        momentum_24h([0.0, 100.0])


def test_target_weight_tilt_and_clamp() -> None:
    # Neutral momentum -> 0.50
    assert pytest.approx(target_weight(0.0), 1e-6) == 0.50
    # +5% momentum with tilt_k=3.0 -> 0.50 + 0.15 = 0.65
    assert pytest.approx(target_weight(0.05), 1e-6) == 0.65
    # -5% momentum with tilt_k=3.0 -> 0.50 - 0.15 = 0.35
    assert pytest.approx(target_weight(-0.05), 1e-6) == 0.35

    # Clamping at upper bound (0.70)
    assert pytest.approx(target_weight(0.20), 1e-6) == 0.70
    # Clamping at lower bound (0.30)
    assert pytest.approx(target_weight(-0.20), 1e-6) == 0.30


def test_pool_price_and_current_weight() -> None:
    # 10 WBNB and 4000 BUSD in pool -> 1 WBNB = 400 BUSD
    price = pool_price(10.0, 4000.0)
    assert pytest.approx(price, 1e-6) == 400.0

    # Portfolio: 0.5 WBNB (200 BUSD) + 200 BUSD -> 400 BUSD total -> 50%
    weight = current_weight(0.5, 200.0, price)
    assert pytest.approx(weight, 1e-6) == 0.50

    # Overweight WBNB: 1.0 WBNB (400 BUSD) + 100 BUSD -> 500 BUSD total -> 80%
    weight_over = current_weight(1.0, 100.0, price)
    assert pytest.approx(weight_over, 1e-6) == 0.80


def test_decide_within_band() -> None:
    # Momentum 0 -> target 0.50. Current weight 0.51 (drift 0.01 < band 0.03)
    state = {
        "wbnb_balance": 0.51,
        "busd_balance": 196.0,
        "reserve_wbnb": 10.0,
        "reserve_busd": 4000.0,  # price = 400
        "momentum": 0.0,
    }
    # Mid-day (12:00 UTC)
    now = datetime(2026, 10, 19, 12, 0, 0, tzinfo=timezone.utc)
    decision = decide(state, now)
    assert decision.action == "none"
    assert decision.amount_in == 0
    assert "within band" in decision.reason


def test_decide_drift_threshold_sell_wbnb() -> None:
    # Momentum 0 -> target 0.50.
    # WBNB = 1.0 (400 BUSD), BUSD = 200 BUSD -> total 600, current = 400/600 = 66.7%
    # drift = +16.7% >= band 3%
    state = {
        "wbnb_balance": 1.0,
        "busd_balance": 200.0,
        "reserve_wbnb": 10.0,
        "reserve_busd": 4000.0,
        "momentum": 0.0,
    }
    now = datetime(2026, 10, 19, 12, 0, 0, tzinfo=timezone.utc)
    decision = decide(state, now)
    assert decision.action == "sell_wbnb"
    assert decision.amount_in > 0
    assert "sell WBNB" in decision.reason

    # Enforce 50% max position limit
    assert decision.amount_in <= int(1.0 * 0.5 * 10**18)


def test_decide_drift_threshold_buy_wbnb() -> None:
    # Momentum 0 -> target 0.50.
    # WBNB = 0.2 (80 BUSD), BUSD = 400 BUSD -> total 480, current = 80/480 = 16.7%
    # drift = -33.3% -> buy WBNB (sell BUSD)
    state = {
        "wbnb_balance": 0.2,
        "busd_balance": 400.0,
        "reserve_wbnb": 10.0,
        "reserve_busd": 4000.0,
        "momentum": 0.0,
    }
    now = datetime(2026, 10, 19, 12, 0, 0, tzinfo=timezone.utc)
    decision = decide(state, now)
    assert decision.action == "buy_wbnb"
    assert decision.amount_in > 0
    assert "sell BUSD" in decision.reason
    assert decision.amount_in <= int(400.0 * 0.5 * 10**18)


def test_decide_daily_calendar_rebalance() -> None:
    # Drift = 0.015 (below standard band 0.03, but >= 0.005)
    # Hour is 19:00 UTC (>= 18), last_swap_day is yesterday
    price = 400.0
    # Target = 0.50. Current = 0.515
    # Total = 1000 BUSD. WBNB value = 515 BUSD (1.2875 WBNB), BUSD = 485
    state = {
        "wbnb_balance": 1.2875,
        "busd_balance": 485.0,
        "reserve_wbnb": 10.0,
        "reserve_busd": 4000.0,
        "momentum": 0.0,
    }

    # Case 1: After 18:00 UTC and no swap today -> triggers daily calendar rebalance
    now_after_18 = datetime(2026, 10, 19, 19, 0, 0, tzinfo=timezone.utc)
    d1 = decide(state, now_after_18, last_swap_day="2026-10-18")
    assert d1.action == "sell_wbnb"
    assert "daily calendar rebalance" in d1.reason

    # Case 2: Already swapped today -> should NOT trigger daily rule, stays "none"
    d2 = decide(state, now_after_18, last_swap_day="2026-10-19")
    assert d2.action == "none"

    # Case 3: Before 18:00 UTC -> should NOT trigger daily rule
    now_before_18 = datetime(2026, 10, 19, 14, 0, 0, tzinfo=timezone.utc)
    d3 = decide(state, now_before_18, last_swap_day="2026-10-18")
    assert d3.action == "none"


def test_decide_min_trade_busd() -> None:
    # Portfolio very small: 0.001 WBNB (0.4 BUSD) + 0.1 BUSD = 0.5 BUSD total.
    # Drift 10% -> trade value 0.05 BUSD < 0.5 BUSD min threshold
    state = {
        "wbnb_balance": 0.001,
        "busd_balance": 0.1,
        "reserve_wbnb": 10.0,
        "reserve_busd": 4000.0,
        "momentum": 0.0,
    }
    now = datetime(2026, 10, 19, 12, 0, 0, tzinfo=timezone.utc)
    d = decide(state, now)
    assert d.action == "none"
    assert "min threshold" in d.reason


def test_decision_hash_consistency() -> None:
    state = {
        "wbnb_balance": 1.0,
        "busd_balance": 200.0,
        "reserve_wbnb": 10.0,
        "reserve_busd": 4000.0,
        "momentum": 0.05,
    }
    now = datetime(2026, 10, 19, 12, 0, 0, tzinfo=timezone.utc)
    d1 = decide(state, now)
    d2 = decide(state, now)

    h1 = decision_hash(d1)
    h2 = decision_hash(d2)

    assert isinstance(h1, bytes)
    assert len(h1) == 32
    assert h1 == h2
