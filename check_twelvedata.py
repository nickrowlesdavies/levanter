#!/usr/bin/env python3
"""
Twelve Data connection test. Run this once your free key is set to confirm
the feed works before running the trial.

    python check_twelvedata.py

Verifies the key, pulls a live price, and downloads recent 4h candles.
Read-only. No brokerage involved.
"""
from __future__ import annotations

import sys

import yaml

from src.data.twelvedata import TwelveDataClient, load_key, MissingApiKey


def main():
    with open("config.yaml") as f:
        cfg = yaml.safe_load(f)
    names = [i["name"] for i in cfg["instruments"]]

    try:
        key = load_key()
    except MissingApiKey as e:
        print(f"\n[!] {e}\n")
        print("Steps:")
        print("  1. cp twelvedata.secret.example.yaml twelvedata.secret.yaml")
        print("  2. paste your free key into it")
        print("  3. re-run:  python check_twelvedata.py\n")
        sys.exit(1)

    client = TwelveDataClient(key)

    print("\n[1/2] Live prices...")
    for n in names:
        p = client.price(n)
        print(f"      {n:<8} {p if p is not None else '(no price)'}")

    print("\n[2/2] Recent 4h candles (EURUSD, last 5)...")
    df = client.candles("EURUSD", interval="4h", start="2025-01-01")
    print(df.tail(5).to_string())

    print("\nAll good. The Twelve Data feed is wired up. ✅")
    print("To run the trial on it, set in config.yaml:")
    print('    data.source: "twelvedata"   and   data.interval: "4h"')
    print("then:  python paper_trade.py --once\n")


if __name__ == "__main__":
    main()
