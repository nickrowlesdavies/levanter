#!/usr/bin/env python3
"""Hard preconditions on the JSON feeds the publications are built from.

The readers in signal_note.py and build_dashboard.py swallow errors and return
an empty dict, which is right for an optional field and wrong for a required
one. On 2 September 2026 a failed rebase left git conflict markers in
crypto_map.json; the Wednesday Signal was written anyway and silently lost its
cross-asset correlation paragraph. A publication that quietly drops a section is
worse than one that does not build, so callers declare what they cannot be
written honestly without and this fails loudly instead.
"""
import json
import os


class SourceError(RuntimeError):
    """A required input is missing, unparseable, truncated or conflicted."""


def check_sources(required, what="output"):
    """Raise SourceError unless every required source is usable.

    `required` maps a path to the top-level keys that path must carry non-null.
    Pass an empty tuple for a file that is a list, or where presence and valid
    JSON is the whole requirement. Every problem is collected and reported at
    once rather than one per run.
    """
    problems = []
    for path, keys in required.items():
        if not os.path.exists(path):
            problems.append(f"{path}: missing")
            continue
        raw = open(path, encoding="utf-8", errors="replace").read()
        if "<<<<<<< " in raw or ">>>>>>> " in raw:
            problems.append(f"{path}: contains git conflict markers, resolve it and regenerate")
            continue
        try:
            data = json.loads(raw)
        except Exception as e:
            problems.append(f"{path}: does not parse ({e})")
            continue
        if not data:
            problems.append(f"{path}: parsed but empty")
            continue
        if isinstance(data, dict):
            missing = [k for k in keys if data.get(k) is None]
            if missing:
                problems.append(f"{path}: missing or null {', '.join(missing)}")
    if problems:
        raise SourceError(
            f"{len(problems)} source problem(s), refusing to write {what}:\n  - "
            + "\n  - ".join(problems)
            + "\nRegenerate the affected feed(s), then run again.")


# The market feeds every publication reads. Strategy *_state.json files are
# deliberately absent: .gitignore excludes them, so they are legitimately
# missing on a fresh checkout and must not block a build.
MARKET_SOURCES = {
    "reports/vol_regime.json": ("assets", "backtest", "classes"),
    "reports/crypto_map.json": ("coins", "avg_corr", "btc_dominance"),
    "reports/fx_map.json": ("pairs",),
    "reports/commodities_map.json": ("items",),
    "reports/btc_metcalfe.json": ("price", "fair_value", "floor"),
    "reports/cycle_gauge.json": (),
}

# direction_backtest.json sits at the repo root and backs the coin-flip honesty
# line, which is a hard gate on both Signals.
SIGNAL_SOURCES = dict(MARKET_SOURCES, **{
    "direction_backtest.json": ("n", "accuracy", "by_class"),
})
