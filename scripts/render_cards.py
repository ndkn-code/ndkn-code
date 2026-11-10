"""Render the animated SVG cards for the GitHub profile README.

Reads data/profile.json (public facts) and data/contributions.json (GitHub
contribution calendar), writes cards/<name>-light.svg and cards/<name>-dark.svg.

The set (one picture, not a stack of equal boxes):
  hero      the portfolio's Ask AI window answering one question, cropped at
            the right and the foot
  tiles     three colored tiles, BUILD, GROW and ANALYZE: one number each,
            with its sentence and its as-of date or dataset
  activity  the contribution graph, the busiest day ringed and keyed

Each card also has a -compact design for the phone column (358 wide, or the
tile's share of it), recomposed rather than squeezed; the README swaps it in
with a <picture> width query.

GitHub shows README images through <img>, so each SVG is self-contained: the
font and mascot are embedded, no scripts, no external requests. Motion is CSS
keyframes only. Every element's resting state is its final state, so
`prefers-reduced-motion` and STATIC=1 show the finished card.

Usage:
    python scripts/render_cards.py            # animated
    STATIC=1 python scripts/render_cards.py   # final frame only, for screenshots
"""

from __future__ import annotations

import datetime as dt
import json
import math
import os
import re
from pathlib import Path
from xml.sax.saxutils import escape

from outline import face

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / os.environ.get("OUT_DIR", "cards")
STATIC = os.environ.get("STATIC") == "1"

# Portfolio color tokens. Rules are opaque so nothing reads see-through.
THEMES = {
    "light": {
        "paper": "#f8faff",
        "rule": "#e2e8f0",
        "surface": "#ffffff",
        "muted_bg": "#f0f4f8",
        "ink": "#374151",
        "strong": "#111827",
        "muted": "#6f7189",
        "faint": "#9aa3b2",
        "primary": "#5279fd",
        "fill": "#5279fd",
        "on_primary": "#ffffff",
        "primary_tint": "#d4dcfe",
        "track": "#e9edf5",
        "chip": "#f8faff",
        "raised": "#ffffff",
        "input": "#e2e8f0",
        "shadow": "rgba(31,39,70,0.16)",
        "ramp": ["#e9edf5", "#d4dcfe", "#a3b6fe", "#7593fd", "#4467e8"],
    },
    "dark": {
        "paper": "#0f172a",
        "rule": "#262e3f",
        "surface": "#1e293b",
        "muted_bg": "#334155",
        "ink": "#e2e8f0",
        "strong": "#f8fafc",
        "muted": "#94a3b8",
        "faint": "#64748b",
        # Dark mode matches the portfolio: a lighter blue for text (7.4:1 on the page),
        # a deeper blue for fills so white text on them passes AA (6.4:1).
        "primary": "#86a3ff",
        "fill": "#3654c9",
        "on_primary": "#ffffff",
        "primary_tint": "#2c3f7a",
        "track": "#1e293b",
        "chip": "#1e293b",
        "raised": "#2b3852",
        "input": "#3a4558",
        "shadow": "rgba(0,0,0,0.55)",
        "ramp": ["#1e293b", "#243a78", "#2d4bb8", "#4467e8", "#6b8fff"],
    },
}


# ---------------------------------------------------------------- type
# Every string is Timeless set as outlines (scripts/outline.py): the fonts never ship.
# kind: "sans" (Timeless Sans Grotesk), "serif", "serif-italic", "serif-text".


def tw(text: str, size: float, weight: int = 400, kind: str = "sans", tracking: float = 0, tnum: bool = False) -> float:
    """Advance width of a shaped string."""
    return face(kind, weight).width(text, size, tracking, tnum)


def wrap(text: str, size: float, width: float, weight: int = 400, kind: str = "sans") -> list[str]:
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if line and tw(trial, size, weight, kind) > width:
            lines.append(line)
            line = word
        else:
            line = trial
    return lines + ([line] if line else [])


