"""
Carry (+ trend filter). The one FX factor with real evidence.

Entry: if being long the pair earns a large enough interest differential
(carry > threshold) go long; if being short earns it (carry < -threshold)
go short. A trend filter is applied by default so we only hold the carry
when price agrees - the classic protection against carry "crashes", where
high-yielders unwind violently in risk-off episodes.

This strategy needs a `carry` column on the price frame (annualised % for
being long the pair), supplied by src.data.rates.carry_for_pair. The roll
itself (earning/paying the differential) is modelled in the backtest engine,
so this strategy only has to decide direction.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .base import Strategy, atr_output
from .indicators import sma, atr


class Carry(Strategy):
    name = "carry"

    def generate(self, df: pd.DataFrame) -> pd.DataFrame:
        p = self.params
        threshold = float(p.get("carry_threshold", 0.5))   # annual % differential
        use_trend = bool(p.get("use_trend_filter", True))
        trend_ma = int(p.get("trend_ma", 100))
        atr_period = int(p.get("atr_period", 14))

        if "carry" not in df.columns:
            # No carry data -> no trades (keeps the pipeline safe).
            return atr_output(df, pd.Series(0, index=df.index, dtype=int),
                              atr(df, atr_period), 2.0, 3.0, len(df))

        carry = df["carry"]
        close = df["close"]
        trend = sma(close, trend_ma)

        long_ok = carry > threshold
        short_ok = carry < -threshold
        if use_trend:
            long_ok &= close > trend
            short_ok &= close < trend

        signal = pd.Series(0, index=df.index, dtype=int)
        signal[long_ok] = 1
        signal[short_ok] = -1

        warmup = max(trend_ma, atr_period) if use_trend else atr_period
        return atr_output(df, signal, atr(df, atr_period),
                          float(p.get("atr_stop_mult", 2.0)),
                          float(p.get("atr_target_mult", 4.0)), warmup)
