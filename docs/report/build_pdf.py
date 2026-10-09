"""Render docs/PROJECT_REPORT.md to docs/PROJECT_REPORT.pdf.

Requires:  pip install markdown playwright  &&  playwright install chromium
Run from the repository root:  python docs/report/build_pdf.py
"""
from pathlib import Path

import markdown
from playwright.sync_api import sync_playwright

DOCS = Path(__file__).resolve().parents[1]
src = (DOCS / "PROJECT_REPORT.md").read_text(encoding="utf-8")
# The PDF does not need a link to itself.
src = src.replace("PDF version: [PROJECT_REPORT.pdf](PROJECT_REPORT.pdf)\n", "")
body = markdown.markdown(src, extensions=["tables", "fenced_code", "sane_lists"])

CSS = """
@page { size: A4; margin: 18mm 18mm 20mm 18mm; }
html { font-family: 'Inter', 'DejaVu Sans', sans-serif; font-size: 10pt; color: #1a1a19; }
body { line-height: 1.5; }
h1 { font-size: 21pt; line-height: 1.2; margin: 0 0 6pt; color: #0b0b0b; letter-spacing: -0.01em; }
h2 { font-size: 14pt; margin: 20pt 0 6pt; color: #0b0b0b; border-bottom: 1px solid #e6e5e0; padding-bottom: 3pt; break-after: avoid; }
h3 { font-size: 11pt; margin: 14pt 0 4pt; color: #0b0b0b; break-after: avoid; }
p, li { margin: 0 0 6pt; }
a { color: #1f63b5; text-decoration: none; }
hr { border: 0; border-top: 1px solid #e6e5e0; margin: 12pt 0; }
code { font-family: 'DejaVu Sans Mono', monospace; font-size: 8.4pt; background: #f4f3ef; padding: 0 2pt; border-radius: 2pt; }
pre { background: #f4f3ef; padding: 8pt 10pt; border-radius: 4pt; overflow: hidden; break-inside: avoid; }
pre code { background: none; padding: 0; font-size: 7.8pt; line-height: 1.4; }
table { border-collapse: collapse; width: 100%; margin: 6pt 0 10pt; font-size: 8.8pt; break-inside: avoid; }
th { text-align: left; font-weight: 600; color: #52514e; border-bottom: 1.5px solid #c3c2b7; padding: 4pt 6pt; }
td { border-bottom: 1px solid #ecebe6; padding: 4pt 6pt; vertical-align: top; }
img { display: block; max-width: 100%; max-height: 95mm; margin: 8pt auto 10pt; break-inside: avoid; }
p:has(> img) { break-inside: avoid; }
strong { color: #0b0b0b; }
"""

html = f"""<!doctype html><html><head><meta charset="utf-8">
<title>EV NEXUS - Project Report</title><style>{CSS}</style></head>
<body>{body}</body></html>"""
tmp = DOCS / "_report_render.html"
tmp.write_text(html, encoding="utf-8")
try:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(tmp.as_uri(), wait_until="networkidle")
        page.pdf(path=str(DOCS / "PROJECT_REPORT.pdf"), format="A4", print_background=True,
                 display_header_footer=True, header_template="<span></span>",
                 footer_template="<div style='font-size:7pt;color:#8a8984;width:100%;text-align:center;'>"
                                 "EV NEXUS project report · <span class='pageNumber'></span> / "
                                 "<span class='totalPages'></span></div>",
                 margin={"top": "18mm", "bottom": "20mm", "left": "18mm", "right": "18mm"})
        browser.close()
finally:
    tmp.unlink(missing_ok=True)
print("wrote", DOCS / "PROJECT_REPORT.pdf")