def balance(text: str, size: float, width: float, weight: int = 400, kind: str = "sans") -> list[str]:
    """Wrap at the narrowest width that keeps the line count, so lines even out."""
    n = len(wrap(text, size, width, weight, kind))
    lo, hi = width * 0.5, width
    while hi - lo > 1:
        mid = (lo + hi) / 2
        if len(wrap(text, size, mid, weight, kind)) > n:
            lo = mid
        else:
            hi = mid
    return wrap(text, size, hi, weight, kind)


def t(x, y, s, size, fill, weight=400, anchor="start", extra="", kind="sans", tracking=0, tnum=False):
    """A run of text as one outlined path. The words stay readable in each card's title."""
    f = face(kind, weight)
    if anchor != "start":
        w = f.width(s, size, tracking, tnum)
        x -= w if anchor == "end" else w / 2
    d = f.path(s, x, y, size, tracking, tnum)
    return f'<path d="{d}" fill="{fill}"{extra}/>' if d else ""


def rrect(x, y, w, h, r, fill, stroke=None, extra=""):
    s = f' stroke="{stroke}"' if stroke else ""
    return f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{r}" fill="{fill}"{s}{extra}/>'


def bubble(x, y, w, h, r, tail: str, fill, extra=""):
    """A chat bubble: rounded on three corners, a tighter radius at the tail corner."""
    rs = 6
    tl = tr = br = bl = r
    if tail == "br":
        br = rs
    else:
        bl = rs
    d = (
        f"M{x + tl:.1f},{y:.1f} H{x + w - tr:.1f} A{tr},{tr} 0 0 1 {x + w:.1f},{y + tr:.1f} "
        f"V{y + h - br:.1f} A{br},{br} 0 0 1 {x + w - br:.1f},{y + h:.1f} "
        f"H{x + bl:.1f} A{bl},{bl} 0 0 1 {x:.1f},{y + h - bl:.1f} "
        f"V{y + tl:.1f} A{tl},{tl} 0 0 1 {x + tl:.1f},{y:.1f} Z"
    )
    return f'<path d="{d}" fill="{fill}"{extra}/>'


