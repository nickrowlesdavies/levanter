# Briefs

Written in the Cowork session, for Claude Code to execute. Newest last.

| File | Status | What it covered |
| --- | --- | --- |
| `2026-08-24-site-and-agent-files.md` | done | Direction-call contradiction, Substack URL in the launch post, robots.txt / llms.txt / sitemap / security.txt / JSON-LD, and per-review URLs at `/reviews/<date>-<cadence>/`. |
| `2026-08-25-model-naming-sweep.md` | done | Removing the false claim that the two bitcoin models differ by what they measure against. Agreed names: the valuation fit and the cycle gauge. Retitled `btc_metcalfe.png`. |
| `2026-08-25-carousel-generator.md` | open | Turn the hand-built LinkedIn carousel into `signal_carousel.py` so it regenerates each week from the same data `signal_note.py` uses. |
| `2026-08-25-x-daily-generator.md` | open | Emit a daily X post alongside the daily note. Rotates its lead by what is actually notable rather than a fixed template, and counts characters the way X does. Sensibly done alongside the carousel generator. |

## Standing conventions these assume

- The repo is the source of truth. Nothing is hand-edited downstream of a generator.
- Anything hand-built gets its source committed, so it can be rebuilt by someone else.
- Channel outputs live under `reports/<channel>/`, with `docx/` and `pdf/` subdirectories,
  named `levanter-<thing>-<date>`.
- The two bitcoin models are always "the valuation fit" and "the cycle gauge". Their
  agreement is never presented as corroboration.
- The direction scorecard quotes all three rows with the commodities caveat attached.
  Never a blended figure, never a bare 62%.

## Open items not yet briefed

- The Signal quotes only the crypto direction row. It should quote all three, rendered
  from one shared helper reading `direction_backtest.json`, so the dashboard, Signal and
  both teasers cannot drift apart.
- Substack Recommendations not yet switched on.

## One thing worth knowing before writing anything for X

X weights every URL at 23 characters whatever its real length. A plain character count
will pass a post that X rejects. This caught the launch post at 277 by a normal count and
281 by X's.
