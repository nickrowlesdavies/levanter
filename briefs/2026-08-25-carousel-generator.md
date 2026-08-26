# Brief for Claude Code: wire the LinkedIn carousel into the pipeline

One task. Small, but it closes a gap where an artefact we publish has no generator.

Read and report first. Tell me how `signal_pdf.py` builds its HTML and turns it into a
PDF, and whether it can be extended or whether a sibling script is cleaner. If anything
below contradicts the repo, the repo wins.

---

## The gap

`reports/linkedin/levanter-signal-carousel-20260824.pdf` is a nine-slide LinkedIn document
post built for the week-of-24-August Signal. Its source is committed beside it as
`levanter-signal-carousel-20260824.html`.

That HTML was hand-built outside the repo and its content is hardcoded to this week. So
next week the carousel cannot be regenerated. Every other Signal surface regenerates from
`signal_note.py`. This one does not, which means it goes stale silently or gets rebuilt by
hand each week.

## What to build

A generator, `signal_carousel.py`, that emits the carousel PDF from the same data the
Signal already uses, on the same run.

- Read the same source `signal_note.py` reads. Do not re-derive figures, and do not read
  them out of the Signal markdown by regex. Same inputs, same numbers, or the carousel
  and the note can disagree.
- Render nine slides at **1080 x 1350** (4:5 portrait, which is what LinkedIn favours on
  mobile). The committed HTML has the layout, the brand tokens and the slide order.
- Output to `reports/linkedin/levanter-signal-carousel-<date>.pdf`, matching the naming
  the other Signal artefacts use.
- Wire it into `cloud_build.sh` next to the Signal steps.

## Slide order, which is deliberate

1. Cover, gradient, lockup, cadence line, free-while-we-build framing
2. The one chart, with the valuation-fit caption
3. What it cannot do
4. Two numbers, one kind of fit: the 42/43 point
5. The seven-day volatility map
6. The loudest read
7. The direction scorecard, gradient, the large percentage
8. The claim we score next week
9. Subscribe, gradient, lockup

Slide 4 exists because two near-identical percentages read as corroboration when they are
the same fit run twice. Slide 8 is the commitment. Neither should be dropped when the
content is parameterised.

## Brand tokens, already in the HTML

Gradient `#0EA5E9` to `#6366F1`. Ink `#0B1F3A`. Accent `#2890F0`. Pale `#D6E6FD`.
White lockup and mark. Use `brand/levanter-signal-lockup.svg` and the existing Signal
SVGs rather than the raster copies in the committed HTML.

## Two things to decide and report, not action

1. **The Editor's line.** If it is supplied via `--editor`, the carousel should gain a
   slide for it at position 2, and the deck becomes ten. Tell me whether that is easy to
   make conditional.
2. **`reports/linkedin/levanter-signal-reshare-<date>.md`** and the post copy in
   `docx/levanter-signal-linkedin-post-<date>.docx` are hand-written, not generated. Say
   whether you think they should be templated like the teasers, or left hand-written
   because the reshare carries a personal argument each week.

## Verification

1. Run the generator standalone. Nine slides, 1080x1350, no missing figures.
2. Every figure on the deck matches the same figure in `reports/signals/levanter-signal-<date>.md`.
   Show the comparison rather than asserting it.
3. Run `cloud_build.sh` end to end and confirm the carousel lands with the rest.

## Out of scope

- Do not change any figure, model, band or name.
- Do not touch the Signal note, teasers, dashboard or reviews.
- Everything fenced in the previous two briefs stays fenced.