def svg(width, height, body, theme, css="", title="", defs="", x0=0):
    """x0 leaves a transparent gap at the left: the README sets paired tiles with no
    whitespace between them, so the gap lives in the image and the outer edges line up."""
    motion = "" if STATIC else css
    cw = width - x0
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">
<title>{escape(title)}</title>
<defs>
<clipPath id="card"><rect x="{x0}" y="0" width="{cw}" height="{height}" rx="16"/></clipPath>
<filter id="lift" x="-20%" y="-20%" width="140%" height="160%"><feDropShadow dx="0" dy="10" stdDeviation="12" flood-color="{theme['shadow']}"/></filter>
{defs}
</defs>
<style>
{motion}
@media (prefers-reduced-motion: reduce) {{ * {{ animation: none !important; }} }}
</style>
<g clip-path="url(#card)">
<rect x="{x0}" y="0" width="{cw}" height="{height}" fill="{theme['paper']}"/>
<g transform="translate({x0},0)">
{body}
</g>
</g>
<rect x="{x0 + 0.5}" y="0.5" width="{cw - 1}" height="{height - 1}" rx="15.5" fill="none" stroke="{theme['rule']}"/>
</svg>
"""


# ---------------------------------------------------------------- motion helpers

LIFT = ' filter="url(#lift)"'

KEYFRAMES = (
    "@keyframes on{from,to{opacity:1}}"
    "@keyframes off{from,to{opacity:0}}"
    "@keyframes fade{from{opacity:0}}"
    "@keyframes drop{from{opacity:0;transform:translateY(10px)}}"
    "@keyframes grow-x{from{transform:scaleX(0)}}"
    "@keyframes pop{from{opacity:0;transform:scale(.3)}}"
)


def count(x, y, start, end, size, fill, weight, delay, uid, *, decimals=0, prefix="",
          suffix="", unit="", anchor="start", frames=16, step=0.05, tabular=True):
    """A number rolling from start to end. Frames are stacked text nodes, each
    hidden by attribute and shown by animation only in its own slot; the final
    value is visible at rest and hidden only while the frames play. Frame 0
    also covers the lead-in, so the slot is never blank."""
    nodes, css = [], []
    for i in range(frames):
        eased = 1 - (1 - i / frames) ** 3
        v = start + (end - start) * eased
        shown = f"{v:,.{decimals}f}"
        cls = f"{uid}{i}"
        s, d = (0, delay + step) if i == 0 else (delay + i * step, step)
        css.append(f".{cls}{{animation:on {d:.3f}s linear {s:.3f}s 1}}")
        nodes.append(t(x, y, f"{prefix}{shown}{unit}", size, fill, weight, anchor, f' class="{cls}" opacity="0"', tnum=tabular))
    total = delay + frames * step
    css.append(f".{uid}z{{animation:off {total:.3f}s linear 0s 1}}")
    nodes.append(t(x, y, f"{prefix}{end:,.{decimals}f}{unit}{suffix}", size, fill, weight, anchor, f' class="{uid}z"', tnum=tabular))
    return "\n".join(nodes), "".join(css)


# ---------------------------------------------------------------- mascot

def _oklab_to_rgb(m):
    L, a, b = (float(v) for v in m.groups())
    l_ = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m_ = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s_ = (L - 0.0894841775 * a - 1.2914855480 * b) ** 3
    lin = (
        4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_,
        -1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_,
        -0.0041960863 * l_ - 0.7034186147 * m_ + 1.7076147010 * s_,
    )
    enc = [round(255 * max(0, min(1, (1.055 * c ** (1 / 2.4) - 0.055) if c > 0.0031308 else 12.92 * c))) for c in lin]
    return "rgb({}, {}, {})".format(*enc)


def mascot(mode: str, x: float, y: float, size: float) -> str:
    """The portfolio's Ask AI mascot, captured from the site at rest."""
    raw = (ROOT / "assets" / f"mascot-{mode}.svg").read_text()
    raw = re.sub(r"oklab\(([-\d.]+) ([-\d.]+) ([-\d.]+)\)", _oklab_to_rgb, raw)
    raw = raw.replace('aria-hidden="true" focusable="false"', "")
    return raw.replace('<svg width="56" height="56"', f'<svg x="{x}" y="{y}" width="{size}" height="{size}"', 1)


# ---------------------------------------------------------------- hero

# Phosphor PaperPlaneRight (fill), MIT: the portfolio's own send icon.
SEND = "M240,127.89a16,16,0,0,1-8.18,14L63.9,237.9A16.15,16.15,0,0,1,56,240a16,16,0,0,1-15-21.33l27-79.95A4,4,0,0,1,71.72,136H144a8,8,0,0,0,8-8.53,8.19,8.19,0,0,0-8.26-7.47h-72a4,4,0,0,1-3.79-2.72l-27-79.94A16,16,0,0,1,63.84,18.07l168,95.89A16,16,0,0,1,240,127.89Z"

INSET = {False: 36, True: 20}  # one text inset for every card at each width


