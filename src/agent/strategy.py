"""TiltBalance core strategy logic (pure calculations, zero network calls)."""

from dataclasses import dataclass
from datetime import datetime
import json
from typing import Any, Literal
from web3 import Web3

DEFAULT_BAND = 0.03
DEFAULT_MIN_TRADE_BUSD = 0.5


@dataclass(frozen=True)
class Decision:
    """Strategy rebalance decision container."""

    action: Literal["none", "sell_wbnb", "buy_wbnb"]
    amount_in: int  # Token atomic units (wei) to spend on the swap
    reason: str
    inputs: dict[str, Any]


def momentum_24h(closes: list[float]) -> float:
    """Calculate 24h momentum from hourly close prices.

    Requires at least 2 closes; computes (latest - oldest) / oldest.
    """
    if len(closes) < 2:
        raise ValueError(f"Need at least 2 prices to compute momentum, got {len(closes)}")
    if closes[0] <= 0:
        raise ValueError(f"Base price must be positive, got {closes[0]}")
    return (closes[-1] / closes[0]) - 1.0


def target_weight(
    momentum: float,
    tilt_k: float = 3.0,
    lo: float = 0.30,
    hi: float = 0.70,
) -> float:
    """Compute target WBNB portfolio weight tilted by momentum.

    Base weight is 0.5 (50/50). Tilts upward if BNB momentum is positive,
    downward if negative, clamped strictly between [lo, hi].
    """
    raw = 0.5 + (tilt_k * momentum)
    return max(lo, min(hi, raw))


def pool_price(reserve_wbnb: float, reserve_busd: float) -> float:
    """Calculate spot price of 1 WBNB in BUSD from DEX pool reserves."""
    if reserve_wbnb <= 0:
        raise ValueError(f"reserve_wbnb must be positive, got {reserve_wbnb}")
    if reserve_busd <= 0:
        raise ValueError(f"reserve_busd must be positive, got {reserve_busd}")
    return reserve_busd / reserve_wbnb


def current_weight(wbnb_val: float, busd_val: float, price: float) -> float:
    """Compute current WBNB portfolio weight by valuation."""
    wbnb_in_busd = wbnb_val * price
    total = wbnb_in_busd + busd_val
    if total <= 0:
        return 0.5
    return wbnb_in_busd / total


def decide(
    state: dict[str, Any],
    now_utc: datetime,
    last_swap_day: str | None = None,
    band: float = DEFAULT_BAND,
    min_trade_busd: float = DEFAULT_MIN_TRADE_BUSD,
) -> Decision:
    """Make rebalance decision from current portfolio state and market momentum.

    Args:
        state: Dict containing:
            wbnb_balance: float
            busd_balance: float
            reserve_wbnb: float
            reserve_busd: float
            momentum: float
            wbnb_decimals: int (default 18)
            busd_decimals: int (default 18)
        now_utc: Current UTC datetime.
        last_swap_day: Date string (YYYY-MM-DD) of the last executed swap, if any.
        band: Drift threshold for standard rebalancing (default: 0.03 = 3%).
        min_trade_busd: Minimum swap trade value in BUSD (default: 0.5 BUSD).

    Returns:
        Decision object with action, amount_in, reason, and canonical inputs.
    """
    wbnb_balance = float(state.get("wbnb_balance", 0.0))
    busd_balance = float(state.get("busd_balance", 0.0))
    reserve_wbnb = float(state["reserve_wbnb"])
    reserve_busd = float(state["reserve_busd"])
    momentum = float(state["momentum"])
    wbnb_decimals = int(state.get("wbnb_decimals", 18))
    busd_decimals = int(state.get("busd_decimals", 18))

    price = pool_price(reserve_wbnb, reserve_busd)
    target = target_weight(momentum)
    current = current_weight(wbnb_balance, busd_balance, price)
    drift = current - target
    total_value = (wbnb_balance * price) + busd_balance

    inputs: dict[str, Any] = {
        "momentum": round(momentum, 6),
        "target_weight": round(target, 6),
        "current_weight": round(current, 6),
        "drift": round(drift, 6),
        "price": round(price, 6),
        "wbnb_balance": round(wbnb_balance, 6),
        "busd_balance": round(busd_balance, 6),
        "total_value_busd": round(total_value, 4),
    }

    # Evaluate execution trigger
    today_str = now_utc.strftime("%Y-%m-%d")
    is_daily_eligible = (
        today_str != last_swap_day and now_utc.hour >= 18 and abs(drift) >= 0.005
    )

    if is_daily_eligible:
        reason_type = "daily calendar rebalance"
    elif abs(drift) >= band:
        reason_type = "drift threshold exceeded"
    else:
        return Decision(
            action="none",
            amount_in=0,
            reason="drift within band",
            inputs=inputs,
        )

    # Calculate trade value in BUSD
    trade_value_busd = total_value * abs(drift)
    if trade_value_busd < min_trade_busd:
        return Decision(
            action="none",
            amount_in=0,
            reason=f"trade value {trade_value_busd:.4f} BUSD < {min_trade_busd} min threshold",
            inputs=inputs,
        )

    # Determine action and enforce 50% max position liquidation limit
    if drift > 0:
        # WBNB overweight -> sell WBNB to buy BUSD
        raw_wbnb_to_sell = trade_value_busd / price
        max_sellable_wbnb = wbnb_balance * 0.5
        actual_wbnb = min(raw_wbnb_to_sell, max_sellable_wbnb)
        amount_in = int(actual_wbnb * (10**wbnb_decimals))
        reason = f"{reason_type}: drift +{drift:.4f} > 0, sell WBNB"
        return Decision(
            action="sell_wbnb",
            amount_in=amount_in,
            reason=reason,
            inputs=inputs,
        )
    else:
        # BUSD overweight -> sell BUSD to buy WBNB
        raw_busd_to_sell = trade_value_busd
        max_sellable_busd = busd_balance * 0.5
        actual_busd = min(raw_busd_to_sell, max_sellable_busd)
        amount_in = int(actual_busd * (10**busd_decimals))
        reason = f"{reason_type}: drift {drift:.4f} < 0, sell BUSD to buy WBNB"
        return Decision(
            action="buy_wbnb",
            amount_in=amount_in,
            reason=reason,
            inputs=inputs,
        )


def decision_hash(decision: Decision) -> bytes:
    """Compute keccak256 hash over canonical JSON of the decision.

    The hash is exactly 32 bytes and can be attached to swap calldata.
    """
    canonical_dict = {
        "action": decision.action,
        "amount_in": decision.amount_in,
        "inputs": decision.inputs,
    }
    canonical_json = json.dumps(canonical_dict, sort_keys=True, separators=(",", ":"))
    return bytes(Web3.keccak(text=canonical_json))
