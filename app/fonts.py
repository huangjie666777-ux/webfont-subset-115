from __future__ import annotations

import hashlib
from dataclasses import dataclass

from fontTools.ttLib import TTFont


class FontError(ValueError):
    pass


@dataclass(frozen=True)
class FontInfo:
    font_id: str
    family: str
    codepoints: frozenset[int]
    original_size: int
    filename: str
    weight: int = 400
    style: str = "normal"


def font_id_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_font(data: bytes) -> FontInfo:
    """Validate: single static TrueType font containing a glyf table."""
    import io

    font_id = font_id_of(data)
    if data[:4] == b"ttcf":
        raise FontError("font collections (.ttc/.otc) are not supported")
    font = None
    try:
        font = TTFont(io.BytesIO(data), recalcBBoxes=False, lazy=False)
        if getattr(font.reader, "numFonts", 1) != 1:
            raise FontError("font collections are not supported")
        if "glyf" not in font:
            raise FontError("only static TrueType outlines (glyf table) are supported")
        if "fvar" in font:
            raise FontError("variable fonts are not supported")
        if "CFF " in font or "CFF2" in font:
            raise FontError("only static TrueType outlines (glyf table) are supported")
        cmap = font.getBestCmap()
        if not cmap:
            raise FontError("font has no usable Unicode cmap")
        glyf = font["glyf"]
        glyph_order = font.getGlyphOrder()
        notdef = glyf[".notdef"]
        notdef.getCoordinates(glyf)
        covered: set[int] = set()
        for cp, name in cmap.items():
            if name == ".notdef" or name not in glyph_order:
                continue
            g = glyf[name]
            # Decompose to force parsing every mapped simple/composite outline.
            g.getCoordinates(glyf)
            covered.add(int(cp))
        name_table = font["name"]
        family = (
            name_table.getDebugName(1)
            or name_table.getDebugName(4)
            or font_id[:12]
        )
        weight = 400
        if "OS/2" in font:
            weight = int(font["OS/2"].usWeightClass)
        style = "italic" if font["post"].italicAngle else "normal"
    except FontError:
        raise
    except Exception as exc:  # noqa: BLE001 - AssertionError, KeyError, ...
        detail = str(exc) or exc.__class__.__name__
        raise FontError(f"unreadable or corrupt font: {detail}") from exc
    finally:
        if font is not None:
            font.close()

    return FontInfo(
        font_id=font_id,
        family=family.strip(),
        codepoints=frozenset(covered),
        original_size=len(data),
        filename="",
        weight=weight,
        style=style,
    )
