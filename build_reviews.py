#!/usr/bin/env python3
"""Generate one indexable HTML page per review, plus a reviews index and a
sitemap, from review_archive.json. Plain generated HTML, no framework.

URL scheme (trailing slash, directory + index.html so GitHub Pages needs no
server config):
    /reviews/2026-08-24-daily/
    /reviews/2026-08-17-weekly/     (weekly anchored to its ISO-week Monday)
    /reviews/2026-08-monthly/
    /reviews/                        (index, reverse chronological)

Content is the review's own rendered HTML from the archive, not rewritten. The
title and meta description are derived from the review's first paragraph.

    python build_reviews.py [OUT_ROOT]     # default OUT_ROOT = public
"""
import datetime as dt
import html as _html
import json
import os
import re
import sys

BASE = "https://levantermarkets.com"
ARCHIVE = "review_archive.json"
OG = f"{BASE}/og.png"
DISCLAIMER = ("Educational market analysis across crypto, foreign exchange and "
              "commodities. Historical moves and mechanical signals only, not forecasts, "
              "not financial advice.")


def _strip(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s)).strip()


def _first_para(htmltext):
    m = re.search(r'class="pc-stand">(.*?)</p>', htmltext, re.S)
    if not m:
        m = re.search(r'class="revd">(.*?)</div>', htmltext, re.S)
    if not m:
        m = re.search(r"<p[^>]*>(.*?)</p>", htmltext, re.S)
    return _strip(m.group(1)) if m else _strip(htmltext)


def _trim(s, n):
    if len(s) <= n:
        return s
    cut = s[:n].rsplit(" ", 1)[0]
    return cut.rstrip(".,;: ") + "…"


def _monday(week_key):
    return dt.datetime.strptime(week_key + "-1", "%G-W%V-%u").date()


def slug(cadence, key):
    if cadence == "weekly":
        return f"{_monday(key).isoformat()}-weekly"
    return f"{key}-{cadence}"          # daily key is a date, monthly key is YYYY-MM


def pub_date(cadence, entry, key):
    if cadence == "daily":
        return entry.get("date", key)
    if cadence == "weekly":
        return _monday(key).isoformat()
    return f"{key}-01"                 # monthly: first of month


def load_reviews():
    try:
        a = json.load(open(ARCHIVE))
    except Exception:
        return []
    out = []
    for cadence in ("daily", "weekly", "monthly"):
        for key, entry in (a.get(cadence, {}) or {}).items():
            body = entry.get("html", "")
            fp = _first_para(body)
            out.append({
                "cadence": cadence,
                "key": key,
                "slug": slug(cadence, key),
                "date": pub_date(cadence, entry, key),
                "label": entry.get("label", key),
                "title": entry.get("title", ""),
                "html": body,
                "first_para": fp,
            })
    out.sort(key=lambda r: (r["date"], r["cadence"]))
    return out


MARK = ('<svg viewBox="0 0 120 120" width="30" height="30" aria-hidden="true">'
        '<defs><linearGradient id="lm" x1="0" y1="0" x2="1" y2="1">'
        '<stop offset="0" stop-color="#0ea5e9"/><stop offset=".55" stop-color="#3b82f6"/>'
        '<stop offset="1" stop-color="#6366f1"/></linearGradient></defs>'
        '<rect x="6" y="6" width="108" height="108" rx="28" fill="url(#lm)"/>'
        '<g fill="none" stroke="#fff" stroke-linecap="round">'
        '<path d="M28 80 C50 71 66 71 86 76" stroke-width="8" opacity=".5"/>'
        '<path d="M28 60 C54 48 74 48 96 55" stroke-width="8.5"/>'
        '<path d="M28 40 C46 33 60 33 76 37" stroke-width="8" opacity=".82"/></g>'
        '<path d="M86 46 l14 -6 -4 14" fill="none" stroke="#fff" stroke-width="8" '
        'stroke-linecap="round" stroke-linejoin="round"/></svg>')


def _head(title, desc, canonical, extra=""):
    t = _html.escape(title)
    d = _html.escape(desc)
    return f"""<!doctype html><html lang="en-GB"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{t}</title>
<meta name="description" content="{d}">
<link rel="canonical" href="{canonical}">
<link rel="icon" href="{BASE}/assets/levanter-logo-square.png">
<meta property="og:type" content="article">
<meta property="og:site_name" content="Levanter">
<meta property="og:title" content="{t}">
<meta property="og:description" content="{d}">
<meta property="og:url" content="{canonical}">
<meta property="og:image" content="{OG}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{t}">
<meta name="twitter:description" content="{d}">
<meta name="twitter:image" content="{OG}">
<link rel="stylesheet" href="{BASE}/reviews/reviews.css">
{extra}</head><body>"""


def _chrome_top():
    return (f'<header class="site"><a class="brand" href="{BASE}/">{MARK}'
            f'<span>Levanter</span></a><nav><a href="{BASE}/reviews/">Reviews</a>'
            f'<a href="{BASE}/app/">Dashboard</a></nav></header>')


