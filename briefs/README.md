# Briefs

Written in the Cowork session, for Claude Code to execute. Newest last.

| File | Status | What it covered |
| --- | --- | --- |
| `2026-08-24-site-and-agent-files.md` | done | Direction-call contradiction, Substack URL in the launch post, robots.txt / llms.txt / sitemap / security.txt / JSON-LD, and per-review URLs at `/reviews/<date>-<cadence>/`. |
| `2026-08-25-model-naming-sweep.md` | done | Removing the false claim that the two bitcoin models differ by what they measure against. Agreed names: the valuation fit and the cycle gauge. Retitled `btc_metcalfe.png`. |
| `2026-08-25-carousel-generator.md` | open | Turn the hand-built LinkedIn carousel into `signal_carousel.py` so it regenerates each week from the same data `signal_note.py` uses. |
| `2026-08-25-x-daily-generator.md` | mostly done | Emit a daily X post alongside the daily note. Rotates its lead by what is actually notable rather than a fixed template, and counts characters the way X does. Built in `build_dashboard.py`, writing `reports/x/levanter-x-daily-<date>.md` as a numbered thread. The character counting half is NOT done, see open items. |
| `2026-09-05-off-exchange-section.md` | done | Off-Exchange, a new monthly editorial column on markets that barely trade or do not exist. Copy for issue 1 is committed at `reports/substack/levanter-offexchange-whisky-2026-09-05.md`. Scope line kept; Nick chose to frame Off-Exchange as an explicit aside from crypto/FX/commodities rather than widen the promise. Built as a sibling generator `build_offexchange.py` reading the markdown (no re-keying), reusing the `build_reviews.py` shell/JSON-LD and merging into the one sitemap; pages at `/off-exchange/<date>/` with an index at `/off-exchange/`, its own aside disclaimer, no `source_guard`. Wired into `cloud_build.sh` after `build_reviews.py`. Copy must be `git add -f`'d: the persist force-add does not pick up a hand-written file in gitignored `reports/`. |
| `2026-09-05-off-exchange-weather.md` | open | Off-Exchange No. 2: weather derivatives, the mirror image of whisky (a real, cleared, index-settled market on something intangible that almost nobody knows exists). Copy only, no build work; `build_offexchange.py` already handles the page. The one required step is force-adding the committed markdown + docx, since CI's persist will not. |

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
- ~~The X character count does not weight URLs, and an over-long post is dropped
  silently.~~ **Done 2026-09-02.** `x_text.py` counts the way X does and both renderers
  use it. See the note at the foot of this file, which is now implemented rather than
  only documented.
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

Since 2026-09-02 this is enforced rather than remembered. `x_text.x_len` charges every
link 23, and `x_text.require_fit` raises rather than letting a post through. The launch
post case is a test: 277 plain, 281 as X counts it. Note a long link counts *down*, so a
56-character post carrying a 52-character URL is 27 to X. Hand-written X copy should be
measured with `x_text.x_len`, never `len`.
