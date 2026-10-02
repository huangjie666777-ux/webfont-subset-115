from __future__ import annotations

import json
import shutil
import threading
import uuid
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import config, storage, subset
from .planner import Plan, unicode_range_css

FONTS_SUBDIR = Path("fonts")
CSS_NAME = "fonts.css"
MANIFEST_NAME = "manifest.json"
ZIP_NAME = "package.zip"

builds_lock = threading.RLock()
# job_id -> staging dir of in-flight builds (completed jobs live in JOB_DIR)
in_flight: dict[str, Path] = {}


@dataclass
class JobStatus:
    job_id: str
    status: str = "running"
    error: str | None = None
    detail: Any = None
    result: dict[str, Any] | None = None


jobs: dict[str, JobStatus] = {}


def new_job_id() -> str:
    return uuid.uuid4().hex


def get_job(job_id: str) -> JobStatus | None:
    with builds_lock:
        job = jobs.get(job_id)
        if job is not None:
            return job
        if storage.is_job_completed(job_id):
            return JobStatus(job_id=job_id, status="success")
    return None


def _write_css(entries: list[dict[str, Any]], path: Path) -> None:
    lines = []
    for index, entry in enumerate(entries):
        weight = entry.get("weight", 400)
        style = entry.get("style", "normal")
        lines.append("@font-face {")
        lines.append(f"  font-family: {json.dumps(config.FAMILY_NAME)};")
        lines.append(f"  font-weight: {weight};")
        lines.append(f"  font-style: {style};")
        lines.append(
            f"  src: url(\"fonts/{entry['file']}\") format(\"woff2\");"
        )
        lines.append(f"  unicode-range: {unicode_range_css(entry['codepoints'])};")
        lines.append("}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _build(job_id: str, plan: Plan, stage: Path) -> dict[str, Any]:
    stage.mkdir(parents=True, exist_ok=True)
    (stage / FONTS_SUBDIR).mkdir()
    css_entries: list[dict[str, Any]] = []
    manifest_fonts: list[dict[str, Any]] = []

    for index, font_id in enumerate(plan.used_font_ids, start=1):
        codepoints = sorted(plan.assignment[font_id])
        meta = storage.load_font_meta(font_id)
        src = storage.font_path(font_id)
        file_name = f"font{index}-{font_id[:12]}.woff2"
        out = stage / FONTS_SUBDIR / file_name
        output_size = subset.subset_to_woff2(src, codepoints, out)
        css_entries.append(
            {
                "file": file_name,
                "codepoints": codepoints,
                "weight": (meta or {}).get("weight", 400),
                "style": (meta or {}).get("style", "normal"),
            }
        )
        manifest_fonts.append(
            {
                "source_font_id": font_id,
                "source_filename": (meta or {}).get("filename"),
                "output_file": f"fonts/{file_name}",
                "assigned_codepoints": [f"U+{cp:04X}" for cp in codepoints],
                "original_bytes": src.stat().st_size,
                "output_bytes": output_size,
            }
        )

    _write_css(css_entries, stage / CSS_NAME)
    manifest = {
        "job_id": job_id,
        "family": config.FAMILY_NAME,
        "css": CSS_NAME,
        "requested_codepoints": [f"U+{cp:04X}" for cp in plan.codepoints],
        "fonts": manifest_fonts,
    }
    (stage / MANIFEST_NAME).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    zip_tmp = stage / ZIP_NAME
    with zipfile.ZipFile(zip_tmp, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(stage / CSS_NAME, CSS_NAME)
        zf.write(stage / MANIFEST_NAME, MANIFEST_NAME)
        for entry in css_entries:
            rel = f"fonts/{entry['file']}"
            zf.write(stage / rel, rel)
    return manifest


def run_build(job_id: str, plan: Plan) -> JobStatus:
    """Run a build in its own staging dir; publish only on full success."""
    stage = config.TMP_DIR / f"build-{job_id}"
    with builds_lock:
        jobs[job_id] = JobStatus(job_id=job_id)
        in_flight[job_id] = stage
    try:
        manifest = _build(job_id, plan, stage)
        dest = storage.job_dir(job_id)
        dest.parent.mkdir(parents=True, exist_ok=True)
        # Atomic publish: rename is atomic on the same filesystem.
        stage.replace(dest)
        result = {
            "job_id": job_id,
            "css": CSS_NAME,
            "manifest": MANIFEST_NAME,
            "fonts": [f["output_file"] for f in manifest["fonts"]],
            "download": f"/builds/{job_id}/download",
        }
        with builds_lock:
            jobs[job_id] = JobStatus(job_id=job_id, status="success", result=result)
        return jobs[job_id]
    except Exception as exc:  # noqa: BLE001
        shutil.rmtree(stage, ignore_errors=True)
        with builds_lock:
            jobs[job_id] = JobStatus(
                job_id=job_id, status="failed", error=str(exc)
            )
        return jobs[job_id]
    finally:
        with builds_lock:
            in_flight.pop(job_id, None)


def restore_jobs() -> None:
    with builds_lock:
        for job_id in storage.list_completed_jobs():
            jobs[job_id] = JobStatus(job_id=job_id, status="success")


def package_path(job_id: str) -> Path | None:
    p = storage.job_dir(job_id) / ZIP_NAME
    return p if p.is_file() else None
