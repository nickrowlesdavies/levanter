# Deploying Levanter to the web (always-on, no Mac needed)

This publishes the **market + analysis** site (Home / Crypto / FX / Commodities /
Reviews) to a free, auto-updating web address using **GitHub Pages + Actions**.
GitHub runs the data scripts on a schedule and rebuilds the page for you, so it
stays fresh whether or not your Mac is on.

The paper-strategy tab is **not** part of the public site (it needs your local
account state) - that stays on your Mac via `./dashboard.sh`.

## What gets published
- `build_dashboard.py --market-only` output only.
- **No secrets.** The public scripts use CoinGecko / yfinance / Binance - not
  your Twelve Data key. `twelvedata.key` and all `*.key` files are git-ignored.
- The repo must be **public** for free Pages (or use a paid plan for private +
  Pages). The Python code will be visible; there are no credentials in it.

## One-time setup

### 1. Create the repo and push
From `fx-signal-engine/`:

```bash
git init
git add .
git commit -m "Levanter: market intelligence site"
git branch -M main
```

Create an empty repo on github.com named e.g. `levanter` (no README), then:

```bash
git remote add origin https://github.com/<your-username>/levanter.git
git push -u origin main
```

### 2. Turn on Pages
Repo **Settings → Pages → Build and deployment → Source: GitHub Actions**.
(That's it - the workflow in `.github/workflows/deploy.yml` does the rest.)

### 3. First deploy
Repo **Actions → "Deploy Levanter" → Run workflow** (or just wait - it also runs
every 6 hours and on every push to `main`).

When it finishes, your site is live at:
```
https://<your-username>.github.io/levanter/
```

## Custom domain (acquired: levantermarkets.com + levanter.market)
Use **`levantermarkets.com`** as the primary (a `.com` is the address people
remember and type), and point **`levanter.market`** at it as a short redirect.

### Primary: levantermarkets.com
1. Create a file named `CNAME` at the repo root containing exactly one line:
   ```
   levantermarkets.com
   ```
   Commit and push it. (The build copies it into the published site.)
2. At the registrar for `levantermarkets.com`, add DNS pointing at GitHub Pages:
   - **Apex** `levantermarkets.com` -> four `A` records:
     `185.199.108.153`, `185.199.109.153`, `185.199.110.153`, `185.199.111.153`
     (and the matching `AAAA` records `2606:50c0:8000/8001/8002/8003::153` if you want IPv6).
   - **www** `www.levantermarkets.com` -> `CNAME` to `<your-username>.github.io`.
3. Repo **Settings → Pages → Custom domain** -> enter `levantermarkets.com`, save,
   and tick **Enforce HTTPS** once the certificate is issued (a few minutes).

### Redirect: levanter.market -> levantermarkets.com
Simplest is a registrar-level forward: in the `levanter.market` DNS/forwarding
panel, set a **301 permanent redirect** (with wildcard/path forwarding) to
`https://levantermarkets.com`. That keeps one canonical site and one SSL cert.
(If your registrar cannot forward, point `levanter.market` at the same four
Pages `A` records and add it as a second custom domain, but a redirect is
cleaner and avoids duplicate-content confusion.)

## Update cadence
- Automatic: every 6 hours (change the `cron:` line in `deploy.yml`).
- Manual: **Actions → Run workflow** any time.
- On push: any commit to `main` triggers a rebuild.

## Local preview of the exact published page
```bash
bash cloud_build.sh          # regenerates data + writes public/index.html
python -m http.server -d public 8899
```
Then open http://localhost:8899/.

## Notes
- Binance order-flow may be geo-blocked on GitHub's US runners; the build is
  best-effort and simply omits that one panel if the feed is unavailable.
- First CI run installs dependencies (~1-2 min); later runs use the pip cache.
