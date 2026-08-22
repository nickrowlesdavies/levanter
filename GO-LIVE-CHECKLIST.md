# Go-Live Checklist & Thresholds

The purpose of this document is to make the decision to trade real money
**rule-based, not emotional**. You wrote these criteria while calm; you honour
them later when you're tempted.

## The core principle

The gate is **NOT "did the paper trial make money"**. A few weeks or months of
returns is statistical noise, chasing it is exactly the mistake this whole
project was built to avoid. The gate is:

1. Does the system **operate cleanly**?
2. Does the paper trial **behave consistently** with the validated backtest?
3. Are **you** genuinely ready (capital, discipline, tax, a stop rule)?

You could go live after a profitable trial that was actually broken, or skip a
losing trial that was working perfectly. Judge *behaviour and readiness*, not P&L.

---

## Phase 0 — Minimum trial length

- [ ] The combined portfolio has run forward on paper for **at least 3 months**
      (ideally 6), i.e. ~12–26 weekly rebalances. Less than that tells you almost nothing.

---

## A. Operational reliability (all must pass)

- [ ] Scheduled jobs ran their full cycles with **no errors** in `reports/cron.log`
      (or you ran `./dashboard.sh` reliably on the intended cadence).
- [ ] Signals generated every period without blow-ups (no NaNs, no absurd weights,
      no single position >~50% unexpectedly).
- [ ] You **shadow-traded** on paper: each week you noted the exact trades the
      system said, and they were sensible and executable.
- [ ] The dashboard numbers reconcile with the state files (no silent drift).

## B. Behavioural consistency vs the backtest

The validated walk-forward expectation for the combined portfolio is the yardstick.
The live paper should look like a *sample from the same distribution*, not a different animal.

| Metric | Backtest expectation | Trial red flag (investigate before live) |
|---|---|---|
| Annualised volatility | ~6–9% | Persistently >15% |
| Max drawdown in trial | blend ~-17% worst case | Exceeds **-20%** |
| Trend sleeve behaviour | goes to cash in downtrends | Stays fully invested through an obvious downtrend |
| Weekly turnover | modest, few names change | Churning most positions every week |
| Return character | small, steady grind | Wild swings inconsistent with ~8% vol |

- [ ] No metric above is in "red flag" territory (or if it is, you understand exactly why).

## C. Personal & risk readiness (all must be TRUE)

- [ ] The capital is money you can **genuinely afford to lose**. This is real risk;
      a -20% year is entirely possible.
- [ ] You have checked the **tax and regulatory** treatment for your situation
      (UAE: crypto gains untaxed; confirm ETF/dividend treatment for your account).
- [ ] You have a written **kill-switch**: the drawdown level at which you stop and
      re-evaluate (suggest **-25%** from peak).
- [ ] You commit to following signals **mechanically for a fixed minimum period**
      (suggest 12 months) with **no discretionary overrides**. If you'll override it,
      don't run it.
- [ ] You have decided **position sizing** and the fraction of net worth this represents.

## D. Broker & execution readiness

- [ ] Brokerage account opened and funded (ETF-capable; e.g. Interactive Brokers for UK/UAE).
- [ ] You placed a few **small test trades** and understand the order flow.
- [ ] You understand your real **costs**: commissions, spreads, FX conversion on the account.
- [ ] You can execute the weekly rebalance in ~10 minutes without stress.

---

## The go-live decision

- [ ] **Every box in A, C, and D is ticked, B shows no unexplained red flags, and
      Phase 0 duration is met.** Only then do you proceed.

## Go live SMALL first

Even after the gate:

- [ ] Start with a **fraction of intended capital** (e.g. 20–25%).
- [ ] Run it live-small for **1–2 months** and confirm live fills, costs, and behaviour
      match the paper trial.
- [ ] Scale toward full size **only** once live-small tracks paper cleanly.

## Ongoing rules once live (the discipline layer)

- **Kill-switch:** if drawdown from peak hits your written limit (-25% suggested),
  stop, go to cash, and review before restarting. No exceptions.
- **No overrides:** you either follow the signal or you don't run the system.
- **Weekly, not daily:** check and rebalance on schedule; ignore it in between.
- **Annual review:** re-run the walk-forward on fresh data once a year to confirm
  the edge hasn't decayed.

---

## Reference: what "consistent" means

From the honest walk-forward research (the numbers to sanity-check against):

- **Combined portfolio** (core + trend sleeve): Sharpe ~1.08, ~market-like return at
  low vol, drawdowns materially smaller than buy-and-hold. **The edge is a smoother
  ride, not outsized returns.** If you're expecting to get rich, you'll quit in the
  first rough patch and lose. Expect boring. Boring is the point.