def hero(p: dict, th: dict, mode: str, compact: bool = False) -> str:
    """The portfolio's Ask AI window, running off the right and bottom edges, answering
    one question. Desktop: copy left, window right. Compact: copy on top, window below.
    The numbers the answer stands on are in the tiles card, so they are said once."""
    chat = p["chat"]
    css = [KEYFRAMES]
    body = []
    cx = INSET[compact]
    if compact:
        W, WX = 358, cx
        name_size, head_size, role_size = 36, 23, 13.5
        copy_top = 22
        answer = chat["answer"]
    else:
        W, WX = 840, 436
        name_size, head_size, role_size = 50, 30, 14.5
        copy_top = 0
        answer = chat["answer"]
    right = W - cx  # the thread's right edge; the window itself runs past the card

    def copy_block(top):
        out, cc = [], []
        y_name = top + 26 * (name_size / 40) + (4 if compact else 0)
        y_h1 = y_name + head_size * 1.75
        y_h2 = y_h1 + head_size * 1.3
        out.append(t(cx, y_name, p["name"], name_size, th["strong"], 400, kind="serif"))
        out.append(t(cx, y_h1, p["headline"][0], head_size, th["ink"], 300, kind="serif"))
        out.append(t(cx, y_h2, p["headline"][1], head_size, th["primary"], 400, kind="serif-italic"))
        ul_w = tw(p["headline"][1], head_size, 400, "serif-italic")
        uy = y_h2 + head_size * 0.38
        ul = f"M{cx - 1:.1f} {uy:.1f} C {cx + ul_w * 0.3:.1f} {uy + 4:.1f}, {cx + ul_w * 0.7:.1f} {uy - 3:.1f}, {cx + ul_w + 2:.1f} {uy + 1.5:.1f}"
        ul_len = ul_w * 1.05
        out.append(f'<path class="ul" d="{ul}" fill="none" stroke="{th["primary_tint"]}" stroke-width="{5 if not compact else 4}" stroke-linecap="round" stroke-dasharray="{ul_len:.0f}"/>')
        cc.append(f"@keyframes draw{{from{{stroke-dashoffset:{ul_len:.0f}}}to{{stroke-dashoffset:0}}}}.ul{{animation:draw .7s cubic-bezier(.65,0,.35,1) .2s 1 backwards}}")
        ry = y_h2 + (50 if not compact else 38)
        lh = role_size * 1.45
        for i, line in enumerate(p["roles"]):
            out.append(t(cx, ry + i * lh, line, role_size, th["muted"]))
        y_avail = ry + len(p["roles"]) * lh + (14 if not compact else 10)
        out.append(t(cx, y_avail, p["availability"], role_size, th["ink"], 500))
        widths = [tw(p["name"], name_size, 400, "serif"), tw(p["availability"], role_size, 500)] + [tw(r, role_size) for r in p["roles"]]
        return out, cc, y_name - name_size * 0.72, y_avail, cx + max(widths)

    _, _, ink_top, y_avail, copy_right = copy_block(copy_top)

    # Thread geometry.
    WY = 52 if not compact else int(y_avail + 30)
    pad, head_h = 16, 64
    q_size, a_size, a_lh = 14, 13.5, 21
    q_w = tw(chat["question"], q_size, 500) + 32
    q_y = WY + head_h + 18
    a_x = WX + pad
    a_max = (right - a_x) * 0.9
    emph = set(chat.get("emphasis", [])) if compact else set()
    a_lines = balance(answer, a_size, a_max - 32)
    chips_w = sum(tw(src, 11, 500) + 22 for src in chat["sources"]) + 6 * (len(chat["sources"]) - 1)

    def word_w(w, trailing=" "):
        return tw(w + trailing, a_size, 700 if w.strip(".,") in emph else 400)

    a_w = max(max(sum(word_w(w) for w in line.split(" ")) for line in a_lines), chips_w) + 32
    chips_y_rel = 14 + len(a_lines) * a_lh + 6
    a_h = chips_y_rel + 24 + 14
    a_y = q_y + 40 + 14
    a_bottom = a_y + a_h
    comp_y = a_bottom + 18
    H = int(comp_y + 40 + 18)

    if not compact:
        # Center the copy on the card, but keep it clear of the left satellite.
        ink_h = y_avail - ink_top
        copy_top += (H - ink_h) / 2 - ink_top
    out, cc, _, _, _ = copy_block(copy_top)
    body += out
    css += cc

    # Window: past the right edge and the foot, so only its empty margin is cropped.
    body.append(rrect(WX, WY, W - WX + 40, H + 40, 16, th["surface"], th["rule"], LIFT))
    body.append(mascot(mode, WX + 12, WY + 10, 44))
    body.append(t(WX + 64, WY + 30, chat["title"], 15, th["strong"], 700))
    body.append(t(WX + 64, WY + 48, chat["subtitle"], 12, th["muted"]))
    body.append(f'<line x1="{WX}" x2="{W}" y1="{WY + head_h}" y2="{WY + head_h}" stroke="{th["rule"]}"/>')

    # Composer, as on the portfolio: placeholder and a send button.
    comp_w = right - (WX + pad)
    body.append(rrect(WX + pad, comp_y, comp_w, 40, 20, th["paper"], th["input"]))
    body.append(t(WX + pad + 16, comp_y + 25, chat["placeholder"], 13, th["muted"]))
    bx = WX + pad + comp_w - 36
    body.append(rrect(bx, comp_y + 4, 32, 32, 16, th["fill"]))
    body.append(f'<svg x="{bx + 9}" y="{comp_y + 13}" width="14" height="14" viewBox="0 0 256 256"><path d="{SEND}" fill="{th["on_primary"]}"/></svg>')

    # Beat 1: the question is sent.
    qx = right - q_w
    body.append(
        f'<g class="q">{bubble(qx, q_y, q_w, 40, 18, "br", th["fill"])}'
        f'{t(qx + 16, q_y + 25, chat["question"], q_size, th["on_primary"], 500)}</g>'
    )
    css.append(".q{animation:drop .4s cubic-bezier(.2,.8,.2,1) .5s 1 backwards}")

    # Beat 2: Thinking, in the answer's place, gone when the answer opens.
    t_on, a_on = 1.05, 1.95
    body.append(t(a_x + 16, a_y + 26, "Thinking", a_size, th["muted"], 500, extra=' class="th" opacity="0"'))
    css.append(f".th{{animation:on {a_on - t_on:.2f}s linear {t_on:.2f}s 1}}")

    # Beat 3: the answer streams in word by word, every word laid out from the start.
    words = []
    for li, line in enumerate(a_lines):
        x = a_x + 16
        for w in line.split(" "):
            words.append((x, a_y + 28 + li * a_lh, w))
            x += word_w(w)
    body.append(f'<g class="ab">{bubble(a_x, a_y, a_w, a_h, 18, "bl", th["muted_bg"])}</g>')
    css.append(f".ab{{animation:fade .25s ease-out {a_on:.2f}s 1 backwards}}")
    for i, (x, y, w) in enumerate(words):
        strong = w.strip(".,") in emph
        body.append(t(x, y, w, a_size, th["strong"] if strong else th["ink"], 700 if strong else 400, extra=f' class="w{i}"'))
        css.append(f".w{i}{{animation:fade .14s linear {a_on + 0.08 + i * 0.04:.3f}s 1 backwards}}")
    stream_end = a_on + 0.08 + len(words) * 0.04

    # Beat 4: sources arrive under the answer.
    sx = a_x + 16
    chips = []
    for src in chat["sources"]:
        cw = tw(src, 11, 500) + 22
        chips.append(rrect(sx, a_y + chips_y_rel, cw, 24, 12, th["chip"], th["rule"]))
        chips.append(t(sx + 11, a_y + chips_y_rel + 16, src, 11, th["muted"], 500))
        sx += cw + 6
    body.append(f'<g class="src">{"".join(chips)}</g>')
    css.append(f".src{{animation:drop .35s cubic-bezier(.2,.8,.2,1) {stream_end + 0.2:.2f}s 1 backwards}}")

    title = f"{p['name']}. {' '.join(p['headline'])}. {chat['question']} {answer}"
    return svg(W, H, "\n".join(body), th, "".join(css), title)


