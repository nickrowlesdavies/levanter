# Brief for Claude Code: Levanter

Four tasks, in order. Task 1 is copy and needs a decision from me before you touch it.
Task 3 is the real work. Do not start Task 3 until Tasks 1 and 2 are done and committed.

Before anything else, read the repo and tell me what you found: the build script or
generator that produces the daily, weekly and monthly reviews, where the review markdown
is written, how `app/index.html` is assembled, and whether the build runs on a schedule
or by hand. I have described the site below from the outside. You can see the inside.
If anything here contradicts the repo, the repo wins — say so rather than working around it.

---

## Context

Levanter is a static site on GitHub Pages, Cloudflare DNS, at levantermarkets.com.

- `/` is a landing page.
- `/app/` is the entire dashboard as one page: 35-odd crypto assets, 16 FX pairs, 12
  commodities, volatility regime forecasts, track record, reviews and archive.
- Reviews, track record, archive and about are hash fragments on `/app/`, not pages.
- Daily, weekly and monthly reviews are generated into Markdown and Word on each build.
- The newsletter is a Substack at read.levantermarkets.com. Nothing in this brief touches it.

The brand rule that governs every change: the site's product is honesty about what is and
is not forecastable. Do not add a number, claim or label that is not backed by something
in the repo. If a figure is not available, omit it. Do not fill a gap with a plausible value.

---

## TASK 1: Two copy fixes

### 1a. The direction-call count. Ask me before editing.

`levantersignalteaser.docx` contains:

> "Our direction calls, logged and scored in public, sit at 52% across 410 of them."

The live track record page says the direction-call scoreboard is "filling up now", with
calls logged when made and scored at maturity. The domain was registered on 22 August
2026, so 410 calls cannot have been logged and scored in public.

Find where the 410 and the 52% come from in the repo. Then tell me which of these is true:

- **A.** They are backtested calls over historical data. If so the teaser wording is
  wrong and should read "52% across 410 backtested calls", with "logged and scored in
  public" removed.
- **B.** They are live-logged calls and the track record page is understating what exists.
  If so the track record page needs updating, not the teaser.
- **C.** The numbers do not resolve to anything in the repo. Say so plainly.

Do not pick one and edit. Report what you find and wait.

While you are there: the same teaser says bitcoin is "around 43% below its adoption-trend
fair value". The dashboard shows 45% against the *power-law* trend and a separate
adoption-model fair value. Two different models. Add the model name to the teaser line so
it is unambiguous which one the 43% refers to.

### 1b. Substack URL in the launch post

`levanterlinkedinlaunchpost.docx` says "The writing is at levantermarkets.substack.com".
Everywhere else uses `read.levantermarkets.com`. Change it to `read.levantermarkets.com`.
Grep the whole repo for `substack.com` and fix any other instance of the bare Substack
subdomain in reader-facing copy.

---

## TASK 2: Static discovery files

Five files are supplied in `levanter-site-files.zip`. Extract into the published site root
so they resolve at:

```
/robots.txt
/llms.txt
/sitemap.xml
/.well-known/security.txt
```

The fifth, `jsonld-structured-data.html`, is not a file to deploy. It contains three
`<script type="application/ld+json">` blocks with instructions in comments:

- Block 1 (Organization + WebSite) goes in the `<head>` of the landing page.
- Block 2 (Dataset) goes in the `<head>` of `app/index.html`.
- Block 3 (Person, named author) is commented out. Leave it commented. That is my decision
  to make, not yours.

**GitHub Pages gotcha, do not skip this.** If the site is served through Jekyll, files and
directories beginning with a dot or underscore are excluded from the build, so
`/.well-known/security.txt` will 404 even though it is committed. Add an empty `.nojekyll`
file at the publishing root, or add an explicit `include:` entry in `_config.yml`. Check
which applies here and do it.

Then verify each of the four URLs returns 200 with the right content type after deploy.
`security.txt` must be served as `text/plain`.

