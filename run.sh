#!/bin/bash
# Wrapper for scheduled runs: activate the venv, then run the given command.
# Used by cron so the environment is always correct regardless of PATH.
#   ./run.sh paper_trade.py --once
#   ./run.sh carry_signal.py
cd "/Users/nickrowles-davies/Documents/Claude/Claude Outputs/fx-signal-engine" || exit 1
# shellcheck disable=SC1091
source .venv/bin/activate
exec python "$@"
