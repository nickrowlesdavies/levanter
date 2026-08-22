"""
Twelve Data adapter - free, global FX price feed for the trial.

Why this instead of OANDA: price data is not geo-restricted like a
brokerage account, so Twelve Data works fine from the UK/UAE. The free
tier gives native 4h candles (800 requests/day, 8/min), which is all the
forward paper trial needs. No broker, no regulatory onboarding.

Provides:
  * historical candles -> same OHLC DataFrame shape as every other loader
  * latest price        -> for marking the paper account to market

Credentials: a single data API key, read from env TWELVEDATA_API_KEY or a
git-ignored twelvedata.secret.yaml (see the .example). This is a *data*
key, not a trading credential - it cannot move money.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Optional

import pandas as pd
import requests

HOST = "https://api.twelvedata.com"

# our interval codes -> Twelve Data interval strings
_INTERVAL = {"1d": "1day", "4h": "4h", "2h": "2h", "1h": "1h",
             "30m": "30min", "15m": "15min", "5m": "5min"}


def td_symbol(name: str) -> str:
    """EURUSD -> EUR/USD (majors are 6 chars: base + quote)."""
    name = name.upper().replace("=X", "").replace("_", "").replace("/", "")
    if len(name) == 6:
        return f"{name[:3]}/{name[3:]}"
    return name


class MissingApiKey(RuntimeError):
    pass


class BadRequest(RuntimeError):
    """400 from the API - typically an out-of-range date during pagination."""
    pass


@dataclass
class TwelveDataCreds:
    api_key: str


def _clean(raw: str) -> str:
    """Strip whitespace and any stray quotes (incl. smart quotes some
    editors insert) so a pasted key can't be broken by formatting."""
    return raw.strip().strip("\"'“”‘’").strip()


def load_key(
    plain_file: str = "twelvedata.key",
    secret_file: str = "twelvedata.secret.yaml",
) -> str:
    # 1. Environment variable
    key = os.environ.get("TWELVEDATA_API_KEY")

    # 2. Plaintext file: just the raw key (first non-comment line). No YAML,
    #    no quotes - the robust, editor-proof option.
    if not key and os.path.exists(plain_file):
        with open(plain_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    key = _clean(line)
                    break

    # 3. YAML secret file (legacy / optional)
    if not key and os.path.exists(secret_file):
        import yaml
        try:
            with open(secret_file) as f:
                data = yaml.safe_load(f) or {}
            key = _clean(str(data.get("api_key", "")))
        except Exception:
            key = None  # malformed YAML (e.g. smart quotes) - fall through

    _placeholders = ("PASTE", "YOUR_KEY", "YOUR_REAL_KEY", "YOUR_TWELVE")
    if not key or key.upper().startswith(_placeholders):
        raise MissingApiKey(
            "Twelve Data API key not found. Easiest fix - put the raw key in a "
            "plaintext file:\n    echo 'YOUR_KEY' > twelvedata.key\n"
            "(or set TWELVEDATA_API_KEY env var). "
            "Free key: https://twelvedata.com/pricing"
        )
    return key


class TwelveDataClient:
    def __init__(self, api_key: str, timeout: int = 20):
        self.api_key = api_key
        self.timeout = timeout
        self.session = requests.Session()

    def _get(self, path: str, params: dict, _retries: int = 3) -> dict:
        params = {**params, "apikey": self.api_key}
        for attempt in range(_retries + 1):
            r = self.session.get(f"{HOST}/{path}", params=params, timeout=self.timeout)
            # Handle status codes explicitly so the API key (in the URL) never
            # leaks into an exception message.
            if r.status_code == 401:
                raise RuntimeError(
                    "Twelve Data rejected the API key (401 Unauthorized). Put your "
                    "real key in twelvedata.key:  echo 'YOUR_REAL_KEY' > twelvedata.key"
                )
            if r.status_code == 400:
                raise BadRequest(f"Twelve Data 400 for {path} (likely out-of-range dates)")
            # 429 (or in-body rate-limit) -> wait out the 8/min window and retry.
            body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            rate_limited = r.status_code == 429 or (
                isinstance(body, dict) and str(body.get("code")) == "429")
            if rate_limited:
                if attempt < _retries:
                    time.sleep(16)        # free tier resets per minute
                    continue
                raise RuntimeError("Twelve Data rate limit hit (8/min free tier); retries exhausted")
            if r.status_code != 200:
                raise RuntimeError(f"Twelve Data HTTP {r.status_code} for {path}")
            data = body if body else r.json()
            if isinstance(data, dict) and data.get("status") == "error":
                raise RuntimeError(f"Twelve Data error: {data.get('message')}")
            return data
        raise RuntimeError("Twelve Data request failed")   # unreachable

    def price(self, name: str) -> Optional[float]:
        try:
            data = self._get("price", {"symbol": td_symbol(name)})
            return float(data["price"])
        except Exception:
            return None

    def candles(
        self,
        name: str,
        interval: str = "4h",
        start: Optional[str] = None,
        end: Optional[str] = None,
        max_pages: int = 30,
    ) -> pd.DataFrame:
        """Paginated candle download -> OHLC DataFrame indexed by date.

        Each call returns up to 5000 points; for long 4h histories we page
        forward by date. Daily histories fit in a single call.
        """
        symbol = td_symbol(name)
        td_int = _INTERVAL.get(interval)
        if td_int is None:
            raise ValueError(f"Unsupported interval for Twelve Data: {interval}")

        cursor = start
        end_ts = pd.Timestamp(end) if end else None
        now = pd.Timestamp.utcnow().tz_localize(None)
        frames = []

        for page in range(max_pages):
            params = {
                "symbol": symbol, "interval": td_int,
                "outputsize": 5000, "order": "ASC", "timezone": "UTC",
            }
            if cursor:
                params["start_date"] = cursor
            if end:
                params["end_date"] = end

            try:
                data = self._get("time_series", params)
            except BadRequest:
                break                     # out-of-range page -> we're done
            values = data.get("values", []) if isinstance(data, dict) else []
            if not values:
                break

            df = pd.DataFrame(values)
            df["datetime"] = pd.to_datetime(df["datetime"])
            for c in ("open", "high", "low", "close"):
                df[c] = df[c].astype(float)
            df = df[["datetime", "open", "high", "low", "close"]].rename(
                columns={"datetime": "date"}
            )
            frames.append(df)

            last_time = df["date"].iloc[-1]
            if len(values) < 5000:
                break                     # reached the end of available data
            if end_ts is not None and last_time >= end_ts:
                break
            next_cursor = last_time + pd.Timedelta(seconds=1)
            if next_cursor >= now:
                break                     # caught up to the present
            cursor = next_cursor.strftime("%Y-%m-%d %H:%M:%S")
            time.sleep(8)                 # respect 8 requests/minute free tier

        if not frames:
            return pd.DataFrame(columns=["open", "high", "low", "close"])

        out = pd.concat(frames).drop_duplicates("date").set_index("date").sort_index()
        out.index.name = "date"
        if end_ts is not None:
            out = out[out.index <= end_ts]
        return out
