#!/usr/bin/env python3
"""Generate the Off-Exchange section: one indexable HTML page per issue at
/off-exchange/<date>/, plus an index at /off-exchange/, and register both in the
one generated sitemap.xml.

Off-Exchange is a monthly editorial aside on markets that barely trade or do not
exist at all. It is deliberately OUTSIDE the crypto/FX/commodities scope line the
rest of the site promises, so every page frames itself as an aside and carries a
disclaimer that does NOT claim its subject is one of the three covered classes.

The copy is hand-written and committed as markdown under
reports/substack/levanter-offexchange-<topic>-<date>.md. This reads that markdown
and wraps it in the shared site shell; it never re-keys or parameterises the copy.
When the markdown changes, the page changes. There is no engine figure on these
pages, so source_guard has nothing to guard and is intentionally not called: a
stale market feed must never block a page that reads no feed.

The shell (head, brand mark, top chrome, footer, JSON-LD shape) and the sitemap
are reused from build_reviews.py so the two page types cannot drift apart.

    python build_offexchange.py [OUT_ROOT]     # default OUT_ROOT = public
"""
import datetime as dt
import glob
import html as _html
import json
import os
import re
import sys

import build_reviews as br

BASE = br.BASE
OG = br.OG
SRC_GLOB = "reports/substack/levanter-offexchange-*.md"

# The aside framing (shown on every page and the index) and a matching footer
# disclaimer. Both keep the site's scope line honest: Off-Exchange is separate
# from the three covered asset classes, not an addition to them.
ASIDE = ("Off-Exchange is a monthly aside on markets that barely trade, or do not exist at all. "
         "It sits outside the crypto, foreign exchange and commodities Levanter covers and "
         "scores, and carries no forecast.")
DISCLAIMER = ("Off-Exchange is an editorial aside, separate from the crypto, foreign exchange and "
              "commodities Levanter covers and scores. Educational writing only, no forecast, not "
              "financial advice.")


def _inline(s):
    """Escape text, then apply the light markdown the copy uses (**bold**, *italic*)."""
    s = _html.escape(s, quote=False)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"\*(.+?)\*", r"<i>\1</i>", s)
    return s


def _render_body(text):
    """Block-level render of the copy below the standfirst: ## headings, --- rules,
    and paragraphs. Blocks are separated by blank lines."""
    parts = []
    for block in re.split(r"\n\s*\n", text):
        b = block.strip()
        if not b:
            continue
        if b == "---":
            parts.append("<hr>")
        elif b.startswith("## "):
            parts.append(f"<h2>{_inline(b[3:].strip())}</h2>")
        else:
            para = " ".join(line.strip() for line in b.splitlines())
            parts.append(f"<p>{_inline(para)}</p>")
    return "".join(parts)


def _parse(path):
    raw = open(path).read()
    fname = os.path.basename(path)
    m = re.search(r"levanter-offexchange-(.+)-(\d{4}-\d{2}-\d{2})\.md$", fname)
    topic = m.group(1) if m else ""
    date = m.group(2) if m else ""

    h1 = series = standfirst = ""
    body_lines = []
    for line in raw.splitlines():
        st = line.strip()
        if not h1 and st.startswith("# "):
            h1 = st[2:].strip()
            continue
        if not series and st.startswith("*") and not st.startswith("**") \
                and st.endswith("*") and "Off-Exchange" in st:
            series = st.strip("*").strip()
            continue
        if not standfirst and st.startswith("**") and st.endswith("**"):
            standfirst = st.strip("*").strip()
            continue
        body_lines.append(line)

    nm = re.search(r"No\.\s*(\d+)", series)
    number = int(nm.group(1)) if nm else None
    return {
        "path": path, "topic": topic, "date": date, "h1": h1,
        "series": series, "number": number, "standfirst": standfirst,
        "body_html": _render_body("\n".join(body_lines)),
    }


def _label(date):
    try:
        return dt.date.fromisoformat(date).strftime("%-d %B %Y")
    except ValueError:
        return date


def load_issues():
    issues = [_parse(p) for p in glob.glob(SRC_GLOB)]
    issues = [i for i in issues if i["date"]]
    issues.sort(key=lambda i: i["date"])
    # Fill any missing issue number from chronological position (1 = oldest).
    for pos, it in enumerate(issues, start=1):
        if it["number"] is None:
            it["number"] = pos
    return issues