def _footer():
    y = "2026"
    return (f'<footer class="site"><p class="disc">{_html.escape(DISCLAIMER)}</p>'
            f'<p class="cr">&copy; {y} Levanter. <a href="{BASE}/app/">Live dashboard</a> '
            f'&middot; <a href="{BASE}/reviews/">All reviews</a></p></footer>')


def review_page(r, prev, nxt):
    cad = r["cadence"].capitalize()
    h1 = f"{cad} review, {r['label']}"
    title = _trim(r["first_para"], 65) + " · Levanter"
    desc = _trim(r["first_para"], 155)
    canonical = f"{BASE}/reviews/{r['slug']}/"
    headline = _html.escape(h1)
    article_ld = (
        '<script type="application/ld+json">'
        + json.dumps({
            "@context": "https://schema.org",
            "@type": "Article",
            "headline": h1,
            "datePublished": r["date"],
            "url": canonical,
            "mainEntityOfPage": canonical,
            "image": OG,
            "publisher": {"@id": f"{BASE}/#organization"},
            "isAccessibleForFree": True,
            "inLanguage": "en-GB",
        }, ensure_ascii=False)
        + "</script>")
    nav = '<nav class="pn">'
    if prev:
        nav += f'<a class="prev" href="{BASE}/reviews/{prev["slug"]}/">&larr; {_html.escape(prev["label"])}</a>'
    if nxt:
        nav += f'<a class="next" href="{BASE}/reviews/{nxt["slug"]}/">{_html.escape(nxt["label"])} &rarr;</a>'
    nav += "</nav>"
    body = (
        f'{_head(title, desc, canonical, article_ld)}'
        f'{_chrome_top()}'
        f'<main class="review"><div class="eyebrow">{cad} review</div>'
        f'<h1>{headline}</h1>'
        f'<div class="pub"><time datetime="{r["date"]}">{_html.escape(r["label"])}</time></div>'
        f'<article class="rc">{r["html"]}</article>'
        f'<p class="disclaimer">{_html.escape(DISCLAIMER)}</p>'
        f'{nav}'
        f'<p class="back"><a href="{BASE}/app/">Explore the live dashboard &rarr;</a></p>'
        f'</main>{_footer()}</body></html>')
    return body


def index_page(reviews):
    canonical = f"{BASE}/reviews/"
    title = "Reviews · Levanter"
    desc = ("Every Levanter daily, weekly and monthly market review, newest first. "
            "Honest analysis across crypto, FX and commodities.")
    items = ""
    for r in sorted(reviews, key=lambda x: (x["date"], x["cadence"]), reverse=True):
        items += (
            f'<li class="ri"><a href="{BASE}/reviews/{r["slug"]}/">'
            f'<span class="cad {r["cadence"]}">{r["cadence"]}</span>'
            f'<span class="rl">{_html.escape(r["label"])}</span>'
            f'<span class="rp">{_html.escape(_trim(r["first_para"], 110))}</span></a></li>')
    listhtml = items or '<li class="ri">No reviews yet.</li>'
    return (
        f'{_head(title, desc, canonical)}'
        f'{_chrome_top()}'
        f'<main class="review"><div class="eyebrow">Archive</div>'
        f'<h1>Reviews</h1>'
        f'<p class="lead">Every daily, weekly and monthly review, newest first. '
        f'The live data lives on the <a href="{BASE}/app/">dashboard</a>.</p>'
        f'<ul class="rlist">{listhtml}</ul>'
        f'</main>{_footer()}</body></html>')


def sitemap(reviews):
    def url(loc, lastmod=None, freq=None, pri=None):
        s = f"  <url>\n    <loc>{loc}</loc>\n"
        if lastmod:
            s += f"    <lastmod>{lastmod}</lastmod>\n"
        if freq:
            s += f"    <changefreq>{freq}</changefreq>\n"
        if pri:
            s += f"    <priority>{pri}</priority>\n"
        return s + "  </url>\n"
    newest = max((r["date"] for r in reviews), default=None)
    body = url(f"{BASE}/", newest, "weekly", "1.0")
    body += url(f"{BASE}/app/", newest, "daily", "0.9")
    body += url(f"{BASE}/reviews/", newest, "daily", "0.8")
    for r in sorted(reviews, key=lambda x: x["date"], reverse=True):
        body += url(f"{BASE}/reviews/{r['slug']}/", r["date"], "monthly", "0.7")
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            + body + "</urlset>\n")


