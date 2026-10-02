from __future__ import annotations

import io
from pathlib import Path

from fontTools.subset import Options, Subsetter
from fontTools.ttLib import TTFont


def make_options() -> Options:
    options = Options()
    options.flavor = "woff2"
    options.with_zopfli = True
    # Keep every GSUB/GPOS feature; the subsetter then computes the glyph
    # closure of all retained substitution lookups and prunes GPOS to the
    # glyphs that remain.
    options.layout_features = ["*"]
    options.layout_scripts = ["*"]
    options.glyph_names = False
    options.symbol_cmap = True
    options.legacy_cmap = True
    options.notdef_outline = True
    options.recommended_glyphs = True
    # Keep all name records (copyright, license, designer, URL ...).
    options.name_IDs = ["*"]
    options.name_legacy = True
    options.name_languages = ["*"]
    options.hinting = True
    options.legacy_kern = True
    options.recalc_bounds = True
    options.drop_tables = []
    return options


def subset_to_woff2(src_ttf: Path, codepoints: list[int], out_path: Path) -> int:
    """Build a real WOFF2 subset.

    Subsetting keeps composite glyph components and closes GSUB lookups over the
    retained glyph set (--layout-features=*). Related GPOS lookups are pruned
    automatically; glyph metrics (hmtx/vmtx) and name/copyright records stay.
    """
    options = make_options()
    font = TTFont(str(src_ttf), recalcBBoxes=False, lazy=False)
    try:
        sub = Subsetter(options=options)
        unicodes = set(codepoints)
        sub.populate(unicodes=unicodes)
        sub.subset(font)
        # The subsetter closure may pull in glyphs reachable via GSUB that map
        # back to additional Unicode codepoints; that is intentional.
        buf = io.BytesIO()
        font.flavor = "woff2"
        font.save(buf)
        data = buf.getvalue()
    finally:
        font.close()
    if data[:4] != b"wOF2":
        raise RuntimeError("WOFF2 encoder produced unexpected output")
    out_path.write_bytes(data)
    return len(data)
