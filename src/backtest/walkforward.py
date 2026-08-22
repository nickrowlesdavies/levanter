"""
Walk-forward analysis - the honest way to judge a strategy.

The trap in backtesting: pick the parameters that looked best over all
history, then quote that history's return. That number is fiction - you
could only have chosen those parameters with hindsight.

Walk-forward fixes it. Roll through time in windows:
    [--- train ---][- test -]
                   [--- train ---][- test -]
                                  [--- train ---][- test -]
On each step, optimise parameters ONLY on the train slice, then trade the
next (unseen) test slice with those fixed parameters. Stitch all the test
slices together. The stitched curve is money you could actually have made,
because every parameter choice used only prior data.

Signals are precomputed on the full series (indicators are causal, so this
leaks nothing) and then sliced per window - which also removes the warm-up
gap at each window's start.
"""
from __future__ import annotations

from itertools import product
from typing import Dict, List

import numpy as np
import pandas as pd
from pandas.tseries.offsets import DateOffset

from ..data.loader import Instrument
from .engine import run_backtest
from .metrics import compute_metrics


def param_combos(grid: Dict[str, list]) -> List[dict]:
    keys = list(grid)
    return [dict(zip(keys, vals)) for vals in product(*[grid[k] for k in keys])]


def _windows(index, train_years, test_years, step_years):
    start, end = index[0], index[-1]
    out = []
    train_start = start
    while True:
        train_end = train_start + DateOffset(years=train_years)
        test_end = train_end + DateOffset(years=test_years)
        if train_end >= end:
            break
        out.append((train_start, train_end, min(test_end, end)))
        if test_end >= end:
            break
        train_start = train_start + DateOffset(years=step_years)
    return out


def walk_forward(
    df: pd.DataFrame,
    strategy_cls,
    grid: Dict[str, list],
    inst: Instrument,
    start_equity: float,
    risk_pct: float,
    train_years: int = 4,
    test_years: int = 2,
    step_years: int = 2,
    select: str = "sharpe",
    min_train_trades: int = 5,
    carry_annual: "pd.Series | None" = None,
) -> dict:
    """Run walk-forward for one strategy on one instrument.

    Returns stitched out-of-sample curve, trades, per-window param choices,
    and honest OOS metrics computed on the stitched result.
    """
    combos = param_combos(grid)
    # Precompute signals once per param combo (causal -> safe to slice later).
    precomputed = {i: strategy_cls(**c).generate(df) for i, c in enumerate(combos)}

    windows = _windows(df.index, train_years, test_years, step_years)
    equity = start_equity
    stitched_points: List[tuple] = []
    all_oos_trades = []
    choices = []

    for tr_s, tr_e, te_e in windows:
        train_mask = (df.index >= tr_s) & (df.index < tr_e)
        test_mask = (df.index >= tr_e) & (df.index < te_e)
        train_df, test_df = df[train_mask], df[test_mask]
        if len(train_df) < 60 or len(test_df) < 20:
            continue

        # --- optimise on train only ---
        best_i, best_score = None, -np.inf
        for i, _c in enumerate(combos):
            res = run_backtest(train_df, precomputed[i][train_mask], inst,
                               start_equity, risk_pct, carry_annual=carry_annual)
            if len(res.trades) < min_train_trades:
                continue
            m = compute_metrics(res.equity_curve, res.trades, start_equity, risk_pct)
            score = m.get(select, np.nan)
            if score == score and score > best_score:  # not-nan and better
                best_score, best_i = score, i
        if best_i is None:
            continue

        # --- trade the unseen test slice with the chosen params ---
        res = run_backtest(test_df, precomputed[best_i][test_mask], inst,
                           equity, risk_pct, carry_annual=carry_annual)
        seg = res.equity_curve
        stitched_points.extend(list(zip(seg.index, seg.values)))
        all_oos_trades.extend(res.trades)
        equity = float(seg.iloc[-1]) if len(seg) else equity
        choices.append({"test_start": str(tr_e.date()), "params": combos[best_i],
                        "end_equity": round(equity, 2), "trades": len(res.trades)})

    if not stitched_points:
        return {"curve": pd.Series(dtype=float), "trades": [], "choices": [],
                "metrics": {"num_trades": 0}}

    curve = pd.Series([e for _, e in stitched_points],
                      index=pd.DatetimeIndex([d for d, _ in stitched_points]))
    curve = curve[~curve.index.duplicated(keep="last")].sort_index()
    metrics = compute_metrics(curve, all_oos_trades, start_equity, risk_pct)
    return {"curve": curve, "trades": all_oos_trades,
            "choices": choices, "metrics": metrics}
