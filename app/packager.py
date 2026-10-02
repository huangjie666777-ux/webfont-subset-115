import io
import json
import zipfile

from .planner import unicode_range

CSS_NAME = "fonts.css"


def build_css(family, entries):
    """entries: list of (woff2_relpath, codepoints)."""
    blocks = []
    for path, codepoints in entries:
        blocks.append(
            "@font-face {\n"
            f"  font-family: '{family}';\n"
            "  font-style: normal;\n"
            "  font-weight: normal;\n"
            "  font-display: swap;\n"
            f"  src: url('{path}') format('woff2');\n"
            f"  unicode-range: {unicode_range(codepoints)};\n"
            "}"
        )
    return "\n\n".join(blocks) + "\n"


def build_zip(family, font_entries):
    """font_entries: list of dicts with keys:
    font_id, filename, codepoints, woff2_bytes, original_bytes.
    Returns (zip_bytes, manifest_dict)."""
    css_entries = [(f"fonts/{e['filename']}", e["codepoints"]) for e in font_entries]
    css = build_css(family, css_entries)
    manifest = {
        "family": family,
        "css": CSS_NAME,
        "fonts": [
            {
                "source_font_id": e["font_id"],
                "file": f"fonts/{e['filename']}",
                "codepoints": [f"U+{cp:04X}" for cp in e["codepoints"]],
                "unicode_range": unicode_range(e["codepoints"]),
                "original_bytes": e["original_bytes"],
                "output_bytes": len(e["woff2_bytes"]),
            }
            for e in font_entries
        ],
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(CSS_NAME, css)
        for e in font_entries:
            zf.writestr(f"fonts/{e['filename']}", e["woff2_bytes"])
        zf.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
    return buf.getvalue(), manifest
