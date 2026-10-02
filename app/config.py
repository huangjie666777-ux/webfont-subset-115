from __future__ import annotations

import os
from pathlib import Path


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return int(raw) if raw else default


BASE_DIR = Path(os.environ.get("FONT_SUBSET_DATA", Path(__file__).resolve().parent.parent / "data"))
FONT_DIR = BASE_DIR / "fonts"
JOB_DIR = BASE_DIR / "jobs"
TMP_DIR = BASE_DIR / "tmp"

MAX_FONT_BYTES = _int("MAX_FONT_BYTES", 15 * 1024 * 1024)
MAX_TEXTS = _int("MAX_TEXTS", 500)
MAX_TEXT_CHARS = _int("MAX_TEXT_CHARS", 200_000)
MAX_TOTAL_TEXT_CHARS = _int("MAX_TOTAL_TEXT_CHARS", 2_000_000)
MAX_BUILD_FONTS = _int("MAX_BUILD_FONTS", 16)

FAMILY_NAME = "SubsetWeb"