REVIEWS_CSS = """
:root{--bg:#ffffff;--panel:#f8fafc;--fg:#0f172a;--muted:#64748b;--line:#e2e8f0;--brand:#3b82f6;
  --grad:linear-gradient(120deg,#0ea5e9,#3b82f6 55%,#6366f1);
  --shadow:0 1px 3px rgba(15,23,42,.06),0 8px 24px rgba(15,23,42,.05)}
@media(prefers-color-scheme:dark){:root{--bg:#0b0e14;--panel:#151a23;--fg:#e8edf5;--muted:#8b97a8;
  --line:#232c3a;--shadow:0 1px 2px rgba(0,0,0,.4),0 10px 30px rgba(0,0,0,.35)}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);line-height:1.65;
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif}
a{color:var(--brand);text-decoration:none}a:hover{text-decoration:underline}
header.site,footer.site{max-width:760px;margin:0 auto;padding:18px 20px}
header.site{display:flex;align-items:center;gap:16px;border-bottom:1px solid var(--line)}
header.site .brand{display:flex;align-items:center;gap:9px;font-weight:800;font-size:19px;color:var(--fg)}
header.site .brand:hover{text-decoration:none}
header.site nav{margin-left:auto;display:flex;gap:16px;font-weight:600;font-size:14px}
header.site nav a{color:var(--muted)}
main.review{max-width:760px;margin:0 auto;padding:30px 20px 8px}
.eyebrow{font-size:12px;font-weight:800;letter-spacing:2px;text-transform:uppercase;color:var(--brand)}
main.review h1{font-size:clamp(26px,4vw,36px);line-height:1.15;font-weight:800;letter-spacing:-.5px;margin:8px 0 6px}
.pub{color:var(--muted);font-size:14px;margin-bottom:22px}
.lead{color:var(--muted);font-size:17px}
.rc{font-size:16px}
.rc .piece{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:22px 24px;box-shadow:var(--shadow)}
.rc .pc-kicker{font-size:12px;font-weight:800;letter-spacing:2px;text-transform:uppercase;color:var(--brand)}
.rc .pc-title{font-size:24px;font-weight:800;letter-spacing:-.4px;margin:6px 0 4px}
.rc .pc-date{color:var(--muted);font-size:13px;margin-bottom:14px}
.rc .pc-stand{font-size:18px;font-weight:600;line-height:1.5}
.rc .pc-h{font-size:14px;font-weight:800;text-transform:uppercase;letter-spacing:.6px;color:var(--muted);margin:20px 0 6px}
.rc .pc-cta,.rc .pc-foot{color:var(--muted);font-size:13px;border-top:1px solid var(--line);margin-top:18px;padding-top:12px}
.rc .rev{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px 18px;box-shadow:var(--shadow);margin-bottom:14px}
.rc .revh{font-weight:800;font-size:15px;margin-bottom:7px}
.rc .revb{font-size:14.5px;line-height:1.7}
.rc .revd{margin-bottom:8px}
.rc .mnote{color:var(--muted);font-size:12.5px;margin-top:12px}
.disclaimer{color:var(--muted);font-size:12.5px;border-top:1px solid var(--line);margin-top:26px;padding-top:14px}
.pn{display:flex;justify-content:space-between;gap:14px;margin:22px 0;font-weight:600;font-size:14px}
.pn .next{margin-left:auto;text-align:right}
.back{margin:10px 0 30px;font-weight:700}
.rlist{list-style:none;padding:0;margin:24px 0}
.ri{border:1px solid var(--line);border-radius:12px;margin-bottom:10px;background:var(--panel);box-shadow:var(--shadow)}
.ri a{display:block;padding:14px 16px;color:var(--fg)}.ri a:hover{text-decoration:none;border-color:var(--brand)}
.cad{display:inline-block;font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:.5px;color:#fff;
  background:var(--grad);border-radius:6px;padding:2px 8px;margin-right:10px;vertical-align:middle}
.rl{font-weight:700}.rp{display:block;color:var(--muted);font-size:14px;margin-top:5px}
footer.site{border-top:1px solid var(--line);color:var(--muted);font-size:12.5px;margin-top:20px}
footer.site .cr a{color:var(--brand)}
"""


def write(out_root="public"):
    reviews = load_reviews()
    rev_dir = os.path.join(out_root, "reviews")
    os.makedirs(rev_dir, exist_ok=True)
    open(os.path.join(rev_dir, "reviews.css"), "w").write(REVIEWS_CSS)

    by_cad = {}
    for r in reviews:
        by_cad.setdefault(r["cadence"], []).append(r)
    for cad in by_cad:
        by_cad[cad].sort(key=lambda x: x["date"])

    n = 0
    for r in reviews:
        seq = by_cad[r["cadence"]]
        i = seq.index(r)
        prev = seq[i - 1] if i > 0 else None
        nxt = seq[i + 1] if i < len(seq) - 1 else None
        d = os.path.join(rev_dir, r["slug"])
        os.makedirs(d, exist_ok=True)
        open(os.path.join(d, "index.html"), "w").write(review_page(r, prev, nxt))
        n += 1

    open(os.path.join(rev_dir, "index.html"), "w").write(index_page(reviews))
    open(os.path.join(out_root, "sitemap.xml"), "w").write(sitemap(reviews))
    print(f"build_reviews: wrote {n} review pages + index + sitemap ({len(reviews)} reviews) to {rev_dir}/")
    return reviews


if __name__ == "__main__":
    write(sys.argv[1] if len(sys.argv) > 1 else "public")
