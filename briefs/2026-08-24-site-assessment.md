# Levanter: site assessment

24 August 2026

Reviewed: levantermarkets.com, levantermarkets.com/app/, read.levantermarkets.com, the
domain's RDAP registration record, and the business plan, marketing plan, LinkedIn pack,
launch post, Signal teaser and the three current review files.

---

## 1. The short version

The product is better than its packaging. The dashboard is dense, the positioning is
sharp, and the volatility numbers are specific enough to be checked, which is rare in
this category. What is missing is everything that lets a stranger, a search engine or an
AI assistant find the site and decide it is real. There is no sitemap, no robots.txt, no
structured data, no named human, and no crawlable URL for a single piece of the written
analysis the marketing plan depends on.

None of that is expensive to fix. Most of it is a day's work, and I have written the
files. One item is not a file, and it matters more than the rest: an inconsistency
between the Signal teaser and the live track record page.

---

## 2. What is working

**The positioning holds up.** "Volatility yes, direction no" is a real distinction, not a
marketing line, and the site backs it with numbers at four horizons. Publishing a
direction scoreboard you expect to sit near 50% is something competitors will not
copy, which is what makes it a moat.

**The dashboard earns the visit.** Sixty-two markets on one page, regime labels,
percentile context, stablecoin peg monitoring, and long-horizon bitcoin valuation. The
disclaimers are on every model rather than buried in a footer.

**The cost structure is right.** Free hosting, free data, Cloudflare in front. The
business plan's sequencing, revenue before engineering, is correct for a solo operator
and rare discipline.

**The archive habit is already there.** Daily, weekly and monthly are being produced and
stored. That is the asset. See section 4 for why nothing can currently see it.

---

## 3. The structural problem: none of the writing is a URL

The entire dashboard is one page at `/app/`. Reviews, track record, archive and about are
hash fragments: `#reviews`, `#track`, `#archive`, `#about`.

A hash fragment is not a page. Search engines do not index it separately. An AI assistant
cannot cite it. A reader cannot send someone a link to last Monday's weekly review,
because no such link exists. Every daily note, weekly review and monthly deep dive you
publish disappears into a single URL that changes underneath it.

This collides directly with the marketing plan, whose section 2 banks on SEO and evergreen
content: "your thesis pieces are evergreen and rank over time. The dashboard's data pages
also accrue search traffic." Under the current architecture they cannot. There are two
indexable URLs on the whole site.

The fix, in rough order of effort:

1. Give every archived review its own path. `/reviews/2026-08-24-daily/`,
   `/reviews/2026-08-23-weekly/`, `/reviews/2026-08-monthly/`. A static generator that
   already writes the review markdown can write an HTML page per review at the same time.
2. Give the track record its own page at `/track-record/`. It is the credibility
   centrepiece per your own marketing plan, and it should be a link you can put in a
   LinkedIn bio.
3. Give each market a page. `/crypto/bitcoin/`, `/fx/audjpy/`, `/commodities/platinum/`.
   This is where the long-tail search traffic actually lives, and the data to fill them
   is already being fetched.
4. Regenerate `sitemap.xml` on every build so new review pages get discovered.

Item 1 is the one that pays. Until it is done, the newsletter is the only durable home
for the writing, and Substack owns that audience rather than you.

---

## 4. Trust: an anonymous two-day-old financial domain

The RDAP record for levantermarkets.com:

| Field | Value |
| --- | --- |
| Registered | 22 August 2026 |
| Expires | 22 August 2027 |
| Registrar | GoDaddy.com, LLC (IANA 146) |
| Nameservers | Cloudflare |
| Registrant contact | Redacted for privacy |

Set that beside the site itself: no author name anywhere, no contact address, no company
details, a Substack about page with no byline, and a subject matter that Google
classifies as Your Money or Your Life. That combination is, unfortunately, the exact
signature of a low-quality financial content site. You know the site is honest. Nothing a
machine can read says so.

This is the cheapest large win available, because the credibility already exists and is
simply not on the page. A named author with an Oxford University Press book, thirty years
in legal finance, and a public professional record converts Levanter from anonymous to
attributable in one paragraph.

Whether to attach your name is a disclosure decision, not a technical one, and there are
reasons you might not want a markets side project sitting next to the legal finance day
job. So I have not made the call. What I would say is that the honesty positioning is
harder to sustain anonymously, because the first question a sceptical reader asks is who
is claiming 74%.

Three supporting fixes, all small:

- **Renew the domain for three to five years.** A one-year registration on a finance
  domain is the throwaway pattern. Multi-year is a mild positive signal and costs very
  little.
- **Publish a contact route.** `security.txt` is written and included. An address on the
  About page matters more.
- **Set a canonical.** Both `levantermarkets.com` and `www.levantermarkets.com` serve the
  same page with no `rel=canonical`. Pick one, 301 the other, and add the tag.

---

## 5. The machine layer is missing entirely

Checked and confirmed absent, all returning 404:

| File | Status | Why it matters |
| --- | --- | --- |
| `/robots.txt` | 404 | No crawl guidance, no sitemap pointer, no AI usage preference stated |
| `/llms.txt` | 404 | No structured summary for AI assistants retrieving at query time |
| `/sitemap.xml` | 404 | Nothing tells a crawler what exists |
| JSON-LD structured data | absent | No machine-readable publisher, dataset or method |
| `/.well-known/security.txt` | 404 | No contact route |

I have written all of them. They are in the `site/` folder and drop straight into the
repo root, keeping the `.well-known` directory. Notes on the choices:

