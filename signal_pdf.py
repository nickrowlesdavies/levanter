#!/usr/bin/env python3
"""Render a Levanter Signal markdown file into a branded PDF (logo + charts) for
LinkedIn / PDF distribution. Builds a self-contained HTML and prints it to PDF
with headless Chrome. Local/delivery step (Chrome is not on CI).

    python signal_pdf.py <signal.md> <out.pdf> [--editor "your one-line read"]
"""
import base64
import os
import re
import subprocess
import sys

GRAD = "linear-gradient(120deg,#0ea5e9,#3b82f6 55%,#6366f1)"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

MARK = ('<svg viewBox="0 0 120 120" width="40" height="40">'
        '<g fill="none" stroke="#fff" stroke-linecap="round">'
        '<path d="M20 82 C46 71 66 71 90 78" stroke-width="9" opacity=".55"/>'
        '<path d="M20 60 C52 45 78 45 104 55" stroke-width="9.5"/>'
        '<path d="M20 38 C42 29 60 29 80 35" stroke-width="9" opacity=".82"/></g>'
        '<path d="M90 46 l16 -7 -4 16" fill="none" stroke="#fff" stroke-width="9.5" '
        'stroke-linecap="round" stroke-linejoin="round"/></svg>')


def _img(path):
    if not os.path.exists(path):
        return ""
    b = base64.b64encode(open(path, "rb").read()).decode()
    return f'<figure><img src="data:image/png;base64,{b}"></figure>'


def _inline(s):
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)


def build_html(md, editor_line=None):
    lines = md.splitlines()
    title, dateline = "Levanter Signal", ""
    body, i = [], 0
    in_ul = False

    def close_ul():
        nonlocal in_ul
        if in_ul:
            body.append("</ul>")
            in_ul = False

    for line in lines:
        s = line.rstrip()
        if s.startswith("# "):
            title = s[2:].strip()
            continue
        if s == "---" or not s.strip():
            close_ul()
            continue
        # editor prompt -> replace with the editor line (or drop)
        if s.startswith("> **Editor"):
            close_ul()
            if editor_line:
                body.append(f'<div class="editor"><span>Editor&rsquo;s read</span>'
                            f'<p>{_inline(editor_line)}</p></div>')
            continue
        if s.startswith("> "):                       # launch banner
            close_ul()
            body.append(f'<div class="banner">{_inline(s[2:].strip())}</div>')
            continue
        if s.startswith("## "):
            close_ul()
            body.append(f"<h2>{_inline(s[3:].strip())}</h2>")
            continue
        if s.startswith("- "):
            if not in_ul:
                body.append("<ul>")
                in_ul = True
            body.append(f"<li>{_inline(s[2:].strip())}</li>")
            continue
        close_ul()
        # chart callouts -> embed the referenced images
        low = s.lower()
        if s.startswith("*(chart") or ("chart:" in low and s.startswith("*(")):
            imgs = ""
            # Match on what the chart IS, not on one adjective. Keying this to
            # "adoption" silently dropped the chart when that word was renamed.
            if "fair value" in low or "valuation fit" in low or "floor" in low:
                imgs = _img("reports/btc_metcalfe.png")
            elif "market map" in low or "correlation" in low:
                imgs = _img("reports/crypto_map_treemap.png") + _img("reports/crypto_map_correlation.png")
            if imgs:
                body.append(imgs)
            continue
        if s.startswith("*") and s.endswith("*"):     # italic front/footer matter
            txt = _inline(s.strip("*").strip())
            cls = "stamp" if "Data captured" in s else "foot"
            body.append(f'<p class="{cls}">{txt}</p>')
            continue
        body.append(f"<p>{_inline(s)}</p>")
    close_ul()

    date = title.split("·")[-1].strip() if "·" in title else ""
    head = ("Levanter Signal" if "Signal" in title else title)
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
@page {{ size: A4; margin: 16mm 15mm; }}
* {{ box-sizing: border-box; }}
body {{ margin:0; color:#0f172a; font-family:-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
  font-size:11.2pt; line-height:1.55; }}
.header {{ background:{GRAD}; color:#fff; padding:20px 24px; border-radius:14px;
  display:flex; align-items:center; gap:16px; margin-bottom:22px; }}
.header .mark {{ flex:0 0 auto; }}
.header .t {{ font-weight:800; font-size:22pt; letter-spacing:.3px; line-height:1; }}
.header .s {{ font-size:9pt; letter-spacing:3px; text-transform:uppercase; opacity:.9; margin-top:5px; }}
.header .d {{ margin-left:auto; text-align:right; font-size:10pt; opacity:.95; }}
.header .d b {{ display:block; font-size:13pt; }}
h2 {{ font-size:13.5pt; font-weight:800; color:#1e3a8a; margin:20px 0 6px;
  border-top:1px solid #e2e8f0; padding-top:14px; }}
h2:first-of-type {{ border-top:0; padding-top:0; }}
p {{ margin:0 0 10px; }}
strong {{ font-weight:700; }}
.stamp {{ color:#64748b; font-size:9.5pt; font-style:italic; margin-bottom:16px; }}
.banner {{ background:#eff6ff; border:1px solid #bfdbfe; border-left:4px solid #3b82f6;
  border-radius:10px; padding:12px 14px; margin:0 0 16px; font-size:10.6pt; }}
.editor {{ background:#f8fafc; border:1px solid #e2e8f0; border-left:4px solid #6366f1;
  border-radius:10px; padding:12px 14px; margin:0 0 18px; }}
.editor span {{ font-size:8.5pt; font-weight:800; letter-spacing:1.5px; text-transform:uppercase;
  color:#6366f1; }}
.editor p {{ margin:4px 0 0; font-size:11.6pt; font-weight:600; }}
ul {{ margin:2px 0 12px; padding-left:18px; }}
li {{ margin:0 0 7px; }}
figure {{ margin:14px 0; text-align:center; page-break-inside:avoid; }}
figure img {{ max-width:100%; border:1px solid #e2e8f0; border-radius:10px; }}
.foot {{ color:#64748b; font-size:9pt; border-top:1px solid #e2e8f0; padding-top:12px; margin-top:16px; }}
</style></head><body>
<div class="header"><div class="mark">{MARK}</div>
  <div><div class="t">Levanter Signal</div><div class="s">Markets · Signals · Insight</div></div>
  <div class="d">Weekly premium note<b>{date}</b></div></div>
{''.join(body)}
</body></html>"""


def main():
    md_path, out = sys.argv[1], sys.argv[2]
    editor = None
    if "--editor" in sys.argv:
        editor = sys.argv[sys.argv.index("--editor") + 1]
    html = build_html(open(md_path).read(), editor)
    html_path = out.replace(".pdf", ".html")
    open(html_path, "w").write(html)
    if os.path.exists(CHROME):
        subprocess.run([CHROME, "--headless", "--disable-gpu", "--no-pdf-header-footer",
                        f"--print-to-pdf={out}", "file://" + os.path.abspath(html_path)],
                       check=True, capture_output=True)
        print(f"signal_pdf: wrote {out}")
    else:
        print(f"signal_pdf: Chrome not found; wrote HTML only at {html_path}")


if __name__ == "__main__":
    main()