**Do not deploy the sitemap as a static file if Task 3 lands.** See Task 3 step 5.

---

## TASK 3: Give every review its own URL

This is the item that matters. Everything currently written on the site lives behind a
hash fragment, which means no review can be indexed, linked to, or cited. Every review
published between now and the fix is a piece of writing that never becomes an asset.

### 3.1 What to build

A generated HTML page per review, written at build time from the Markdown that already
exists. URL scheme:

```
/reviews/2026-08-24-daily/
/reviews/2026-08-23-weekly/
/reviews/2026-08-monthly/
/reviews/                      <- index, reverse chronological, all three cadences
```

Trailing slash, directory with `index.html` inside, so the paths work on GitHub Pages
without server config.

### 3.2 What each review page contains

- The review content, rendered from the existing Markdown. Do not rewrite it.
- An `<h1>` that names the cadence and date.
- A `<title>` and `<meta name="description">` derived from the review's own first
  paragraph. No invented summaries.
- `<link rel="canonical">` pointing at its own absolute URL.
- Published date in a `<time datetime="...">` element.
- The standing disclaimer that appears elsewhere on the site: educational market analysis,
  not financial advice.
- Prev / next links to the adjacent review of the same cadence.
- A link back to the live dashboard at `/app/`.
- Open Graph and Twitter card tags using the existing share-card image.
- `Article` JSON-LD with `datePublished`, `headline`, and `publisher` referencing
  `https://levantermarkets.com/#organization` (the `@id` set by Task 2, Block 1).

Match the existing site CSS. Do not introduce a framework, a build dependency, or a
client-side renderer. Plain generated HTML.

### 3.3 Backfill

Generate pages for every review already in the archive, not just new ones. Use the date
already recorded for each. If a review has no reliable date, list it and ask. Do not guess.

### 3.4 Do not break the dashboard

`/app/` and its hash fragments stay exactly as they are. The archive section inside `/app/`
should now link out to the new `/reviews/...` pages rather than only expanding inline.
Anyone with an existing `/app/#archive` link must still land somewhere sensible.

### 3.5 Sitemap becomes generated

Once review pages exist, `sitemap.xml` must be produced by the build, not committed as a
static file. It should list:

- `/`
- `/app/`
- `/reviews/`
- every `/reviews/<slug>/` page, with `<lastmod>` set from the review date

Replace the static `sitemap.xml` from Task 2 with the generated one. Keep the
`Sitemap:` line in `robots.txt` pointing at the same path.

### 3.6 Canonical host

Both `levantermarkets.com` and `www.levantermarkets.com` currently serve the site and
neither declares a canonical. Pick the apex, 301 the `www` host to it at Cloudflare, and
emit `<link rel="canonical">` on every page including the two existing ones. Every absolute
URL you generate must use the same host.

---

## Verification before you tell me it is done

Run these and show me the output. Do not report success on any item you have not checked.

1. `/robots.txt`, `/llms.txt`, `/sitemap.xml`, `/.well-known/security.txt` each return 200.
2. `sitemap.xml` parses as valid XML and every `<loc>` in it returns 200.
3. Every JSON-LD block on every page parses as valid JSON.
4. A review page picked at random renders correctly, and its canonical, title, date and
   disclaimer are all present and correct for that review.
5. Review count on `/reviews/` equals the number of review Markdown files in the repo.
   If it does not, say by how much and why.
6. `/app/` still loads and every hash fragment still works.
7. `www` redirects to apex with a 301.

---

## Out of scope

Do not do these. They are decisions I have not made yet.

- Adding a named author or byline anywhere, or uncommenting JSON-LD Block 3.
- Per-market pages (`/crypto/bitcoin/` and similar). Later, not now.
- Any affiliate link, disclosure page, or "tools we use" page.
- Anything touching the Substack.
- Changing the volatility or direction models, or any figure they produce.
- Adding analytics beyond what is already there.
