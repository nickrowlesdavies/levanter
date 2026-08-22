"""
Trend-following breakout (Donchian + trend filter). Baseline strategy.

Entry: close makes a new `breakout_lookback`-bar high (long) or low (short),
only in the direction of the SMA(trend_ma) trend. ATR-based stop/target.
"""
from __future__ import annotations

import pandas as pd

from .base import Strategy, atr_output
from .indicators import sma, atr


class TrendBreakout(Strategy):
    name = "trend_breakout"

    def generate(self, df: pd.DataFrame) -> pd.DataFrame:
        p = self.params
        trend_ma = int(p.get("trend_ma", 100))
        lookback = int(p.get("breakout_lookback", 20))
        atr_period = int(p.get("atr_period", 14))

        close = df["close"]
        trend = sma(close, trend_ma)
        a = atr(df, atr_period)
        upper = close.rolling(lookback).max().shift(1)
        lower = close.rolling(lookback).min().shift(1)

        signal = pd.Series(0, index=df.index, dtype=int)
        signal[(close > upper) & (close > trend)] = 1
        signal[(close < lower) & (close < trend)] = -1

        warmup = max(trend_ma, lookback, atr_period)
        return atr_output(df, signal, a,
                          float(p.get("atr_stop_mult", 2.0)),
                          float(p.get("atr_target_mult", 3.0)), warmup)
