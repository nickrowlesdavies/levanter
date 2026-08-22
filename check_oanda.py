#!/usr/bin/env python3
"""
OANDA connection test. Run this once your credentials are set to confirm
the practice feed is live before doing anything else.

    python check_oanda.py

It verifies three things:
  1. Auth works and the account is reachable (prints balance/currency).
  2. Live pricing streams (prints bid/ask/spread for the majors).
  3. Historical candles download (prints the last few daily bars).

No orders are placed. Read-only.
"""
from __future__ import annotations

import sys

import yaml

from src.data.oanda import OandaClient, load_creds, MissingCredentials


def main():
    with open("config.yaml") as f:
        cfg = yaml.safe_load(f)
    env = cfg["data"].get("environment", "practice")
    names = [i["name"] for i in cfg["instruments"]]

    try:
        creds = load_creds(env)
    except MissingCredentials as e:
        print(f"\n[!] {e}\n")
        print("Steps:")
        print("  1. cp oanda.secret.example.yaml oanda.secret.yaml")
        print("  2. paste your practice token + account id into it")
        print("  3. re-run:  python check_oanda.py\n")
        sys.exit(1)

    client = OandaClient(creds)
    print(f"\nEnvironment: {creds.environment}  ({creds.host})")

    # 1. Account
    print("\n[1/3] Account summary...")
    acc = client.account_summary()
    print(f"      id={acc.get('id')}  currency={acc.get('currency')}  "
          f"balance={acc.get('balance')}  openTrades={acc.get('openTradeCount')}")

    # 2. Pricing
    print("\n[2/3] Live pricing...")
    px = client.pricing(names)
    if len(px):
        for _, row in px.iterrows():
            pips = row["spread"] / (0.01 if "JPY" in row["instrument"] else 0.0001)
            print(f"      {row['instrument']:<8} bid={row['bid']:.5f} "
                  f"ask={row['ask']:.5f}  spread={pips:.1f} pips  "
                  f"tradeable={row['tradeable']}")
    else:
        print("      (no prices returned - market may be closed)")

    # 3. Candles
    print("\n[3/3] Historical daily candles (EURUSD, last 5)...")
    df = client.candles("EURUSD", interval="1d", start="2024-01-01")
    print(df.tail(5).to_string())

    print("\nAll good. The OANDA practice feed is wired up. ✅")
    print("Next: set data.source: \"oanda\" in config.yaml to backtest on OANDA data,")
    print("or say the word and I'll build the forward paper-trading loop.\n")


if __name__ == "__main__":
    main()
