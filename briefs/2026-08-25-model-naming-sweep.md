# Brief for Claude Code: Levanter, model-naming correction sweep

Two tasks. Task A is a correctness sweep and is the reason this brief exists.
Task B is one decision I need reported, not made.

Start by reading and reporting, not editing. Tell me which files generate prose
that mentions either bitcoin valuation model, which of them are generator source
versus emitted output, and where the chart images are produced. If anything below
contradicts the repo, the repo wins. Say so rather than working around it.

---

## The claim being removed

An earlier pass introduced a distinction that is false: that the two bitcoin
models differ by what they measure price against, one against the size of the
network and the other against the calendar or time.

They do not differ that way. `btc_metcalfe.py` regresses log price on
log((date - GENESIS).days). `cycle_gauge.py` does the same thing. Same variable,
same functional form.

What actually differs:

1. Price history: blockchain.info versus yfinance.
2. Band definition: 5th/95th residual percentile versus one standard deviation.
3. The cycle gauge adds halving timing to classify a phase.

That is also the real reason the two percentages sit a point apart.

Agreed names: **the valuation fit** and **the cycle gauge**.

And the consequence that must survive into the prose: because they are the same
kind of fit over overlapping data, close agreement between them is close to
guaranteed. It is not coincidence, and it is not confirmation. A reader must not
take 42 and 43 as two independent readings.

---

## TASK A: Sweep every prose surface

The Signal and the dashboard cards are already done. The pieces below were
"fixed" in the earlier pass and therefore now carry the false distinction. This
is worse in the monthly than in the Signal, because the monthly is the piece
going to LinkedIn.

### A1. Grep for the false claim

Run these across the whole repo, generator source and emitted output alike:

```
network-adoption        network adoption       network-value        network value
against the calendar    rather than the calendar
time-based cycle        time based cycle
rather than network size                        size of its network
price to network size   fit of price to time
power-law               power law               powerlaw
adoption fair value     adoption floor          adoption model
coincidence
```

For each hit, report the file, the line, whether it is generator source or
generated output, and the surrounding sentence. Do not edit yet.

`coincidence` matters because the earlier fix may have said the two figures
agreeing is coincidence. That is also wrong, for the opposite reason.

`fit of price to time` is **correct** and should be left alone. It is listed so
you check each instance rather than assume.

### A2. Fix generator source, not output

Every change goes in the code or template that emits the string. If you fix an
emitted `.md` or `.docx` in `reports/` without fixing the generator, it returns
on the next build. Where an emitted artefact is committed and served, regenerate
it after fixing the source rather than hand-editing it.

Known pieces to check, at minimum: the weekly review, the monthly review, the
monthly LinkedIn post, the Signal note and teaser, the daily note, the About
copy, `llms.txt`, and any dashboard panel text not already covered by the card
rename.

### A3. The chart image, which grep will not find

`X20.png` / `X21.png` carry a matplotlib title reading **"Bitcoin vs long-term
adoption fair value (power law)"**, with legend entries "Adoption fair value" and
"Adoption floor (95%)". Those strings are baked into the PNG, so the sweep above
misses them, and they contradict the new vocabulary on the very slide that
explains it.

Retitle in the plotting code and regenerate:

- Title: `Bitcoin vs the valuation fit`
- Legend: `BTC price`, `Valuation fit`, `Fit floor (5th percentile)`

Check the floor label against what the code actually computes before you write
it. If the band is the 5th/95th residual percentile, say percentile. Do not
copy my suggested label if it does not match the code.

### A4. Consistency check on the surviving vocabulary

After the sweep, exactly two names should appear anywhere in prose: **the
valuation fit** and **the cycle gauge**. Report any third name still in use.

---

## TASK B: The Editor's read, report do not decide

The 24 August Signal opened with an EDITOR'S READ block. The 25 August issue does
not have one. Tell me:

1. Was it removed deliberately, or did it drop out during regeneration?
2. Is it hand-written, or generated from a template? If generated, paste the
   template and tell me how much it varies week to week.

Do not restore it or delete it. I want the answer before deciding.

---

## Verification before you report back

Run these and show the output. Do not report success on anything unchecked.

1. Every grep term in A1 returns zero hits in prose, except `fit of price to
   time` where it is accurate. Show the count per term.
2. The regenerated chart PNG carries the new title and legend. Show it.
3. The site builds and deploys clean.
4. `/reviews/` still shows one weekly, and the weekly-freeze convention from the
   last brief still holds. This is the first build since that change.
5. Both model names resolve to exactly one meaning across dashboard, daily,
   weekly, monthly, Signal and promo copy.

---

## What to send back to me

- The regenerated 25 August Signal PDF.
- The regenerated chart PNG.
- A table: file, line, before string, after string, for every edit.
- The Task B answer.
- The grep counts from verification step 1.

I will re-diff the Signal against my LinkedIn carousel and Substack version and
merge, so the PDF matters more than a summary of it.

---

## Out of scope

- Do not rename anything on the volatility model or the direction scoreboard.
  This sweep is about the two bitcoin valuation surfaces only.
- Do not change any figure, band, or model parameter. Names and prose only.
- Do not restore or remove the Editor's read.
- Everything fenced off in the previous brief stays fenced: no author byline,
  JSON-LD Block 3 stays commented, no per-market pages, no affiliate copy,
  nothing on the Substack.
