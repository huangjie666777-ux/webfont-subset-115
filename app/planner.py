from __future__ import annotations

from dataclasses import dataclass

IGNORED_CODEPOINTS = frozenset({0x09, 0x0A, 0x0D})  # TAB, CR, LF


class PlanningError(ValueError):
    pass


@dataclass(frozen=True)
class Plan:
    codepoints: list[int]
    # font_id -> ordered list of assigned codepoints
    assignment: dict[str, list[int]]
    used_font_ids: list[str]


def collect_codepoints(texts: list[str]) -> list[int]:
    """Deduplicate by Unicode code point, preserving first-appearance order.

    No Unicode normalization is performed. TAB/CR/LF are ignored.
    """
    seen: set[int] = set()
    ordered: list[int] = []
    for text in texts:
        for ch in text:
            cp = ord(ch)
            if cp in IGNORED_CODEPOINTS or cp in seen:
                continue
            seen.add(cp)
            ordered.append(cp)
    return ordered


def plan_fallback(
    codepoints: list[int], font_ids: list[str], coverage: dict[str, frozenset[int]]
) -> Plan:
    """Assign each codepoint to the first font that maps it to a non-.notdef glyph."""
    assignment: dict[str, list[int]] = {fid: [] for fid in font_ids}
    missing: list[int] = []
    for cp in codepoints:
        for fid in font_ids:
            if cp in coverage[fid]:
                assignment[fid].append(cp)
                break
        else:
            missing.append(cp)
    if missing:
        raise PlanningError(missing)
    used = [fid for fid in font_ids if assignment[fid]]
    return Plan(codepoints=codepoints, assignment=assignment, used_font_ids=used)


def merge_ranges(codepoints: list[int]) -> list[tuple[int, int]]:
    """Merge sorted codepoints into inclusive contiguous ranges."""
    ranges: list[tuple[int, int]] = []
    for cp in sorted(codepoints):
        if ranges and cp == ranges[-1][1] + 1:
            ranges[-1] = (ranges[-1][0], cp)
        else:
            ranges.append((cp, cp))
    return ranges


def unicode_range_css(codepoints: list[int]) -> str:
    parts = [
        f"U+{lo:04X}" if lo == hi else f"U+{lo:04X}-{hi:04X}"
        for lo, hi in merge_ranges(codepoints)
    ]
    return ", ".join(parts)
