"""
Forward paper-trading loop - the "trial".

This is the backtester's logic run incrementally on live-updating data,
with account state persisted to disk so it survives restarts. Each cycle:

  1. Pull recent completed candles for every instrument.
  2. Manage any open position: if a later bar's high/low breached the stop
     or target, close it there (same conservative rule as the backtest).
  3. If flat and the newest completed bar fires a signal, open a paper
     position and surface it as a RECOMMENDED TRADE (entry/stop/target/size).
  4. Mark the account to market (live OANDA price if available, else close).
  5. Persist state; append actions to a CSV log.

It books trades into a SIMULATED account only. It never sends a real order.
Works on either data source: yfinance (test today, no token) or OANDA
(live practice prices once your token is set).
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import datetime, timedelta
from typing import List, Optional

import pandas as pd

from ..data.loader import Instrument, load_candles
from ..signals.registry import STRATEGIES
from ..risk.sizing import position_size

# Generous calendar lookback per interval so indicators (e.g. MA100) warm up.
_LOOKBACK_DAYS = {"1d": 600, "4h": 160, "1h": 70, "30m": 40, "15m": 25}


def _now() -> datetime:
    return datetime.utcnow()


class PaperTrader:
    def __init__(self, cfg: dict, state_path: str = "reports/paper_state.json",
                 log_path: str = "reports/paper_log.csv"):
        self.cfg = cfg
        self.state_path = state_path
        self.log_path = log_path

        acct = cfg["account"]
        self.starting_equity = float(acct["starting_equity"])
        self.risk_pct = float(acct["risk_per_trade_pct"])

        scfg = cfg["strategy"]
        self.strategy = STRATEGIES[scfg["name"]](**scfg["params"])

        self.instruments = [
            Instrument(i["name"], i["symbol"], i["pip"], i["spread_pips"])
            for i in cfg["instruments"]
        ]
        self.source = cfg["data"].get("source", "yfinance")
        self.environment = cfg["data"].get("environment", "practice")
        self.interval = cfg["data"].get("interval", "1d")

        self.state = self._load_state()

    # ---- state -------------------------------------------------------
    def _load_state(self) -> dict:
        if os.path.exists(self.state_path):
            with open(self.state_path) as f:
                return json.load(f)
        return {
            "starting_equity": self.starting_equity,
            "realized_equity": self.starting_equity,   # cash after closed trades
            "open_positions": {},                      # name -> position dict
            "closed_trades": [],
            "last_bar_seen": {},                       # name -> iso timestamp
            "created": _now().isoformat(),
            "updated": _now().isoformat(),
        }

    def _save_state(self):
        os.makedirs(os.path.dirname(self.state_path), exist_ok=True)
        self.state["updated"] = _now().isoformat()
        with open(self.state_path, "w") as f:
            json.dump(self.state, f, indent=2, default=str)

    def _log(self, rows: List[dict]):
        if not rows:
            return
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
        df = pd.DataFrame(rows)
        header = not os.path.exists(self.log_path)
        df.to_csv(self.log_path, mode="a", header=header, index=False)

    # ---- data helpers ------------------------------------------------
    def _recent_candles(self, inst: Instrument) -> pd.DataFrame:
        lookback = _LOOKBACK_DAYS.get(self.interval, 600)
        start = (_now() - timedelta(days=lookback)).strftime("%Y-%m-%d")
        end = (_now() + timedelta(days=1)).strftime("%Y-%m-%d")
        return load_candles(
            inst, start, end, self.interval,
            cache_dir=self.cfg["data"]["cache_dir"],
            use_cache=False,               # live data must be fresh
            source=self.source, environment=self.environment,
        )

    def _mark(self, name: str) -> Optional[float]:
        """Latest known price for marking to market. Uses the last candle
        close cached during run_cycle - no extra API calls, works on any
        data source (keeps us well inside free-tier rate limits)."""
        return self.state.get("last_close", {}).get(name)

    # ---- core cycle --------------------------------------------------
    def run_cycle(self) -> List[dict]:
        actions: List[dict] = []
        for inst in self.instruments:
            try:
                df = self._recent_candles(inst)
            except Exception as e:
                actions.append(self._action(inst, "data_error", note=str(e)[:120]))
                continue
            if df is None or len(df) < 2:
                continue
            sig = self.strategy.generate(df)
            actions += self._manage_open(inst, df)
            actions += self._maybe_enter(inst, df, sig)
            self.state["last_bar_seen"][inst.name] = str(df.index[-1])
            # Cache the latest close for quota-friendly mark-to-market.
            self.state.setdefault("last_close", {})[inst.name] = float(
                df["close"].iloc[-1]
            )

        self._save_state()
        self._log(actions)
        return actions

    def _half_spread(self, inst: Instrument) -> float:
        return (inst.spread_pips * inst.pip) / 2.0

    def _manage_open(self, inst: Instrument, df: pd.DataFrame) -> List[dict]:
        pos = self.state["open_positions"].get(inst.name)
        if not pos:
            return []
        entry_time = pd.Timestamp(pos["entry_time"])
        future = df[df.index > entry_time]
        d = int(pos["direction"])
        hs = self._half_spread(inst)

        for ts, bar in future.iterrows():
            hit = px = None
            if d == 1:
                if bar["low"] <= pos["stop"]:
                    hit, px = "stop", pos["stop"]
                elif bar["high"] >= pos["target"]:
                    hit, px = "target", pos["target"]
            else:
                if bar["high"] >= pos["stop"]:
                    hit, px = "stop", pos["stop"]
                elif bar["low"] <= pos["target"]:
                    hit, px = "target", pos["target"]
            if hit:
                fill = px - d * hs
                pnl = d * (fill - pos["entry_price"]) * pos["units"]
                self.state["realized_equity"] += pnl
                risked = abs(pos["entry_price"] - pos["stop"]) * pos["units"]
                trade = {
                    **pos, "exit_time": str(ts), "exit_price": fill,
                    "reason": hit, "pnl": pnl,
                    "R": (pnl / risked) if risked else 0.0,
                }
                self.state["closed_trades"].append(trade)
                del self.state["open_positions"][inst.name]
                return [self._action(
                    inst, f"CLOSE_{hit.upper()}", price=fill, pnl=pnl,
                    note=f"{'LONG' if d==1 else 'SHORT'} closed, R={trade['R']:.2f}")]
        return []

    def _maybe_enter(self, inst: Instrument, df: pd.DataFrame,
                     sig: pd.DataFrame) -> List[dict]:
        if inst.name in self.state["open_positions"]:
            return []
        latest = df.index[-1]
        # Only act once per new bar.
        if self.state["last_bar_seen"].get(inst.name) == str(latest):
            return []
        signal = int(sig.loc[latest, "signal"])
        if signal == 0:
            return []

        hs = self._half_spread(inst)
        close = float(df.loc[latest, "close"])
        entry = close + signal * hs          # market entry just after bar close
        stop = float(sig.loc[latest, "stop"])
        target = float(sig.loc[latest, "target"])
        equity = self.equity()
        units = position_size(equity, self.risk_pct, entry, stop)
        if units <= 0:
            return []

        pos = {
            "instrument": inst.name, "direction": signal,
            "entry_time": str(latest), "entry_price": entry,
            "stop": stop, "target": target, "units": units,
            "risk_pct": self.risk_pct,
        }
        self.state["open_positions"][inst.name] = pos
        side = "LONG" if signal == 1 else "SHORT"
        rr = abs(target - entry) / abs(entry - stop) if entry != stop else 0
        note = (f"{side} {inst.name} @ {entry:.5f} | stop {stop:.5f} "
                f"| target {target:.5f} | {units:.0f} units "
                f"| risk {self.risk_pct}% | R:R {rr:.1f}")
        return [self._action(inst, "RECOMMENDED_TRADE", price=entry, note=note)]

    # ---- reporting ---------------------------------------------------
    def equity(self) -> float:
        """Realized cash + unrealized P&L on open positions."""
        eq = self.state["realized_equity"]
        for name, pos in self.state["open_positions"].items():
            mark = self._mark(name)
            if mark is None:
                continue
            eq += pos["direction"] * (mark - pos["entry_price"]) * pos["units"]
        return eq

    def _action(self, inst, kind, price=None, pnl=None, note="") -> dict:
        return {
            "time": _now().isoformat(timespec="seconds"),
            "instrument": inst.name, "action": kind,
            "price": price, "pnl": pnl, "note": note,
        }

    def summary(self) -> str:
        s = self.state
        realized = s["realized_equity"]
        ret = (realized / s["starting_equity"] - 1) * 100
        closed = s["closed_trades"]
        wins = [t for t in closed if t["pnl"] > 0]
        wr = (len(wins) / len(closed) * 100) if closed else float("nan")
        avg_R = (sum(t["R"] for t in closed) / len(closed)) if closed else float("nan")

        lines = [
            "=" * 62,
            f" PAPER ACCOUNT ({self.source}, {self.interval})  "
            f"since {s['created'][:10]}",
            "=" * 62,
            f" Realized equity : {realized:,.2f}  ({ret:+.2f}% vs "
            f"{s['starting_equity']:,.0f} start)",
            f" Closed trades   : {len(closed)}   win rate "
            f"{wr:.1f}%   avg {avg_R:+.2f}R" if closed else
            f" Closed trades   : 0",
            f" Open positions  : {len(s['open_positions'])}",
        ]
        for name, p in s["open_positions"].items():
            side = "LONG" if p["direction"] == 1 else "SHORT"
            lines.append(f"    - {side} {name} @ {p['entry_price']:.5f} "
                         f"(stop {p['stop']:.5f} / target {p['target']:.5f})")
        lines.append("=" * 62)
        return "\n".join(lines)
