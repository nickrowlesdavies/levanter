"""
Data layer.

Right now this pulls free daily FX candles via yfinance (no credentials).
It is deliberately written behind a small interface so a live/practice
OANDA feed (or any broker) can be dropped in later without touching the
strategy or backtest code.

Everything downstream expects a DataFrame indexed by date with columns:
    open, high, low, close   (lowercase)
"""
from __future__ import annotations

import os
import warnings
from dataclasses import dataclass

import pandas as pd

warnings.filterwarnings("ignore")


@dataclass
class Instrument:
    name: str          # e.g. "EURUSD"
    symbol: str        # data-source ticker, e.g. "EURUSD=X"
    pip: float         # pip size, e.g. 0.0001 (or 0.01 for JPY pairs)
    spread_pips: float # assumed round-trip spread cost in pips


def _flatten_yf(df: pd.DataFrame) -> pd.DataFrame:
    """yfinance sometimes returns MultiIndex columns; normalise to OHLC."""
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns=str.lower)
    keep = ["open", "high", "low", "close"]
    df = df[[c for c in keep if c in df.columns]].copy()
    df.index.name = "date"
    return df.dropna()


def load_candles(
    inst: Instrument,
    start: str,
    end: str,
    interval: str = "1d",
    cache_dir: str = "data_cache",
    use_cache: bool = True,
    source: str = "yfinance",
    environment: str = "practice",
) -> pd.DataFrame:
    """Load OHLC candles for one instrument, with a local CSV cache.

    `source` selects the feed: "yfinance" (free, no creds) or "oanda"
    (practice/live account). Both return the same OHLC shape.
    """
    os.makedirs(cache_dir, exist_ok=True)
    cache_path = os.path.join(
        cache_dir, f"{inst.name}_{source}_{interval}_{start}_{end}.csv"
    )

    if use_cache and os.path.exists(cache_path):
        return pd.read_csv(cache_path, index_col="date", parse_dates=True)

    if source == "oanda":
        from .oanda import OandaClient, load_creds

        client = OandaClient(load_creds(environment))
        df = client.candles(inst.name, interval=interval, start=start, end=end)
        if use_cache and len(df):
            df.to_csv(cache_path)
        return df

    if source == "twelvedata":
        from .twelvedata import TwelveDataClient, load_key

        client = TwelveDataClient(load_key())
        df = client.candles(inst.name, interval=interval, start=start, end=end)
        if use_cache and len(df):
            df.to_csv(cache_path)
        return df

    import yfinance as yf

    raw = yf.download(
        inst.symbol,
        start=start,
        end=end,
        interval=interval,
        progress=False,
        auto_adjust=True,
    )
    if raw is None or len(raw) == 0:
        raise RuntimeError(f"No data returned for {inst.name} ({inst.symbol})")

    df = _flatten_yf(raw)
    if use_cache:
        df.to_csv(cache_path)
    return df
