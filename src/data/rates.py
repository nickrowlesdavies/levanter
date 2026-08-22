"""
Interest-rate data + FX carry.

Carry is the one FX factor with real evidence behind it: over time, holding
the higher-yielding currency against the lower-yielding one tends to pay -
both through the interest differential you earn (the "roll"/swap) and
because high-yielders historically don't depreciate as much as interest-rate
parity says they should.

We pull 3-month interbank rates per currency from FRED's public CSV endpoint
(no API key needed), then for a pair BASE/QUOTE compute:

    carry = rate(BASE) - rate(QUOTE)     # annualised %, being LONG the pair

Positive carry -> being long the pair earns the differential; negative ->
being short earns it. Rates are monthly and move slowly, so we forward-fill
them onto the daily/4h price index.
"""
from __future__ import annotations

import io
import os

import pandas as pd
import requests

# currency -> FRED 3-month interbank series id (all key-free CSV)
CCY_SERIES = {
    "USD": "IR3TIB01USM156N",
    "EUR": "IR3TIB01EZM156N",
    "GBP": "IR3TIB01GBM156N",
    "JPY": "IR3TIB01JPM156N",
    "AUD": "IR3TIB01AUM156N",
    "CHF": "IR3TIB01CHM156N",
    "NZD": "IR3TIB01NZM156N",
    "CAD": "IR3TIB01CAM156N",
    "NOK": "IR3TIB01NOM156N",
    "SEK": "IR3TIB01SEM156N",
}

_FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"


def fetch_rate(ccy: str, cache_dir: str = "data_cache", use_cache: bool = True) -> pd.Series:
    """Return a date-indexed Series of the currency's 3m rate (annual %)."""
    sid = CCY_SERIES.get(ccy.upper())
    if sid is None:
        raise ValueError(f"No rate series configured for {ccy}")

    os.makedirs(cache_dir, exist_ok=True)
    cache_path = os.path.join(cache_dir, f"rate_{ccy.upper()}.csv")
    if use_cache and os.path.exists(cache_path):
        s = pd.read_csv(cache_path, index_col=0, parse_dates=True).iloc[:, 0]
        s.name = ccy.upper()
        return s

    r = requests.get(_FRED_CSV.format(sid=sid), timeout=30)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text))
    df.columns = ["date", "val"]
    df["date"] = pd.to_datetime(df["date"])
    df["val"] = pd.to_numeric(df["val"], errors="coerce")
    s = df.dropna().set_index("date")["val"]
    s.name = ccy.upper()
    if use_cache:
        s.to_csv(cache_path)
    return s


def carry_for_pair(name: str, index: pd.DatetimeIndex,
                   cache_dir: str = "data_cache") -> pd.Series:
    """Annualised carry (%) for being LONG `name` (e.g. 'AUDUSD'), aligned
    and forward-filled onto `index`."""
    base, quote = name[:3].upper(), name[3:].upper()
    rb = fetch_rate(base, cache_dir)
    rq = fetch_rate(quote, cache_dir)

    # Union the two monthly series, ffill, then reindex onto price dates.
    rates = pd.concat([rb.rename("base"), rq.rename("quote")], axis=1).sort_index()
    rates = rates.ffill()
    diff = (rates["base"] - rates["quote"]).dropna()

    idx = pd.DatetimeIndex(index)
    aligned = diff.reindex(diff.index.union(idx)).ffill().reindex(idx)
    aligned.name = "carry"
    return aligned
