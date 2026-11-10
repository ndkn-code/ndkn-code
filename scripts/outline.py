"""Set text as vector outlines, so no font file ever ships in this public repo.

The Timeless Free Font License 1.2 allows converting text set in the fonts to
outlines within a specific work (section 5.2) and forbids putting the fonts on a
public repository (section 6). The cards are the work; the font files stay
private and are read from TIMELESS_DIR at render time.

Text is shaped with HarfBuzz (kerning, ligatures, tabular figures on request) and
drawn through fontTools pens into one SVG path per run.
"""

from __future__ import annotations

import io
import os
from functools import lru_cache
from pathlib import Path

import uharfbuzz as hb
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

DEFAULT_DIR = Path.home() / "Developer" / "jknguyen-portfolio" / "public" / "fonts" / "timeless"

FILES = {
    "sans": {400: "TimelessSans-GroteskRegular", 500: "TimelessSans-GroteskMedium", 600: "TimelessSans-GroteskSemibold"},
    "sans-italic": {400: "TimelessSans-GroteskRegularItalic"},
    "serif": {300: "TimelessSerif-Light", 400: "TimelessSerif-Regular"},
    "serif-italic": {300: "TimelessSerif-LightItalic", 400: "TimelessSerif-RegularItalic"},
    "serif-text": {400: "TimelessSerif-TextRegular", 500: "TimelessSerif-TextMedium"},
}


def font_dir() -> Path:
    d = Path(os.environ.get("TIMELESS_DIR", DEFAULT_DIR))
    if not (d / "TimelessSerif-Regular.woff2").exists():
        raise SystemExit(f"Timeless fonts not found in {d}. Set TIMELESS_DIR.")
    return d


class Face:
    def __init__(self, path: Path):
        tt = TTFont(path)
        tt.flavor = None  # HarfBuzz reads sfnt, not WOFF2
        buf = io.BytesIO()
        tt.save(buf)
        self.hb = hb.Font(hb.Face(buf.getvalue()))
        self.upm = tt["head"].unitsPerEm
        self.glyphs = tt.getGlyphSet()
        self.order = tt.getGlyphOrder()

    def shape(self, text: str, tnum: bool):
        b = hb.Buffer()
        b.add_str(text)
        b.guess_segment_properties()
        feats = {"kern": True, "liga": True}
        if tnum:
            feats["tnum"] = True
        hb.shape(self.hb, b, feats)
        return b.glyph_infos, b.glyph_positions

    def width(self, text: str, size: float, tracking: float = 0, tnum: bool = False) -> float:
        _, pos = self.shape(text, tnum)
        return sum(p.x_advance for p in pos) * size / self.upm + tracking * max(0, len(pos) - 1)

    def path(self, text: str, x: float, y: float, size: float, tracking: float = 0, tnum: bool = False) -> str:
        infos, pos = self.shape(text, tnum)
        s = size / self.upm
        pen = SVGPathPen(self.glyphs, ntos=lambda v: f"{v:.1f}".rstrip("0").rstrip("."))
        cx = x
        for info, p in zip(infos, pos):
            name = self.order[info.codepoint]
            tp = TransformPen(pen, (s, 0, 0, -s, cx + p.x_offset * s, y - p.y_offset * s))
            self.glyphs[name].draw(tp)
            cx += p.x_advance * s + tracking
        return pen.getCommands()


def _nearest(weights: dict, weight: int) -> str:
    return weights[min(weights, key=lambda w: abs(w - weight))]


@lru_cache(maxsize=None)
def face(kind: str = "sans", weight: int = 400) -> Face:
    return Face(font_dir() / f"{_nearest(FILES[kind], weight)}.woff2")
