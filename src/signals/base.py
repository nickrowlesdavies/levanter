"""
Strategy interface.

A strategy takes a price DataFrame and returns, for every bar, everything
the backtester needs to act WITHOUT looking into the future:

    signal      : +1 (go long), -1 (go short), 0 (no entry)
    stop        : suggested stop-loss price for a new entry (NaN if no signal)
    target      : suggested take-profit price for a new entry (NaN if no signal)

Critically: the value on row t must be computable from data up to and
including row t only. The backtester then acts on the NEXT bar's open, so
there is no lookahead. Any new strategy just subclasses Strategy.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np
import pandas as pd


def atr_output(df: pd.DataFrame, signal: pd.Series, atr: pd.Series,
               stop_mult: float, target_mult: float,
               warmup: int = 0) -> pd.DataFrame:
    """Turn an entry signal + ATR into the (signal, stop, target) frame every
    strategy returns. Long stops below / target above; short the mirror. This
    keeps risk management identical across strategies so a comparison isolates
    the ENTRY edge, not the exit rules."""
    close = df["close"]
    long, short = signal == 1, signal == -1

    stop = pd.Series(np.nan, index=df.index)
    target = pd.Series(np.nan, index=df.index)
    stop[long] = close[long] - stop_mult * atr[long]
    target[long] = close[long] + target_mult * atr[long]
    stop[short] = close[short] + stop_mult * atr[short]
    target[short] = close[short] - target_mult * atr[short]

    out = pd.DataFrame({"signal": signal.astype(int), "stop": stop,
                        "target": target}, index=df.index)
    if warmup > 0:
        out.iloc[:warmup] = pd.DataFrame(
            {"signal": 0, "stop": np.nan, "target": np.nan},
            index=out.index[:warmup])
    return out


class Strategy(ABC):
    name: str = "base"

    def __init__(self, **params):
        self.params = params

    @abstractmethod
    def generate(self, df: pd.DataFrame) -> pd.DataFrame:
        """Return a DataFrame aligned to df.index with columns:
        signal, stop, target."""
        raise NotImplementedError
