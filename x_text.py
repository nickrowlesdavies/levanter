#!/usr/bin/env python3
"""How X counts a post, and what to do when one does not fit.

X wraps every link in t.co, so it charges a flat 23 characters for a URL
whatever its real length. A plain len() therefore passes posts that X rejects:
the launch post measured 277 by a normal count and 281 by X's, the difference
being one bare "levantermarkets.com" at 19 characters charged as 23.

Both thread renderers used len(). signal_note went further and dropped any post
over the limit from the thread without a word, so a thread could publish a post
short with nothing in the output to say so. Silence is the wrong failure here:
the point of a numbered thread is that every post in it arrives.
"""
import re

X_LIMIT = 280        # characters in a single post
URL_WEIGHT = 23      # what X charges for any link, however long

# A scheme-qualified URL, or a bare host on one of the TLDs we actually publish.
# Deliberately narrow: a greedy pattern would read "0.55" or "e.g." as a link and
# silently inflate the count, which fails in the opposite direction.
_URL = re.compile(
    r"https?://\S+"
    r"|\b(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+(?:com|org|net|io|co|ai|dev|app|substack\.com)\b(?:/\S*)?",
    re.I)


class PostTooLong(RuntimeError):
    """One or more posts exceed the limit as X counts it."""


def x_len(s):
    """Length of `s` as X counts it, with every URL charged at URL_WEIGHT."""
    return len(_URL.sub("u" * URL_WEIGHT, s or ""))


def overlong(posts, limit=X_LIMIT):
    """[(1-based index, x_len, plain len, text)] for every post that will not fit."""
    return [(i, x_len(p), len(p), p)
            for i, p in enumerate(posts, 1) if x_len(p) > limit]


def require_fit(posts, where="thread", limit=X_LIMIT):
    """Raise PostTooLong naming every offender. Never drop one quietly."""
    bad = overlong(posts, limit)
    if not bad:
        return
    lines = [f"post {i}: {xl} chars as X counts it ({pl} plain), {xl - limit} over"
             for i, xl, pl, _ in bad]
    raise PostTooLong(
        f"{len(bad)} post(s) in the {where} exceed the {limit}-character limit:\n  - "
        + "\n  - ".join(lines)
        + "\nShorten them. They are not dropped, because a thread missing a post "
          "is worse than one that does not build.")
