"""
Time-series momentum.

Entry: if price return over `lookback` bars exceeds +threshold and price is
above its trend filter -> long; below -threshold and below trend -> short.
Bets that recent strength persists. ATR stop/target.
"""
from __future__ import annotations

import pandas as pd

from .base import Strategy, atr_output
from .indicators import sma, atr, roc


class Momentum(Strategy):
    name = "momentum"

    def generate(self, df: pd.DataFrame) -> pd.DataFrame:
        p = self.params
        lookback = int(p.get("lookback", 60))
        threshold = float(p.get("threshold", 0.02))   # 2% move
        trend_ma = int(p.get("trend_ma", 100))
        atr_period = int(p.get("atr_period", 14))

        close = df["close"]
        r = roc(close, lookback)
        trend = sma(close, trend_ma)

        signal = pd.Series(0, index=df.index, dtype=int)
        signal[(r > threshold) & (close > trend)] = 1
        signal[(r < -threshold) & (close < trend)] = -1

        warmup = max(lookback, trend_ma, atr_period)
        return atr_output(df, signal, atr(df, atr_period),
                          float(p.get("atr_stop_mult", 2.0)),
                          float(p.get("atr_target_mult", 3.0)), warmup)
