"""
Position sizing and risk rules.

Risk-based sizing: we risk a fixed % of current equity on the distance
between entry and stop. This keeps every trade's downside roughly equal in
money terms regardless of how wide the stop is - the single most important
discipline in staying alive.

    risk_amount = equity * risk_per_trade_pct / 100
    units       = risk_amount / stop_distance_in_price

P&L is then units * price_move, which for FX quoted in the account currency
(e.g. *USD pairs for a USD account) is a clean approximation. Cross-currency
conversion nuances are deferred until a live broker is wired.
"""
from __future__ import annotations


def position_size(equity: float, risk_pct: float, entry: float, stop: float) -> float:
    """Return position size in units. Zero if the stop is invalid."""
    stop_distance = abs(entry - stop)
    if stop_distance <= 0:
        return 0.0
    risk_amount = equity * (risk_pct / 100.0)
    return risk_amount / stop_distance
