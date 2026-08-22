"""Central strategy registry: name -> Strategy class."""
from __future__ import annotations

from .trend_breakout import TrendBreakout
from .ma_crossover import MaCrossover
from .momentum import Momentum
from .mean_reversion import MeanReversion
from .carry import Carry

ALL_STRATEGIES = {
    c.name: c
    for c in (TrendBreakout, MaCrossover, Momentum, MeanReversion, Carry)
}

# Back-compat alias used by earlier modules.
STRATEGIES = ALL_STRATEGIES
