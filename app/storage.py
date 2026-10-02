from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from . import config

_lock = threading.RLock()


def init_dirs() -> None:
    for d in (config.FONT_DIR, config.JOB_DIR, config.TMP_DIR):
        d.mkdir(parents=True, exist_ok=True)


def font_path(font_id: str) -> Path:
    return config.FONT_DIR / f"{font_id}.ttf"


def font_meta_path(font_id: str) -> Path:
    return config.FONT_DIR / f"{font_id}.json"


def has_font(font_id: str) -> bool:
    return font_path(font_id).is_file() and font_meta_path(font_id).is_file()


def save_font_if_absent(font_id: str, data: bytes, meta: dict[str, Any]) -> bool:
    """Atomically store a new font. Returns False if the ID already exists."""
    with _lock:
        if has_font(font_id):
            return False
        tmp = config.TMP_DIR / f"font-{font_id}.ttf"
        tmp_m = config.TMP_DIR / f"font-{font_id}.json"
        tmp.write_bytes(data)
        tmp_m.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(font_path(font_id))
        tmp_m.replace(font_meta_path(font_id))
        return True


def load_font_meta(font_id: str) -> dict[str, Any] | None:
    p = font_meta_path(font_id)
    if not p.is_file():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def job_dir(job_id: str) -> Path:
    return config.JOB_DIR / job_id



def list_completed_jobs() -> set[str]:
    if not config.JOB_DIR.exists():
        return set()
    return {
        p.name
        for p in config.JOB_DIR.iterdir()
        if p.is_dir() and (p / "package.zip").is_file() and (p / "manifest.json").is_file()
    }


def is_job_completed(job_id: str) -> bool:
    d = job_dir(job_id)
    return (d / "package.zip").is_file() and (d / "manifest.json").is_file()
