# Levanter (fx-signal-engine)

Market intelligence across crypto, foreign exchange and commodities. A static dashboard at
levantermarkets.com built from public data, plus a Substack at read.levantermarkets.com.

The product is honesty about what is and is not forecastable. Volatility is forecast because
it can be. Direction is not, and the scorecard proving that is published. Every convention
below exists to stop a number looking stronger than it is.

---

## Two agents work in this repo

**Claude Code** owns the repo. Generators, models, builds, deploys, git. Anything that
regenerates is its lane: `signal_note.py`, `build_dashboard.py`, `build_reviews.py`,
`btc_metcalfe.py`, `cycle_gauge.py`, `signal_pdf.py`, `cloud_build.sh`, `src/`, `static/`,
`public/`, and every committed JSON the build reads or writes.

**Claude in Cowork** owns hand-built publishing assets and the argument-carrying copy that
no generator produces: the LinkedIn carousel, X cards, reshare commentary, post captions,
briefs, and review of what actually shipped. It writes only into `reports/<channel>/` and
`briefs/`. It never edits generator source.

### Rules that keep this from breaking

1. **One at a time, and now enforced.** `signal_note.py`, `signal_monthly.py` and
   `build_dashboard.py` take an exclusive lock on the working tree at startup via
   `repo_lock.py`. A second generator exits 1 and names the process holding it. Set
   `LEVANTER_LOCK_WAIT=60` to wait instead of failing; cron jobs should. The lock is an
   flock, so a killed run cannot strand it and there is nothing to clear by hand.
   Asking politely was not enough: on 2026-09-02 two sessions here produced a commit
   importing an untracked module, repeated rebase conflicts, and a `crypto_map.json`
   full of git conflict markers that came one run short of being published. The lock
   covers the generators, not git, so **still do not run two sessions here**: nothing
   stops two agents committing and rebasing over each other.
2. **Claude Code owns git.** Cowork writes files into the working tree but does not commit.
   After a Cowork session writes, Claude Code reviews and commits them.
3. **Read the repo, not an upload.** A build can move figures within minutes. Never work
   from a PDF or markdown file pasted into a chat. Stage the current file from disk.
4. **Never hand-edit downstream of a generator.** If a generated file is wrong, the
   generator is wrong. No fourth copy of a document that already has three.
5. **Commit the source of anything hand-built.** If only one agent can rebuild an artefact,
   it will go stale. The carousel HTML is committed for this reason and is being promoted
   to `signal_carousel.py`.

---

## Layout

- Generators and scripts at root.
- `reports/<channel>/` for published output: `linkedin/`, `substack/`, `signals/`, `x/`,
  `marketing/`. Each has `docx/` and, where relevant, `pdf/` subdirectories.
- Naming: `levanter-<thing>-<date>`, ISO date, hyphenated.
- `brand/` for logos and generators of brand assets. SVG preferred over raster.
- `briefs/` for instructions written in one session for the other to execute. See its README
  for status and open items.

---

## Standing content rules

These are correctness rules, not style preferences. Breaking one ships a false claim.

**The two bitcoin models are "the valuation fit" and "the cycle gauge".** Both regress log
price on log network age. They differ only by price source, band definition, and the cycle
gauge's halving-phase logic. Their agreement is therefore close to guaranteed and must never
be presented as corroboration. Do not describe one as measuring against the network and the
other against the calendar. That distinction is false and was published once already.

**The direction scorecard quotes all three rows** with the commodities caveat attached:
crypto over its sample, commodities over its sample and why the higher figure is not an edge,
FX not yet scored. Never a blended figure. Never a bare 62%. Render it from one shared helper
reading `direction_backtest.json` so the dashboard, Signal and teasers cannot drift.

**Backtested is not live.** Say which. "52% across 410 backtested calls" is honest.
"Logged and scored in public" applied to a backfill is not, and shipped once.

**Every figure is stamped to a period.** Cite the horizon with the number: "74% at 90 days",
not "74% accurate".

**Everything is educational, not financial advice.** On every surface, no exceptions.

---

## Prose rules for anything reader-facing

No filler adjectives (genuinely, truly, incredibly, absolutely, fundamentally, essentially).
No filler verbs (navigate, delve into, unpack, unravel). No buzzwords (testament to, nuanced,
compelling, pivotal, transformative). No hedges (somewhat, perhaps, appeared to). Em-dashes
capped at 8 per 5,000 words. Sparing colons and semicolons. Vary sentence length and openings.

The brand voice is plain English for a reader who does not want jargon. That is deliberately
not the formal register used elsewhere by the author.
