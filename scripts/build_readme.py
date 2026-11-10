"""Write README.md (and preview.html, a local GitHub-like page) from data/profile.json."""

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
p = json.loads((ROOT / "data" / "profile.json").read_text())
cards = os.environ.get("CARDS_DIR", "cards")


NARROW = "(max-width: 600px)"


def pic(name, alt, width, href=None):
    """Light and dark, each with a compact design for the phone column."""
    img = (
        "<picture>"
        f'<source media="{NARROW} and (prefers-color-scheme: dark)" srcset="{cards}/{name}-compact-dark.svg">'
        f'<source media="{NARROW}" srcset="{cards}/{name}-compact-light.svg">'
        f'<source media="(prefers-color-scheme: dark)" srcset="{cards}/{name}-dark.svg">'
        f'<img src="{cards}/{name}-light.svg" alt="{alt}" width="{width}"></picture>'
    )
    return f'<a href="{href}">{img}</a>' if href else img


chat, sat, sg, fc = p["chat"], p["satellites"], p["segments"], p["forecast"]
hero_alt = (
    f"{p['name']}, {' '.join(p['headline']).lower()}. {chat['question']} {chat['answer']} "
    f"AI Tutor daily users went from {sat['tutor']['before']} to {sat['tutor']['after']}+ as of {sat['tutor']['as_of']}; "
    f"Lumist reached {sat['users']['value']:,}+ users as of {sat['users']['as_of']}."
)
seg_alt = f"{sg['lead']} {sg['rest']} " + ", ".join(f"{r['share']}% of {r['label'].lower()}" for r in sg["rows"]) + f". {sg['source']}."
fc_alt = f"{fc['lead']}: {fc['after']}% MAPE, down from about {fc['before']}%. {fc['source']}."

blocks = [
    f"<p>{pic('hero', hero_alt, '100%', p['portfolio_url'])}</p>",
    f"<p>{pic('pair', seg_alt + ' ' + fc_alt, '100%', sg['href'])}</p>",
    f"<p>{pic('activity', 'GitHub contributions in the last year.', '100%')}</p>",
]
work = " · ".join(f"[{x['title']}]({x['href']})" for x in p["projects"])
links = f"[Portfolio and case studies]({p['portfolio_url']}) · [LinkedIn]({p['linkedin_url']})"
note = "Cards are SVGs drawn by `scripts/render_cards.py` and refreshed daily by a GitHub Action. Font: Google Sans, SIL Open Font License (`fonts/OFL.txt`)."

if cards == "cards":
    (ROOT / "README.md").write_text("\n\n".join(blocks) + f"\n\n**Selected work:** {work}\n\n{links}\n\n<sub>{note}</sub>\n")


def md_links(s):
    import re
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"`(.+?)`", r"<code>\1</code>", s)
    return re.sub(r"\[(.+?)\]\((.+?)\)", r'<a href="\2">\1</a>', s)


html = "\n".join(blocks) + f"<p>{md_links('**Selected work:** ' + work)}</p><p>{md_links(links)}</p><p><sub>{md_links(note)}</sub></p>"
page = f"""<!doctype html><html><head><meta charset="utf-8"><title>ndkn-code README preview</title>
<meta name="color-scheme" content="light dark">
<style>
body{{margin:0;background:#fff;color:#1f2328;font:16px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
@media (prefers-color-scheme: dark){{body{{background:#0d1117;color:#e6edf3}} .box{{border-color:#30363d!important}} a{{color:#4493f8}}}}
.wrap{{max-width:896px;margin:24px auto;padding:0 16px}}
.box{{border:1px solid #d1d9e0;border-radius:6px;padding:32px}}
@media (max-width:600px){{.wrap{{padding:0 8px}} .box{{padding:16px}}}}
.head{{font:600 12px ui-monospace,monospace;opacity:.7;margin-bottom:16px}}
p{{margin:0 0 16px}} img{{max-width:100%;vertical-align:top}} a{{color:#0969da;text-decoration:none}}
</style></head><body><div class="wrap"><div class="box"><div class="head">ndkn-code / README.md</div>
{html}
</div></div></body></html>"""
(ROOT / ("preview.html" if cards == "cards" else "preview-static.html")).write_text(page)
