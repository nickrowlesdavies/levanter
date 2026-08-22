"""
Moving-average crossover (classic trend-following).

Entry: fast SMA crosses above slow SMA -> long; crosses below -> short.
A pure trend model, different mechanism from the breakout. ATR stop/target.
"""
from __future__ import annotations

import pandas as pd

from .base import Strategy, atr_output
from .indicators import sma, atr


class MaCrossover(Strategy):
    name = "ma_crossover"

    def generate(self, df: pd.DataFrame) -> pd.DataFrame:
        p = self.params
        fast = int(p.get("fast", 20))
        slow = int(p.get("slow", 50))
        atr_period = int(p.get("atr_period", 14))

        close = df["close"]
        f, s = sma(close, fast), sma(close, slow)
        cross_up = (f > s) & (f.shift(1) <= s.shift(1))
        cross_dn = (f < s) & (f.shift(1) >= s.shift(1))

        signal = pd.Series(0, index=df.index, dtype=int)
        signal[cross_up] = 1
        signal[cross_dn] = -1

        warmup = max(fast, slow, atr_period)
        return atr_output(df, signal, atr(df, atr_period),
                          float(p.get("atr_stop_mult", 2.0)),
                          float(p.get("atr_target_mult", 3.0)), warmup)
