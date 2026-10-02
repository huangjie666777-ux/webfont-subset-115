from __future__ import annotations

import io
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from . import builder, config, fonts, planner, storage
from .fonts import FontError
from .planner import PlanningError


class BuildRequest(BaseModel):
    texts: list[str] = Field(default_factory=list)
    font_ids: list[str] = Field(default_factory=list)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    storage.init_dirs()
    builder.restore_jobs()
    yield


app = FastAPI(title="Web Font Subset Service", version="1.0.0", lifespan=lifespan)


@app.get("/")
def index() -> dict[str, Any]:
    return {
        "service": "web-font-subset",
        "limits": {
            "max_font_bytes": config.MAX_FONT_BYTES,
            "max_texts": config.MAX_TEXTS,
            "max_text_chars_per_item": config.MAX_TEXT_CHARS,
            "max_total_text_chars": config.MAX_TOTAL_TEXT_CHARS,
            "max_build_fonts": config.MAX_BUILD_FONTS,
        },
        "endpoints": [
            "POST /fonts",
            "GET /fonts/{font_id}",
            "POST /builds",
            "GET /builds/{job_id}",
            "GET /builds/{job_id}/download",
        ],
    }


def _read_limited(file: UploadFile, limit: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = file.file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise HTTPException(
                status_code=413,
                detail=f"font exceeds maximum upload size of {limit} bytes",
            )
        chunks.append(chunk)
    return b"".join(chunks)


@app.post("/fonts")
async def upload_font(request: Request, file: UploadFile = File(...)) -> dict[str, Any]:
    declared = request.headers.get("content-length")
    if declared is not None:
        try:
            if int(declared) > config.MAX_FONT_BYTES + 16 * 1024:
                raise HTTPException(status_code=413, detail="upload too large")
        except ValueError:
            pass
    data = _read_limited(file, config.MAX_FONT_BYTES)
    if not data:
        raise HTTPException(status_code=400, detail="empty upload")
    try:
        info = fonts.validate_font(data)
    except FontError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    meta = {
        "font_id": info.font_id,
        "filename": file.filename or "",
        "family": info.family,
        "original_size": info.original_size,
        "weight": info.weight,
        "style": info.style,
    }
    created = storage.save_font_if_absent(info.font_id, data, meta)
    return {
        "font_id": info.font_id,
        "already_present": not created,
        "family": info.family,
        "size_bytes": info.original_size,
        "unicode_coverage": [f"U+{cp:04X}" for cp in sorted(info.codepoints)],
        "coverage_count": len(info.codepoints),
    }


@app.get("/fonts/{font_id}")
def font_status(font_id: str) -> dict[str, Any]:
    meta = storage.load_font_meta(font_id)
    if meta is None or not storage.has_font(font_id):
        raise HTTPException(status_code=404, detail="font not found")
    info = fonts.validate_font(storage.font_path(font_id).read_bytes())
    return {
        "font_id": font_id,
        "family": info.family,
        "size_bytes": info.original_size,
        "unicode_coverage": [f"U+{cp:04X}" for cp in sorted(info.codepoints)],
    }


@app.post("/builds")
async def create_build(req: BuildRequest) -> dict[str, Any]:
    if not req.font_ids:
        raise HTTPException(status_code=400, detail="font_ids must not be empty")
    if len(req.font_ids) > config.MAX_BUILD_FONTS:
        raise HTTPException(status_code=400, detail="too many font_ids")
    if len(req.texts) > config.MAX_TEXTS:
        raise HTTPException(status_code=413, detail="too many text items")
    total = sum(len(t) for t in req.texts)
    if total > config.MAX_TOTAL_TEXT_CHARS:
        raise HTTPException(status_code=413, detail="combined text too large")
    for t in req.texts:
        if len(t) > config.MAX_TEXT_CHARS:
            raise HTTPException(status_code=413, detail="text item too large")

    ordered_ids: list[str] = []
    for fid in req.font_ids:
        if fid not in ordered_ids:
            ordered_ids.append(fid)
    for fid in ordered_ids:
        if not storage.has_font(fid):
            raise HTTPException(status_code=404, detail=f"unknown font_id: {fid}")

    coverage = {}
    for fid in ordered_ids:
        try:
            coverage[fid] = fonts.validate_font(
                storage.font_path(fid).read_bytes()
            ).codepoints
        except FontError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    codepoints = planner.collect_codepoints(req.texts)
    if not codepoints:
        raise HTTPException(status_code=400, detail="no usable codepoints in texts")
    try:
        plan = planner.plan_fallback(codepoints, ordered_ids, coverage)
    except PlanningError as exc:
        missing = exc.args[0]
        return JSONResponse(
            status_code=422,
            content={"detail": "missing codepoints", "missing": [f"U+{cp:04X}" for cp in missing]},
        )

    job_id = builder.new_job_id()
    job = builder.run_build(job_id, plan)
    if job.status != "success":
        raise HTTPException(status_code=500, detail=f"build failed: {job.error}")
    return {"status": "success", **(job.result or {})}


@app.get("/builds/{job_id}")
def build_status(job_id: str) -> dict[str, Any]:
    job = builder.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="build not found")
    return {
        "job_id": job.job_id,
        "status": job.status,
        "error": job.error,
        "result": job.result,
    }


@app.get("/builds/{job_id}/download")
def download_build(job_id: str) -> FileResponse:
    path = builder.package_path(job_id)
    if path is None:
        raise HTTPException(status_code=404, detail="package not available")
    return FileResponse(
        path,
        media_type="application/zip",
        filename=f"{job_id}.zip",
    )
