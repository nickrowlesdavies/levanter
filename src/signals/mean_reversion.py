"""
Mean reversion (RSI + Bollinger). Counter-trend.

Entry: price closes below the lower Bollinger band AND RSI is oversold ->
long (bet on a bounce); above the upper band AND RSI overbought -> short.
Targets are typically closer (revert to the mean), so the default
target multiple is smaller than the trend strategies'. ATR stop/target.
"""
from __future__ import annotations

import pandas as pd

from .base import Strategy, atr_output
from .indicators import atr, rsi, bollinger


class MeanReversion(Strategy):
    name = "mean_reversion"

    def generate(self, df: pd.DataFrame) -> pd.DataFrame:
        p = self.params
        bb_period = int(p.get("bb_period", 20))
        bb_std = float(p.get("bb_std", 2.0))
        rsi_period = int(p.get("rsi_period", 14))
        rsi_low = float(p.get("rsi_low", 30))
        rsi_high = float(p.get("rsi_high", 70))
        atr_period = int(p.get("atr_period", 14))

        close = df["close"]
        _, upper, lower = bollinger(close, bb_period, bb_std)
        r = rsi(close, rsi_period)

        signal = pd.Series(0, index=df.index, dtype=int)
        signal[(close < lower) & (r < rsi_low)] = 1
        signal[(close > upper) & (r > rsi_high)] = -1

        warmup = max(bb_period, rsi_period, atr_period)
        return atr_output(df, signal, atr(df, atr_period),
                          float(p.get("atr_stop_mult", 2.0)),
                          float(p.get("atr_target_mult", 1.5)), warmup)
