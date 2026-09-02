#!/usr/bin/env python3
"""One writer at a time in this working tree.

CLAUDE.md already asks for this, and asking was not enough. On 2 September 2026
two sessions ran here at once and between them produced a commit that imported
an untracked module, repeated rebase conflicts, and a crypto_map.json carrying
git conflict markers that came within one run of reaching a publication.

The lock is an exclusive flock on a file in the repo root. The kernel releases
an flock when the holding process exits for any reason, including kill -9, so a
crashed run cannot strand a lock that someone later has to break by hand. That
property is the whole reason for using flock rather than a PID file.

Usage:

    import repo_lock
    repo_lock.acquire("signal_note")        # raises LockBusy if held elsewhere

    with repo_lock.held("build"):           # or as a context manager
        ...

Set LEVANTER_LOCK_WAIT=<seconds> to wait for the holder instead of failing at
once. A cron job usually wants a short wait; a person at a terminal usually
wants to be told immediately who is running.
"""
import contextlib
import datetime as dt
import fcntl
import json
import os
import sys
import time

LOCK_PATH = os.environ.get("LEVANTER_LOCK", ".levanter.lock")


class LockBusy(RuntimeError):
    """Another process is writing to this working tree."""


# Keeps the file objects alive for the life of the process. Closing one, or
# letting it be garbage collected, releases its lock.
_HELD = []


def _describe(fh):
    try:
        fh.seek(0)
        d = json.loads(fh.read() or "{}")
    except Exception:
        return "another process, details unreadable"
    if not d:
        return "another process"
    return (f"{d.get('what', 'a run')}, pid {d.get('pid', '?')}, "
            f"started {d.get('started', '?')}")


def acquire(what="a run", wait=None):
    """Take the tree lock, or raise LockBusy naming who holds it."""
    if wait is None:
        try:
            wait = float(os.environ.get("LEVANTER_LOCK_WAIT", "0") or 0)
        except ValueError:
            wait = 0.0
    fh = open(LOCK_PATH, "a+", encoding="utf-8")
    deadline = time.monotonic() + max(0.0, wait)
    while True:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except OSError:
            if time.monotonic() >= deadline:
                holder = _describe(fh)
                fh.close()
                raise LockBusy(
                    f"another Levanter process holds this working tree: {holder}. "
                    f"Wait for it rather than running both, which is how a half-written "
                    f"feed reaches a publication. Set LEVANTER_LOCK_WAIT=60 to wait.")
            time.sleep(0.25)
    fh.seek(0)
    fh.truncate()
    json.dump({"what": what, "pid": os.getpid(),
               "started": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
               "argv": " ".join(sys.argv[:3])}, fh)
    fh.flush()
    _HELD.append(fh)
    return fh


@contextlib.contextmanager
def held(what="a run", wait=None):
    fh = acquire(what, wait)
    try:
        yield fh
    finally:
        release(fh)


def release(fh=None):
    """Release the lock. Rarely needed: process exit releases it."""
    for h in ([fh] if fh is not None else list(_HELD)):
        with contextlib.suppress(Exception):
            fcntl.flock(h, fcntl.LOCK_UN)
            h.close()
        if h in _HELD:
            _HELD.remove(h)
