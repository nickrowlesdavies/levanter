# Brief for Claude Code: give Off-Exchange a home on the site

One task, and a decision for Nick that has to land before you build anything.

Read and report first. Tell me how `build_reviews.py` generates the per-review pages at
`/reviews/<date>-<cadence>/`, and whether a new page type belongs inside that machinery or
beside it. If anything below contradicts the repo, the repo wins.

---

## What Off-Exchange is

A monthly column on markets that barely trade, or that do not exist at all. Decided
5 September 2026. It rides inside the last Signal of the month instead of going out as its
own post, because a new section holding one post has no audience of its own.

Issue 1 is written and sits at `reports/substack/levanter-offexchange-whisky-2026-09-05.md`,
with the docx beside it in `docx/`. It argues that no exchange anywhere lists a whisky
future, and that the absence is itself information: the retail cask trade occupies the space
an exchange would hold if the asset could support one. Issue 2 is weather derivatives.

The copy was hand-written in a Cowork session. Per the standing convention its source is the
markdown committed alongside it. There is no generator here and there should not be one.
This is argument-carrying copy, which is Cowork's lane, and parameterising it would produce
nothing a template can fill.

## The blocker, which is Nick's rather than yours

The landing page promises "Crypto, foreign exchange and commodities read side by side", and
the footer says "Educational market analysis across crypto, FX and commodities". A monthly
column about whisky casks sits outside that promise.

Do not widen the scope line on your own initiative. Either Nick widens it, or Off-Exchange
gets framed on the page as an explicit aside from the three covered asset classes. Ask him
before building.

## What to build, once that is settled

A page type for Off-Exchange at `/off-exchange/<date>/`, with an index at `/off-exchange/`.

- Read the copy from `reports/substack/levanter-offexchange-*.md`. Do not re-key it into a
  template. When the markdown changes, the page changes.
- Reuse whatever `build_reviews.py` already does for per-review pages: the same shell, brand
  tokens, footer, JSON-LD shape and sitemap registration.
- The index lists issues newest first, each with the standfirst line from its file.
- Register the pages in the generated sitemap.

No engine figures appear on these pages, so `source_guard.check_sources` has nothing to
guard. Leave it out, and do not let a stale feed block the build of a page that reads no
feed.

## What not to do

Do not put Off-Exchange on the dashboard, and keep it away from the direction scorecard and
the volatility rows. It carries no forecast and no scored claim, and its separation from the
scored surfaces is the point of it. A reader who cannot tell which parts of Levanter are
being scored is the failure mode.

Do not add an unconditional monthly Off-Exchange step to `cloud_build.sh`. There will be
months with no issue, and a build that expects one will either fail or publish a stale page.

## Naming

`reports/substack/levanter-offexchange-<topic>-<date>.md`, docx beside it in `docx/`,
matching the channel convention.

## Provenance of the copy

Issue 1 passed three gates before it was written into this tree. Every figure, date, proper
name and quotation traced to a named source, and one live error was caught that way: an
earlier draft carried the Scotch Whisky Association's February warning about a 35% US tariff
as though it were current, when Washington had in fact removed the 10% tariff on 24 July
2026. A mechanical scan for the banned constructions and the em-dash cap followed, then the
prose was measured against Nick's own published baseline, all six measures in band.

The harness and its source corpus live at `Documents/Claude/Claude Outputs/Levanter
Off-Exchange`, outside this repo. Three files: a source corpus with verbatim extracts, URLs
and verification dates, an assertion tracer, and a slop-and-voice scanner. If they belong in
the repo, say where. They are not generator source and I have not placed them in one.

## How the copy reaches the repo

`reports/` is gitignored, so both new files show as ignored locally. That is fine and needs
no action from you: the CI workflow already force-adds this channel with
`git add -f reports/substack/*.md reports/substack/docx/*.docx`, and the markdown sits
directly in `reports/substack/` where that glob matches it. The next run picks both up. No
build step deletes the directory, so nothing here is at risk of being regenerated away.

The brief and this README change are the only tracked files touched. No generator source was
edited, and nothing was committed from the Cowork session.
