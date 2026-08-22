# FX Signal Engine

A personal-use FX signal + backtesting system. Swing timeframe, majors,
broker-agnostic. Built to measure edge honestly before any real money.

## What it does today (v0.1)
- Pulls free daily FX data (yfinance), cached locally.
- Generates signals from a pluggable strategy (trend-following breakout baseline).
- Backtests bar-by-bar with **realistic costs and no lookahead**.
- Splits **in-sample vs out-of-sample** and scores both.
- Outputs a scorecard (Sharpe, drawdown, win rate, profit factor, expectancy in R),
  per-pair trade blotters (CSV), and equity-curve charts (PNG).

## What it is NOT (yet)
- Not connected to a broker. No live or paper orders are placed.
- Not financial advice. It surfaces signals; a human decides.

## Quick start
```bash
cd fx-signal-engine
source .venv/bin/activate
python run_backtest.py            # run the backtest
python run_backtest.py --refresh  # re-download data (ignore cache)
```
Everything tunable lives in `config.yaml`. To try a new idea, add a strategy
class in `src/signals/` (subclass `Strategy`) and point `config.yaml` at it.

## Layout
```
config.yaml            all knobs (pairs, costs, risk, strategy params)
run_backtest.py        entry point
src/data/loader.py     data layer (yfinance now; OANDA-ready interface)
src/signals/           strategies (pluggable)
src/backtest/          engine (honest sim) + metrics
src/risk/sizing.py     risk-based position sizing
reports/               generated charts + trade blotters
```

## Paper trading (the trial)
```bash
python paper_trade.py --once                  # one cycle (use with cron/scheduler)
python paper_trade.py --loop --interval 3600  # run continuously, hourly
python paper_trade.py --status                # print account state only
python paper_trade.py --reset                 # wipe the paper account
```
Books trades into a SIMULATED account (`reports/paper_state.json`), logs every
action to `reports/paper_log.csv`, and surfaces each new signal as a
RECOMMENDED TRADE. Never sends a real order. Runs on yfinance today; flip
`data.source: "oanda"` for live practice prices.

## OANDA setup
```bash
cp oanda.secret.example.yaml oanda.secret.yaml   # then paste token + account id
python check_oanda.py                            # verify the connection
```
`oanda.secret.yaml` is git-ignored. See the example file for where to get a
free practice token.

## Roadmap (see chat for detail)
1. Data + backtest  ✅
2. OANDA practice feed + adapter  ✅
3. Paper-trading loop (the "trial")  ✅  (activates fully once token is set)
4. Strategy research + walk-forward optimisation
5. Risk guardrails (daily loss limit, exposure caps)
6. Go-live gate: signals surfaced for human approval, never auto-fired

## Honest note
The baseline strategy is a transparent classic, not a proven edge. On daily
majors net of costs it lands around break-even — exactly what you should
expect before real research. The point of this rig is to stop you fooling
yourself. Out-of-sample expectancy > 0R after costs is the bar to clear.
```