# ---------------------------------------------------------------- tiles
# Three colored tiles in one image, so the phone design can stack them full width.
# Each: a label, one number with its unit, one sentence, its as-of date or dataset.
# They start after the hero's answer lands, so the hero leads.

LATER = 2.9
TILE = {
    "blue": {"bg": "#4467e8", "ink": "#ffffff", "soft": "#ffffff"},  # translucent white fails AA here
    "gold": {"bg": "#feaa00", "ink": "#1f1a0e", "soft": "rgba(31,26,14,0.72)"},
    "lavender": {"bg": "#ae92ea", "ink": "#1c1533", "soft": "rgba(28,21,51,0.85)"},
}


def tiles(tl: dict, th: dict, compact: bool = False) -> str:
    items = tl["items"]
    pad = 24 if not compact else 20
    gap = 16 if not compact else 12
    W = 840 if not compact else 358
    tw_ = (W - gap * (len(items) - 1)) / len(items) if not compact else W
    text_w = tw_ - 2 * pad
    lines = [balance(it["text"], 14.5, text_w, 500) for it in items]
    n_lines = max(len(x) for x in lines) if not compact else None

    def tile_h(k):
        n = n_lines if not compact else len(lines[k])
        return 112 + n * 20 + 40

    # One number size for all tiles, the largest at which the widest number and unit fit.
    def run_w(it, k):
        return tw(f"{it['value']:,}{it['suffix']}", 50 * k, 400, "serif") + 8 + tw(it["unit"], 28 * k, 400, "serif-italic")
    fit = min(1.0, min(text_w / run_w(it, 1.0) for it in items))
    n_size, u_size = 50 * fit, 28 * fit

    css = [KEYFRAMES]
    body = ['<defs><linearGradient id="sheen" x1="0" x2="1" y1="0" y2="0">'
            '<stop offset="0" stop-color="#fff" stop-opacity="0"/>'
            '<stop offset="0.5" stop-color="#fff" stop-opacity="0.32"/>'
            '<stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient></defs>']
    y = 0
    for k, it in enumerate(items):
        c = TILE[it["color"]]
        if compact:
            x, h = 0, tile_h(k)
        else:
            x, h = k * (tw_ + gap), tile_h(0)
        body.append(rrect(x, y, tw_, h, 16, c["bg"]))
        body.append(t(x + pad, y + 38, it["label"], 12, c["soft"], 600, tracking=1.6))
        num = f"{it['value']:,}{it['suffix']}"
        # The real number from the first frame; one shine sweep crosses the tile once.
        body.append(t(x + pad - 1, y + 94, num, n_size, c["ink"], 400, kind="serif"))
        body.append(f'<clipPath id="tc{k}"><rect x="{x:.1f}" y="{y}" width="{tw_:.1f}" height="{h}" rx="16"/></clipPath>')
        band = 150
        # Hidden at rest (attribute), visible only while the sweep plays, so a still,
        # reduced motion and STATIC all show a clean tile.
        body.append(
            f'<g clip-path="url(#tc{k})"><rect class="sh{k}" x="{x - band - 70:.1f}" y="{y}" width="{band}" height="{h}" '
            f'fill="url(#sheen)" opacity="0"/></g>'
        )
        travel = tw_ + band + 140
        css.append(
            f"@keyframes sweep{k}{{from{{opacity:1;transform:skewX(-18deg) translateX(0)}}"
            f"to{{opacity:1;transform:skewX(-18deg) translateX({travel:.0f}px)}}}}"
            f".sh{k}{{transform-box:fill-box;transform-origin:0 100%;animation:sweep{k} 1.1s cubic-bezier(.4,0,.2,1) {LATER + 0.3 + k * 0.15:.2f}s 1}}"
        )
        body.append(t(x + pad - 1 + tw(num, n_size, 400, "serif") + 8, y + 94, it["unit"], u_size, c["ink"], 400, kind="serif-italic"))
        for i, line in enumerate(lines[k]):
            body.append(t(x + pad, y + 124 + i * 20, line, 14.5, c["ink"], 500))
        body.append(t(x + pad, y + h - 22, it["foot"], 12, c["soft"], 500))
        if compact:
            y += h + gap
    H = (y - gap) if compact else tile_h(0)
    title = " ".join(f"{it['label'].title()}: {it['value']:,}{it['suffix']} {it['unit']}. {it['text']} {it['foot']}." for it in items)
    return frameless(W, int(H), "\n".join(body), th, "".join(css), title)


