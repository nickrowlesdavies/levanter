"""
Shared technical indicators.

One vetted implementation each, so every strategy computes ATR/RSI/etc the
same way and comparisons stay apples-to-apples. All are causal: value at
bar t uses only data up to bar t.
"""
from __future__ import annotations

import pandas as pd


def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(period).mean()


def atr(df: pd.DataFrame, period: int) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr.rolling(period).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's RSI."""
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0.0, float("nan"))
    return 100 - (100 / (1 + rs))


def roc(series: pd.Series, period: int) -> pd.Series:
    """Rate of change over `period` bars (fractional, e.g. 0.02 = +2%)."""
    return series.pct_change(period)


def bollinger(series: pd.Series, period: int = 20, num_std: float = 2.0):
    """Return (mid, upper, lower) Bollinger bands."""
    mid = series.rolling(period).mean()
    sd = series.rolling(period).std()
    return mid, mid + num_std * sd, mid - num_std * sd
