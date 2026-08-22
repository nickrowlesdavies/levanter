#!/usr/bin/env python3
"""
Run a full backtest across all configured instruments.

    python run_backtest.py               # uses config.yaml
    python run_backtest.py --refresh     # ignore cache, re-download data

For every instrument it prints an in-sample and out-of-sample scorecard,
then a portfolio-level summary. Out-of-sample is the number that matters:
it is data the strategy parameters were never chosen against.
"""
from __future__ import annotations

import argparse
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import yaml

from src.data.loader import Instrument, load_candles
from src.signals.registry import STRATEGIES
from src.backtest.engine import run_backtest
from src.backtest.metrics import compute_metrics, format_report


def load_config(path: str = "config.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--refresh", action="store_true", help="ignore data cache")
    args = ap.parse_args()

    cfg = load_config(args.config)
    acct = cfg["account"]
    dcfg = cfg["data"]
    scfg = cfg["strategy"]
    oos_start = pd.Timestamp(cfg["backtest"]["out_of_sample_start"])

    strat_cls = STRATEGIES[scfg["name"]]
    strategy = strat_cls(**scfg["params"])

    print(f"\nStrategy: {scfg['name']}  params={scfg['params']}")
    print(f"Data: {dcfg['start']} -> {dcfg['end']} ({dcfg['interval']}), "
          f"risk {acct['risk_per_trade_pct']}%/trade, "
          f"OOS from {oos_start.date()}\n")
    print("IN-SAMPLE (params chosen here - treat with suspicion):")

    portfolio_is, portfolio_oos = [], []
    curves = {}

    for i in cfg["instruments"]:
        inst = Instrument(i["name"], i["symbol"], i["pip"], i["spread_pips"])
        df = load_candles(
            inst, dcfg["start"], dcfg["end"], dcfg["interval"],
            dcfg["cache_dir"], use_cache=not args.refresh,
        )
        sig = strategy.generate(df)

        is_mask = df.index < oos_start
        oos_mask = df.index >= oos_start

        res_is = run_backtest(df[is_mask], sig[is_mask], inst,
                              acct["starting_equity"], acct["risk_per_trade_pct"])
        m_is = compute_metrics(res_is.equity_curve, res_is.trades,
                               acct["starting_equity"], acct["risk_per_trade_pct"])
        print(format_report(inst.name, m_is))
        portfolio_is.append(m_is)

        # Out-of-sample restarts equity so the score is clean.
        res_oos = run_backtest(df[oos_mask], sig[oos_mask], inst,
                               acct["starting_equity"], acct["risk_per_trade_pct"])
        m_oos = compute_metrics(res_oos.equity_curve, res_oos.trades,
                                acct["starting_equity"], acct["risk_per_trade_pct"])
        portfolio_oos.append((inst.name, m_oos))
        curves[inst.name] = res_oos.equity_curve

        # Save the per-instrument trade blotter for inspection.
        os.makedirs("reports", exist_ok=True)
        res_oos.blotter().to_csv(f"reports/{inst.name}_oos_trades.csv", index=False)

    print("\nOUT-OF-SAMPLE (the honest score):")
    for name, m in portfolio_oos:
        print(format_report(name, m))

    # Simple equal-weight portfolio expectancy summary (OOS).
    total_trades = sum(m["num_trades"] for _, m in portfolio_oos)
    exp = [m["expectancy_R"] for _, m in portfolio_oos if m["expectancy_R"] == m["expectancy_R"]]
    avg_exp = sum(exp) / len(exp) if exp else float("nan")
    print(f"\n  PORTFOLIO OOS: {total_trades} trades, "
          f"avg expectancy {avg_exp:.3f}R across pairs")
    print("  (>0R after costs = the strategy has a measurable edge to keep testing.)")

    # Plot out-of-sample equity curves.
    plt.figure(figsize=(11, 6))
    for name, curve in curves.items():
        norm = curve / curve.iloc[0] * 100
        plt.plot(norm.index, norm.values, label=name, linewidth=1.3)
    plt.axhline(100, color="grey", linestyle="--", linewidth=0.8)
    plt.title(f"Out-of-sample equity curves ({scfg['name']}) - start=100")
    plt.ylabel("Equity (indexed to 100)")
    plt.legend()
    plt.tight_layout()
    out_png = "reports/oos_equity_curves.png"
    plt.savefig(out_png, dpi=130)
    print(f"\n  Chart saved: {out_png}")
    print("  Trade blotters saved: reports/<PAIR>_oos_trades.csv\n")


if __name__ == "__main__":
    main()
