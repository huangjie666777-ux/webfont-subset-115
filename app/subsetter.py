import io

from fontTools import subset


def subset_font(font, codepoints):
    """Subset a TTFont to the given codepoints and return WOFF2 bytes.

    Keeps all GSUB layout features (with their substitution closure),
    prunes GPOS to the retained glyphs, preserves glyph metrics and
    all name table entries (copyright / license).
    """
    options = subset.Options()
    options.flavor = "woff2"
    options.layout_features = ["*"]
    options.name_IDs = ["*"]
    options.name_legacy = True
    options.name_languages = ["*"]
    options.notdef_glyph = True
    options.notdef_outline = True
    options.glyph_names = True
    options.recalc_bounds = False
    options.recalc_average_width = False
    options.recalc_max_context = False
    options.drop_tables = list(options.drop_tables) 
    for keep in ("hmtx", "hhea", "name", "head", "maxp", "OS/2", "post", "cmap"):
        if keep in options.drop_tables:
            options.drop_tables.remove(keep)

    ss = subset.Subsetter(options=options)
    ss.populate(unicodes=list(codepoints))
    ss.subset(font)

    font.flavor = "woff2"
    buf = io.BytesIO()
    font.save(buf)
    return buf.getvalue()
