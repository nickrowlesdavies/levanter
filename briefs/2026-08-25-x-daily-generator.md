# Brief for Claude Code: generate the daily X post

Companion to the carousel-generator brief. Same shape of job, sensibly done together.

Read and report first. Tell me where the daily note is assembled in `signal_note.py` or
`build_dashboard.py`, and what structured data is available at that point (regime flips,
matured calls, peg status, dominance, leaders and laggards). If the repo contradicts
anything below, the repo wins.

---

## Why this exists

Levanter will post to X daily. The daily note already generates, so the content exists.
What does not exist is an X-shaped version of it, and hand-writing one every morning is
the version that stops happening in a busy week.

X is not LinkedIn. Daily is normal there, posts have a half-life of hours rather than days,
and a market-update account is an established format. The constraint is not frequency, it
is that the post must not read like a bot.

## What to build

Emit `reports/x/levanter-x-daily-<date>.md` on the same run that produces the daily note.
One post, ready to paste. Optionally a second, alternate framing, clearly labelled.

## Character budget, and the trap in it

The cap is 280, but **X weights every URL at 23 characters regardless of its real length**.
`levantermarkets.com` is 19 characters and costs 23. A plain `len()` will pass a post that
X rejects. Count with the URL substituted at 23, and assert the result is at most 280
before writing the file.

## Choosing what leads, which is the whole design

Do not use a fixed template. The same three lines in the same order every day is what makes
an account invisible. Pick the lead by walking this priority order and taking the first that
has something real to say today:

1. **A volatility regime flip.** A market newly turbulent, or newly calm. Name it, give the
   current vol against its median.
2. **A matured call, scored.** A prior turbulent-or-calm call that has now resolved, with
   hit or miss stated plainly. This is the strongest recurring format Levanter has and
   nobody else can run it. Prefer it over anything except a live regime flip.
3. **A peg or dominance event.** A tracked stablecoin below 0.995, or a sharp dominance move.
   Rare, so it leads when it happens.
4. **A cross-asset divergence.** Metals and speculative crypto both bid while the dollar is
   quiet, or similar. State the observation and that the tape cannot say which explanation
   is driving it.
5. **Fallback, the board.** Leaders and laggards plus the volatility read. Use this only when
   nothing above fires.

Record which lead was used, so a future run can avoid using the same one four days running
when several are available.

## Format rules

- Lead with the volatility read, not the leaderboard. The leaderboard is commodity content
  that any price bot produces. The regime call is the differentiator.
- Two or three short blocks separated by blank lines. Not a paragraph.
- No hashtags on the daily. They add nothing and read as filler at this frequency.
- **No link on most days.** X suppresses posts whose payload is an outbound link. Emit the
  post without one by default, and include the link only on the days the lead is a scored
  call or a regime flip worth clicking through for. Note in the file whether a link was
  included and why.
- Educational, not financial advice, is implied by the brand rather than repeated in 280
  characters. Do not spend the budget on it.

## Standing content rules that apply here

All of `CLAUDE.md` applies, and two matter especially at this length:

- Never quote a bare commodities direction figure. If the scorecard appears, the caveat
  travels with it, or the figure does not appear at all.
- Say backtested when it is backtested. At 280 characters the temptation to drop the
  qualifier is highest and the cost of dropping it is the same.

## Verification

1. Every generated post passes the X-weighted length check. Show the count.
2. Run it against the last seven days of data. Show the seven posts and which lead each
   used. If more than four use the same lead, the priority order or the variety logic
   needs work, and say so rather than shipping it.
3. Every figure in a post matches the same figure in that day's note.

## Out of scope

- Do not post anything. This generates a file for a human to send.
- Do not change any model, figure or band.
- No threads yet. One post a day, and revisit once there is an audience.