def issue_page(it, prev, nxt):
    canonical = f"{BASE}/off-exchange/{it['date']}/"
    title = br._trim(it["h1"], 65) + " · Off-Exchange · Levanter"
    desc = br._trim(_html.unescape(re.sub("<[^>]+>", "", it["standfirst"])) or it["h1"], 155)
    eyebrow = f"Off-Exchange · No. {it['number']}"
    article_ld = (
        '<script type="application/ld+json">'
        + json.dumps({
            "@context": "https://schema.org",
            "@type": "Article",
            "headline": it["h1"],
            "datePublished": it["date"],
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
        nav += (f'<a class="prev" href="{BASE}/off-exchange/{prev["date"]}/">'
                f'&larr; No. {prev["number"]}</a>')
    if nxt:
        nav += (f'<a class="next" href="{BASE}/off-exchange/{nxt["date"]}/">'
                f'No. {nxt["number"]} &rarr;</a>')
    nav += "</nav>"
    stand = f'<p class="oe-stand">{_inline(it["standfirst"])}</p>' if it["standfirst"] else ""
    return (
        f'{br._head(title, desc, canonical, article_ld)}'
        f'{br._chrome_top()}'
        f'<main class="review"><div class="eyebrow">{_html.escape(eyebrow)}</div>'
        f'<h1>{_html.escape(it["h1"])}</h1>'
        f'<div class="pub"><time datetime="{it["date"]}">{_html.escape(_label(it["date"]))}</time></div>'
        f'<p class="oe-aside">{_html.escape(ASIDE)}</p>'
        f'{stand}'
        f'<article class="oe">{it["body_html"]}</article>'
        f'<p class="disclaimer">{_html.escape(DISCLAIMER)}</p>'
        f'{nav}'
        f'<p class="back"><a href="{BASE}/off-exchange/">All Off-Exchange &rarr;</a></p>'
        f'</main>{br._footer(DISCLAIMER)}</body></html>')


def index_page(issues):
    canonical = f"{BASE}/off-exchange/"
    title = "Off-Exchange · Levanter"
    desc = br._trim(ASIDE, 155)
    items = ""
    for it in sorted(issues, key=lambda x: x["date"], reverse=True):
        stand = _html.unescape(re.sub("<[^>]+>", "", it["standfirst"]))
        items += (
            f'<li class="ri"><a href="{BASE}/off-exchange/{it["date"]}/">'
            f'<span class="cad monthly">No. {it["number"]}</span>'
            f'<span class="rl">{_html.escape(it["h1"])}</span>'
            f'<span class="rp">{_html.escape(br._trim(stand, 140))}</span></a></li>')
    listhtml = items or '<li class="ri">No issues yet.</li>'
    return (
        f'{br._head(title, desc, canonical)}'
        f'{br._chrome_top()}'
        f'<main class="review"><div class="eyebrow">Aside</div>'
        f'<h1>Off-Exchange</h1>'
        f'<p class="oe-aside">{_html.escape(ASIDE)}</p>'
        f'<ul class="rlist">{listhtml}</ul>'
        f'</main>{br._footer(DISCLAIMER)}</body></html>')


def sitemap_extra(issues):
    """(loc, lastmod, changefreq, priority) tuples for build_reviews.sitemap()."""
    if not issues:
        return []
    newest = max(i["date"] for i in issues)
    extra = [(f"{BASE}/off-exchange/", newest, "monthly", "0.6")]
    for it in sorted(issues, key=lambda x: x["date"], reverse=True):
        extra.append((f"{BASE}/off-exchange/{it['date']}/", it["date"], "yearly", "0.6"))
    return extra


def write(out_root="public"):
    issues = load_issues()
    if not issues:
        print("build_offexchange: no issues found, nothing written (reviews sitemap left intact)")
        return []
    oe_dir = os.path.join(out_root, "off-exchange")
    os.makedirs(oe_dir, exist_ok=True)
    for i, it in enumerate(issues):
        prev = issues[i - 1] if i > 0 else None
        nxt = issues[i + 1] if i < len(issues) - 1 else None
        d = os.path.join(oe_dir, it["date"])
        os.makedirs(d, exist_ok=True)
        open(os.path.join(d, "index.html"), "w").write(issue_page(it, prev, nxt))
    open(os.path.join(oe_dir, "index.html"), "w").write(index_page(issues))

    # Rewrite the one sitemap as the union of reviews + Off-Exchange. This runs
    # after build_reviews.py in cloud_build.sh, so this is the final, complete
    # sitemap; running build_reviews alone still writes a valid reviews-only one.
    reviews = br.load_reviews()
    sm = br.sitemap(reviews, extra=sitemap_extra(issues))
    open(os.path.join(out_root, "sitemap.xml"), "w").write(sm)
    print(f"build_offexchange: wrote {len(issues)} issue page(s) + index to {oe_dir}/ "
          f"and merged them into {out_root}/sitemap.xml")
    return issues


if __name__ == "__main__":
    write(sys.argv[1] if len(sys.argv) > 1 else "public")