def frameless(width, height, body, theme, css, title):
    """For an image that draws its own tiles: no outer card, transparent between tiles."""
    motion = "" if STATIC else css
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">
<title>{escape(title)}</title>
<style>
{motion}
@media (prefers-reduced-motion: reduce) {{ * {{ animation: none !important; }} }}
</style>
{body}
</svg>
"""


# ---------------------------------------------------------------- activity

def _streaks(days):
    longest = run = 0
    for d in days:
        run = run + 1 if d["contributionCount"] > 0 else 0
        longest = max(longest, run)
    current = 0
    trimmed = days[:-1] if days and days[-1]["contributionCount"] == 0 else days
    for d in reversed(trimmed):
        if d["contributionCount"] == 0:
            break
        current += 1
    return longest, current


def fmt_date(iso: str, year=True) -> str:
    d = dt.date.fromisoformat(iso)
    return f"{d:%b} {d.day}, {d.year}" if year else f"{d:%b} {d.day}"


def activity(c: dict, th: dict, compact: bool = False) -> str:
    """Desktop: the year as GitHub draws it. Compact: the last 26 weeks, labeled as such,
    at a cell size a phone can read; totals and streaks stay for the full year. The empty
    grid is there from the first frame; only the color arrives."""
    days = c["days"]
    months: dict[str, int] = {}
    for d in days:
        months[d["date"][:7]] = months.get(d["date"][:7], 0) + d["contributionCount"]
    best = max(months, key=months.get)
    best_name = dt.date.fromisoformat(best + "-01").strftime("%B %Y")
    longest, current = _streaks(days)
    busiest = max(days, key=lambda d: d["contributionCount"])
    as_of = fmt_date(days[-1]["date"])

    W = 358 if compact else 840
    m = INSET[compact]
    head = f"{c['total']:,} contributions"
    body = []
    if not compact:
        body += [
            t(m, 50, head, 26, th["strong"], 400, kind="serif"),
            t(m + tw(head + " ", 26, 400, "serif"), 50, f"in the last year, as of {as_of}", 14, th["muted"]),
            t(m, 72, f"{best_name} was the busiest month, with {months[best]:,}.", 14, th["ink"], 500),
        ]
        shown, gy, gap = days, 112, 4
    else:
        body += [
            t(m, 40, head, 24, th["strong"], 400, kind="serif"),
            t(m, 58, f"in the last year, as of {as_of}", 12.5, th["muted"]),
            t(m, 82, f"{best_name} was the busiest month,", 13, th["ink"], 500),
            t(m, 100, f"with {months[best]:,}. Last 26 weeks below.", 13, th["ink"], 500),
        ]
        last = dt.date.fromisoformat(days[-1]["date"])
        start = last - dt.timedelta(days=(last.weekday() + 1) % 7 + 25 * 7)  # Sunday 25 weeks back
        shown = [d for d in days if dt.date.fromisoformat(d["date"]) >= start]
        gy, gap = 138, 4

    first = dt.date.fromisoformat(shown[0]["date"])
    lead = (first.weekday() + 1) % 7  # GitHub weeks start on Sunday
    weeks = math.ceil((len(shown) + lead) / 7)
    pitch = (W - 2 * m + gap) / weeks
    cell = pitch - gap
    nz = sorted(d["contributionCount"] for d in days if d["contributionCount"] > 0)
    q = [nz[int(len(nz) * f)] for f in (0.25, 0.5, 0.75)] if nz else [1, 2, 3]

    def level(n):
        return 0 if n == 0 else 1 + sum(n > x for x in q)

    css = [KEYFRAMES]
    seen, ring = None, None
    step = 0.022 if not compact else 0.04
    for i, d in enumerate(shown):
        col, row = divmod(i + lead, 7)
        x, y = m + col * pitch, gy + row * pitch
        body.append(rrect(x, y, cell, cell, 2.5, th["ramp"][0]))
        lv = level(d["contributionCount"])
        if lv:
            body.append(rrect(x, y, cell, cell, 2.5, th["ramp"][lv], extra=f' class="c{col}"'))
        if d is busiest:
            ring = (x, y)
        mo = d["date"][:7]
        if row == 0 and mo != seen and col < weeks - 2:
            seen = mo
            body.append(t(x, gy - 9, dt.date.fromisoformat(d["date"]).strftime("%b"), 11, th["muted"]))
    for col in range(weeks):
        css.append(f".c{col}{{animation:fade .35s ease-out {LATER + 0.3 + col * step:.3f}s 1 backwards}}")
    sweep_end = LATER + 0.3 + weeks * step + 0.35

    # The busiest day: ringed in the gap around its cell, keyed in the stats by the same ring.
    if ring:
        rx, ry = ring
        o = gap / 2
        body.append(rrect(rx - o, ry - o, cell + 2 * o, cell + 2 * o, 4, "none", th["strong"], ' stroke-width="1" class="ring"'))
        css.append(f".ring{{transform-box:fill-box;transform-origin:center;animation:pop .4s cubic-bezier(.2,.8,.2,1.4) {sweep_end + 0.1:.2f}s 1 backwards}}")

    stats = [
        ("Longest streak", f"{longest} days", False),
        ("Current streak", f"{current} days", False),
        ("Busiest day", f"{busiest['contributionCount']:,} on {fmt_date(busiest['date'])}", True),
    ]
    grid_right = m + weeks * pitch - gap
    sy = gy + 7 * pitch + 30
    body.append(f'<line x1="{m}" x2="{grid_right:.1f}" y1="{sy - 12}" y2="{sy - 12}" stroke="{th["rule"]}"/>')

    def stat(x, y, label, value, keyed):
        out = []
        if keyed:
            out.append(rrect(x + 1, y - 9.5, 10, 10, 3, "none", th["strong"], ' stroke-width="1.25"'))
            x += 18
        out.append(t(x, y, label, 12.5, th["muted"]))
        out.append(t(x + tw(label + "  ", 12.5), y, value, 13.5, th["strong"], 700))
        return out, x + tw(label + "  ", 12.5) + tw(value, 13.5, 700)

    if not compact:
        sx = m
        for label, value, keyed in stats:
            out, end = stat(sx, sy + 13, label, value, keyed)
            body += out
            sx = end + 36
        legend_y = sy + 13
        H = int(sy + 13 + 28)
        lx = grid_right - 5 * 14 + 3 - tw("More", 11) - 6
        body.append(t(lx - 6, legend_y, "Less", 11, th["muted"], 400, "end"))
    else:
        for i, (label, value, keyed) in enumerate(stats):
            out, _ = stat(m, sy + 13 + i * 24, label, value, keyed)
            body += out
        legend_y = sy + 13 + 3 * 24 + 4
        H = int(legend_y + 24)
        lx = m + tw("Less ", 11) + 2
        body.append(t(m, legend_y, "Less", 11, th["muted"]))
    for i, color in enumerate(th["ramp"]):
        body.append(rrect(lx + i * 14, legend_y - 10, 11, 11, 2.5, color))
    body.append(t(lx + 5 * 14 + 3, legend_y, "More", 11, th["muted"]))

    title = f"{c['total']:,} GitHub contributions in the last year. {best_name} was the busiest month. Busiest day: {fmt_date(busiest['date'])}."
    return svg(W, H, "\n".join(body), th, "".join(css), title)


# ---------------------------------------------------------------- main

def main() -> None:
    profile = json.loads((ROOT / "data" / "profile.json").read_text())
    contrib = json.loads((ROOT / "data" / "contributions.json").read_text())
    OUT.mkdir(exist_ok=True)
    for old in OUT.glob("*.svg"):
        old.unlink()
    for mode, th in THEMES.items():
        for compact in (False, True):
            tag = "-compact" if compact else ""
            files = {
                "hero": hero(profile, th, mode, compact),
                "tiles": tiles(profile["tiles"], th, compact),
                "activity": activity(contrib, th, compact),
            }
            for name, content in files.items():
                (OUT / f"{name}{tag}-{mode}.svg").write_text(content)
    print(f"wrote {len(list(OUT.glob('*.svg')))} cards to {OUT}")


if __name__ == "__main__":
    main()
