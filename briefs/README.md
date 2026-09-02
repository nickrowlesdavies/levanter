# Briefs

Written in the Cowork session, for Claude Code to execute. Newest last.

| File | Status | What it covered |
| --- | --- | --- |
| `2026-08-24-site-and-agent-files.md` | done | Direction-call contradiction, Substack URL in the launch post, robots.txt / llms.txt / sitemap / security.txt / JSON-LD, and per-review URLs at `/reviews/<date>-<cadence>/`. |
| `2026-08-25-model-naming-sweep.md` | done | Removing the false claim that the two bitcoin models differ by what they measure against. Agreed names: the valuation fit and the cycle gauge. Retitled `btc_metcalfe.png`. |
| `2026-08-25-carousel-generator.md` | open | Turn the hand-built LinkedIn carousel into `signal_carousel.py` so it regenerates each week from the same data `signal_note.py` uses. |
| `2026-08-25-x-daily-generator.md` | mostly done | Emit a daily X post alongside the daily note. Rotates its lead by what is actually notable rather than a fixed template, and counts characters the way X does. Built in `build_dashboard.py`, writing `reports/x/levanter-x-daily-<date>.md` as a numbered thread. The character counting half is NOT done, see open items. |

## Standing conventions these assume

- The repo is the source of truth. Nothing is hand-edited downstream of a generator.
- Anything hand-built gets its source committed, so it can be rebuilt by someone else.
- Channel outputs live under `reports/<channel>/`, with `docx/` and `pdf/` subdirectories,
  named `levanter-<thing>-<date>`.
- The two bitcoin models are always "the valuation fit" and "the cycle gauge". Their
  agreement is never presented as corroboration.
- The direction scorecard quotes all three rows with the commodities caveat attached.
  Never a blended figure, never a bare 62%. The monthly Signal does this. The weekly and
  the dashboard do not yet, see open items.
- Nothing is written on top of a broken feed. Generators call `source_guard.check_sources`
  and stop rather than quietly dropping a section.
- One writer at a time in this tree, enforced by `repo_lock.py`, not just asked for.

## Open items not yet briefed

- **The direction scorecard is half converted.** The monthly Signal now quotes all three
  rows, with the commodities not-an-edge caveat and FX declared unscored. The weekly Signal
  and the dashboard still quote the crypto row alone. There is still no shared helper:
  `signal_note.py`, `signal_monthly.py` and `build_dashboard.py` each read
  `direction_backtest.json` themselves, so the three surfaces can still drift apart. Doing
  the weekly is the small half. The shared helper is the part that stops it recurring.
- **The X character count does not weight URLs.** `_thread_file` uses plain `len()`, so the
  warning at the foot of this file is documented but not implemented. Worse, a post over the
  limit is dropped from the thread silently, so a thread can publish a post short with no
  error. No current thread trips either problem: today's daily, weekly and monthly threads
  max out at 212, 222 and 189 characters with no URLs in the long posts, and nothing is
  being dropped. It is latent, not active, and it will bite the first time a post carries a
  link. Fix both together, and make the drop loud rather than silent.
- **`direction_backtest.json` is a frozen backtest with a review date.** 410 calls at 52
  percent over a window that closed 15 August, flagged `review_after: 2026-10-01`. From
  October it should be refreshed or superseded by the live scoreboard, and until then every
  surface must keep calling it backtested.
- Substack Recommendations not yet switched on.

## What changed on 2026-09-02

Recorded here because it changes how you work in this repo, not because it needs a brief.

- **One writer at a time is now enforced.** `signal_note.py`, `signal_monthly.py` and
  `build_dashboard.py` take an exclusive flock on the tree at startup, via `repo_lock.py`.
  A second generator exits 1 and names the holder. `LEVANTER_LOCK_WAIT=60` waits instead.
  The lock does not cover git, so two sessions can still commit over each other: the
  standing rule in CLAUDE.md still applies.
- **A broken feed now stops a build.** `source_guard.py` declares what each publication
  cannot be written honestly without and fails loudly. It exists because a failed rebase
  left git conflict markers in `crypto_map.json` and a Signal was written anyway, silently
  losing its cross-asset correlation paragraph.
- **Past issues can be regenerated faithfully.** `signal_monthly.py --as-of <ISO>` pins the
  capture time, so rebuilding August in September stamps and differences as August rather
  than as today.
- **The monthly review freezes on publication day.** It upserts while the month runs, then
  freezes from the 28th, so the website copy and the piece sent to Substack stop drifting
  apart. `MONTHLY_PUBLISH_DAY` is shared by the freeze and the publish gate.

## One thing worth knowing before writing anything for X

X weights every URL at 23 characters whatever its real length. A plain character count
will pass a post that X rejects. This caught the launch post at 277 by a normal count and
281 by X's.
