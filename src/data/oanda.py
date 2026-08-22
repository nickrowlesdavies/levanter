"""
OANDA v20 practice-account adapter.

Provides three things the rest of the system needs:
  * historical candles  -> same OHLC DataFrame shape as the yfinance loader
  * live pricing (bid/ask/spread) -> for the forward paper-trading loop
  * account summary      -> to confirm the connection is real

Credentials are NEVER hard-coded. They are read (in order) from:
  1. environment variables  OANDA_API_TOKEN / OANDA_ACCOUNT_ID
  2. a local, git-ignored file  oanda.secret.yaml  (see the .example)

Practice (demo) and live share the same API shape; only the host differs.
We default to practice. Nothing here places an order - it reads data only.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Optional

import pandas as pd
import requests

PRACTICE_HOST = "https://api-fxpractice.oanda.com"
LIVE_HOST = "https://api-fxtrade.oanda.com"

# Map our internal names to OANDA instrument codes and granularities.
_GRANULARITY = {"1d": "D", "4h": "H4", "1h": "H1", "30m": "M30", "15m": "M15"}


def oanda_symbol(name: str) -> str:
    """EURUSD -> EUR_USD (majors are 6 chars: base + quote)."""
    name = name.upper().replace("_", "").replace("=X", "")
    if len(name) == 6:
        return f"{name[:3]}_{name[3:]}"
    return name  # already formatted or non-standard


@dataclass
class OandaCreds:
    api_token: str
    account_id: str
    environment: str = "practice"  # "practice" or "live"

    @property
    def host(self) -> str:
        return LIVE_HOST if self.environment == "live" else PRACTICE_HOST


class MissingCredentials(RuntimeError):
    pass


def load_creds(environment: str = "practice",
               secret_file: str = "oanda.secret.yaml") -> OandaCreds:
    """Load credentials from env vars, falling back to a local secret file."""
    token = os.environ.get("OANDA_API_TOKEN")
    account = os.environ.get("OANDA_ACCOUNT_ID")
    env = os.environ.get("OANDA_ENV", environment)

    if (not token or not account) and os.path.exists(secret_file):
        import yaml
        with open(secret_file) as f:
            data = yaml.safe_load(f) or {}
        token = token or data.get("api_token")
        account = account or data.get("account_id")
        env = data.get("environment", env)

    if not token or not account:
        raise MissingCredentials(
            "OANDA credentials not found. Set OANDA_API_TOKEN and "
            "OANDA_ACCOUNT_ID env vars, or create oanda.secret.yaml "
            "(copy oanda.secret.example.yaml)."
        )
    return OandaCreds(api_token=token, account_id=account, environment=env)


class OandaClient:
    def __init__(self, creds: OandaCreds, timeout: int = 20):
        self.creds = creds
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {creds.api_token}",
                "Content-Type": "application/json",
            }
        )

    # ---- connection / account -----------------------------------------
    def account_summary(self) -> dict:
        url = f"{self.creds.host}/v3/accounts/{self.creds.account_id}/summary"
        r = self.session.get(url, timeout=self.timeout)
        r.raise_for_status()
        return r.json()["account"]

    # ---- live pricing --------------------------------------------------
    def pricing(self, instruments) -> pd.DataFrame:
        """Current bid/ask/spread for one or more instruments."""
        if isinstance(instruments, str):
            instruments = [instruments]
        codes = ",".join(oanda_symbol(x) for x in instruments)
        url = f"{self.creds.host}/v3/accounts/{self.creds.account_id}/pricing"
        r = self.session.get(url, params={"instruments": codes}, timeout=self.timeout)
        r.raise_for_status()
        rows = []
        for p in r.json().get("prices", []):
            bid = float(p["bids"][0]["price"]) if p.get("bids") else float("nan")
            ask = float(p["asks"][0]["price"]) if p.get("asks") else float("nan")
            rows.append(
                {
                    "instrument": p["instrument"],
                    "time": pd.to_datetime(p["time"]),
                    "bid": bid,
                    "ask": ask,
                    "spread": ask - bid,
                    "tradeable": p.get("tradeable", False),
                }
            )
        return pd.DataFrame(rows)

    # ---- historical candles -------------------------------------------
    def candles(
        self,
        name: str,
        interval: str = "1d",
        start: Optional[str] = None,
        end: Optional[str] = None,
        price: str = "M",         # M=mid, B=bid, A=ask
        max_pages: int = 200,
    ) -> pd.DataFrame:
        """Paginated candle download -> OHLC DataFrame indexed by date.

        OANDA caps each request at 5000 candles, so we page forward by time.
        Only *complete* candles are kept (no half-formed current bar).
        """
        symbol = oanda_symbol(name)
        gran = _GRANULARITY.get(interval)
        if gran is None:
            raise ValueError(f"Unsupported interval for OANDA: {interval}")

        url = f"{self.creds.host}/v3/instruments/{symbol}/candles"
        params = {"granularity": gran, "price": price, "count": 5000}
        if start:
            params["from"] = pd.Timestamp(start).tz_localize("UTC").isoformat()
        end_ts = pd.Timestamp(end).tz_localize("UTC") if end else None

        all_rows = []
        for _ in range(max_pages):
            r = self.session.get(url, params=params, timeout=self.timeout)
            r.raise_for_status()
            candles = r.json().get("candles", [])
            if not candles:
                break
            for c in candles:
                if not c.get("complete", False):
                    continue
                mid = c[{"M": "mid", "B": "bid", "A": "ask"}[price]]
                all_rows.append(
                    {
                        "date": pd.to_datetime(c["time"]),
                        "open": float(mid["o"]),
                        "high": float(mid["h"]),
                        "low": float(mid["l"]),
                        "close": float(mid["c"]),
                    }
                )
            last_time = pd.to_datetime(candles[-1]["time"])
            if end_ts is not None and last_time >= end_ts:
                break
            if len(candles) < params["count"]:
                break  # reached the present
            # Advance the window just past the last candle.
            params.pop("count", None)
            params["from"] = (last_time + pd.Timedelta(seconds=1)).isoformat()
            params["count"] = 5000
            time.sleep(0.15)  # be polite to the API

        if not all_rows:
            return pd.DataFrame(columns=["open", "high", "low", "close"])

        df = pd.DataFrame(all_rows).drop_duplicates("date").set_index("date")
        df.index = df.index.tz_localize(None)
        df.index.name = "date"
        if end_ts is not None:
            df = df[df.index <= end_ts.tz_localize(None)]
        return df.sort_index()