**robots.txt** uses a `Content-Signal` line of `search=yes, ai-input=yes, ai-train=no`.
That says: index me, cite me when answering a question, do not absorb me into a training
corpus. Assistants that retrieve and cite (Claude, ChatGPT search, Perplexity) are
allowed by name. Bulk training crawlers (GPTBot, CCBot, Bytespider, meta-externalagent)
are disallowed. If you would rather trade training consent for reach, flip `ai-train` to
`yes` and delete the four disallow blocks. For a publication whose product is judgement
rather than data, keeping the analysis out of training sets is the defensible position.

**llms.txt** is the one worth reading before you ship it. It carries the framing you want
repeated when an assistant summarises Levanter to someone: that direction calls are
experimental by design, that volatility figures are backtested and horizon-specific, and
that dashboard numbers are timestamped rather than durable. Get this file right and you
influence how the site is described in answers you never see.

**JSON-LD** comes in three blocks. Organization and WebSite for the landing page, Dataset
for the dashboard, and an optional Person block for the named author question in section
4. The Person block is commented out. Fill it in or delete it.

One caveat on the sitemap: it lists two URLs, because two URLs is what the site has. It
becomes useful the moment section 3 is done.

The Substack at read.levantermarkets.com is Substack's to configure. You cannot add these
files there, and you do not need to.

---

## 6. Fix this before you post the Signal teaser

The Signal teaser says:

> "Our direction calls, logged and scored in public, sit at 52% across 410 of them.
> Almost exactly a coin flip, and we publish that rather than hide it."

The live track record page says the direction scoreboard is "filling up now", with calls
logged when made and scored at maturity.

Both cannot be true. The domain is two days old, so 410 direction calls cannot have been
logged and scored in public. Either they are backtested, in which case "logged and scored
in public" is the wrong description, or the track record page is understating what is
already recorded.

For most publications this would be a copy nit. For a brand whose entire proposition is
that it does not dress up numbers, it is the one category of error that does real damage,
and it would be sitting in the first paid-tier promotion you run. Resolve the number,
then say precisely which it is: "52% across 410 backtested calls" reads as honest.
"Logged and scored in public" applied to a backtest does not.

While you are in there, the same teaser says bitcoin is "around 43% below its
adoption-trend fair value". The dashboard today shows 45% against the power-law trend,
with adoption-model fair value at $135k against a price near $77k, which is about 43%
below. The two numbers are measuring different things and the teaser does not say which.
Name the model.

---

## 7. Copy and consistency

- **Substack URL.** The LinkedIn launch post points readers to
  `levantermarkets.substack.com`. Everything else uses `read.levantermarkets.com`. Fix
  the launch post before it goes out, so the custom domain gets the links and the
  authority.
- **Substack About page is empty of substance.** It currently carries the tagline and a
  subscribe prompt. It should carry the thesis, the method, the cadence, and the
  scorecard link. It is a page people read before subscribing, and Substack's own
  recommendation engine surfaces it.
- **Watchlist persistence.** The watchlist lives in browser localStorage. That is the
  right call for a no-accounts site, but it is device-bound and vanishes when someone
  clears site data. One line on the page saying so prevents an annoyed reader.

---

## 8. Affiliate: the plan versus the near-term reality

The business plan puts affiliate first and calls it the year-one breadwinner. Two honest
constraints worth planning around.

**Acceptance.** Several of the named partners vet applicants on traffic and site
maturity. A two-day-old domain with no backlink profile will likely be declined by the
exchange programmes and possibly by Amazon Associates, which requires qualifying sales
within a window. Ledger, Trezor and TradingView are the more realistic first
applications. Apply once there is traffic to show, not before, because a decline usually
carries a reapplication delay.

**Regulatory.** This one is yours rather than mine, but it should not go unsaid.
Affiliate links to cryptoasset exchanges, directed at UK consumers, sit close to the FCA's
cryptoasset financial promotions regime, and an "educational, not advice" disclaimer does
not by itself take a promotion outside it. The UAE angle raises the same question from
the other direction given the Dubai company location in the LinkedIn pack. Worth
resolving before the first exchange link goes live rather than after, because the
downside is not a fine so much as the brand damage of having to take it down.

The hardware wallet partners carry none of this and are also the cleanest fit with the
positioning. Start there, as the plan already says.

---

## 9. Where the protocols land

The four documents are now project files, so they apply in every future session in this
project. Two notes on how they interact with Levanter.

**The registers conflict, deliberately.** `ABOUT_ME.md` sets a formal analytical register
with numbered footnotes and no bullet points. Levanter's brand voice is plain English for
a reader who does not want jargon. Both are correct for their own output. The project
instructions block I have written makes the split explicit so a future session does not
average the two into something that suits neither.

**Run the Prose Humanising Protocol over the review templates, once.** The daily, weekly
and monthly reviews are generated from templates, which means any AI-ism in a template
repeats every week for as long as the site runs. A single pass over the generator
strings, rather than over each week's output, fixes it permanently. On a quick read of
today's three files the copy is clean, but the templates are where this is worth checking
properly.

---

## 10. Order I would do it in

**This week, before any promotion.**

1. Resolve the 410 direction calls contradiction (section 6).
2. Fix the Substack URL in the launch post (section 7).
3. Drop in robots.txt, llms.txt, sitemap.xml, security.txt and the JSON-LD (section 5).
4. Set the canonical between apex and www (section 4).
5. Write the Substack About page properly (section 7).

**Next two weeks.**

6. Decide the named-author question and act on it either way (section 4).
7. Renew the domain for multiple years (section 4).
8. Give every archived review its own URL (section 3, item 1).
9. Regenerate the sitemap on each build.

**Next month.**

10. Track record on its own page (section 3, item 2).
11. Per-market pages (section 3, item 3).
12. Apply to Ledger and Trezor, once there is traffic to show (section 8).

Items 1 to 5 are a morning. Item 8 is the one that decides whether the marketing plan's
SEO section is a strategy or a hope.
