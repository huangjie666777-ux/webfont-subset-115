IGNORED_CODEPOINTS = {0x09, 0x0A, 0x0D}


class MissingGlyphs(Exception):
    def __init__(self, codepoints):
        self.codepoints = sorted(codepoints)
        super().__init__(
            "no font covers codepoints: "
            + ", ".join(f"U+{cp:04X}" for cp in self.codepoints)
        )


def extract_codepoints(texts):
    seen = set()
    ordered = []
    for text in texts:
        for ch in text:
            cp = ord(ch)
            if cp in IGNORED_CODEPOINTS or cp in seen:
                continue
            seen.add(cp)
            ordered.append(cp)
    return ordered


def plan(codepoints, coverages):
    """Assign each codepoint to the first font (in order) covering it."""
    assignment = {}
    missing = []
    for cp in codepoints:
        for font_id, cov in coverages:
            if cp in cov:
                assignment[cp] = font_id
                break
        else:
            missing.append(cp)
    if missing:
        raise MissingGlyphs(missing)
    per_font = {}
    for cp, font_id in assignment.items():
        per_font.setdefault(font_id, []).append(cp)
    for cps in per_font.values():
        cps.sort()
    return per_font


def merge_ranges(codepoints):
    """Merge sorted codepoints into (start, end) inclusive ranges."""
    ranges = []
    for cp in sorted(codepoints):
        if ranges and cp == ranges[-1][1] + 1:
            ranges[-1][1] = cp
        else:
            ranges.append([cp, cp])
    return [(start, end) for start, end in ranges]


def unicode_range(codepoints):
    parts = []
    for start, end in merge_ranges(codepoints):
        if start == end:
            parts.append(f"U+{start:04X}")
        else:
            parts.append(f"U+{start:04X}-{end:04X}")
    return ", ".join(parts)
