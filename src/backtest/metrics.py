"""
Performance metrics - the honest scorecard.

Given an equity curve and a trade blotter, compute the numbers that
actually tell you whether there is an edge, net of costs:

  * Total return %, CAGR
  * Sharpe (annualised, on daily equity changes)
  * Max drawdown %
  * Win rate, average win/loss, expectancy per trade (in R multiples)
  * Profit factor, number of trades

R multiple = trade pnl / money risked on that trade. Expectancy in R is
the single most useful "is this worth trading" number.
"""
from __future__ import annotations

from typing import List

import numpy as np
import pandas as pd

from .engine import Trade

TRADING_DAYS = 252


def _max_drawdown(curve: pd.Series) -> float:
    running_max = curve.cummax()
    dd = (curve - running_max) / running_max
    return float(dd.min())  # negative number, e.g. -0.18


def compute_metrics(
    curve: pd.Series,
    trades: List[Trade],
    starting_equity: float,
    risk_pct: float,
) -> dict:
    out: dict = {}

    total_return = curve.iloc[-1] / starting_equity - 1.0
    n_days = max((curve.index[-1] - curve.index[0]).days, 1)
    years = n_days / 365.25
    cagr = (curve.iloc[-1] / starting_equity) ** (1 / years) - 1 if years > 0 else np.nan

    daily = curve.resample("1D").last().ffill()
    rets = daily.pct_change().dropna()
    sharpe = (
        np.sqrt(TRADING_DAYS) * rets.mean() / rets.std()
        if rets.std() > 0
        else np.nan
    )

    out["final_equity"] = float(curve.iloc[-1])
    out["total_return_pct"] = float(total_return * 100)
    out["cagr_pct"] = float(cagr * 100) if cagr == cagr else float("nan")
    out["sharpe"] = float(sharpe) if sharpe == sharpe else float("nan")
    out["max_drawdown_pct"] = float(_max_drawdown(curve) * 100)

    n = len(trades)
    out["num_trades"] = n
    if n == 0:
        out.update(
            win_rate_pct=float("nan"), profit_factor=float("nan"),
            expectancy_R=float("nan"), avg_win=float("nan"), avg_loss=float("nan"),
        )
        return out

    pnls = np.array([t.pnl for t in trades])
    wins = pnls[pnls > 0]
    losses = pnls[pnls < 0]

    out["win_rate_pct"] = float(len(wins) / n * 100)
    out["avg_win"] = float(wins.mean()) if len(wins) else 0.0
    out["avg_loss"] = float(losses.mean()) if len(losses) else 0.0
    gross_win = wins.sum()
    gross_loss = -losses.sum()
    out["profit_factor"] = float(gross_win / gross_loss) if gross_loss > 0 else float("inf")

    # Expectancy in R: pnl divided by money risked on each trade.
    r_multiples = []
    for t in trades:
        risked = abs(t.entry_price - t.stop) * t.units
        if risked > 0:
            r_multiples.append(t.pnl / risked)
    out["expectancy_R"] = float(np.mean(r_multiples)) if r_multiples else float("nan")
    return out


def format_report(name: str, m: dict) -> str:
    def g(k, fmt="{:.2f}"):
        v = m.get(k, float("nan"))
        return fmt.format(v) if v == v else "n/a"

    return (
        f"  {name:<8} | trades {m.get('num_trades',0):>4} | "
        f"ret {g('total_return_pct'):>7}% | CAGR {g('cagr_pct'):>6}% | "
        f"Sharpe {g('sharpe'):>5} | maxDD {g('max_drawdown_pct'):>7}% | "
        f"win {g('win_rate_pct'):>5}% | PF {g('profit_factor'):>4} | "
        f"exp {g('expectancy_R'):>5}R"
    )
