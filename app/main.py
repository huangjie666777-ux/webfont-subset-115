import re

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from . import config
from .builder import BuildStore, UnknownFont
from .fontstore import FontRejected, FontStore
from .planner import MissingGlyphs

app = FastAPI(title="Web Font Subsetter")
font_store = FontStore()
build_store = BuildStore(font_store)

FAMILY_RE = re.compile(r"^[\w \-]{1,64}$")


class BuildRequest(BaseModel):
    texts: list[str] = Field(..., min_length=1)
    font_ids: list[str] = Field(..., min_length=1)
    family: str = "SubsetSans"


@app.post("/fonts", status_code=201)
async def upload_font(request: Request, file: UploadFile = File(...)):
    data = await file.read(config.MAX_UPLOAD_BYTES + 1)
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"font exceeds {config.MAX_UPLOAD_BYTES} bytes")
    try:
        font_id, coverage = font_store.add(data)
    except FontRejected as exc:
        raise HTTPException(422, str(exc))
    return {
        "font_id": font_id,
        "size": len(data),
        "coverage_count": len(coverage),
        "coverage": [f"U+{cp:04X}" for cp in sorted(coverage)],
    }


@app.get("/fonts/{font_id}")
async def font_info(font_id: str):
    try:
        meta = font_store.load_meta(font_id)
    except KeyError:
        raise HTTPException(404, "unknown font id")
    return {
        "font_id": font_id,
        "size": meta["size"],
        "coverage_count": len(meta["coverage"]),
        "coverage": [f"U+{cp:04X}" for cp in meta["coverage"]],
    }


@app.post("/builds", status_code=201)
async def create_build(req: BuildRequest):
    if len(req.texts) > config.MAX_TEXTS:
        raise HTTPException(413, "too many text entries")
    total = sum(len(t) for t in req.texts)
    if total > config.MAX_TEXT_CHARS:
        raise HTTPException(413, f"text exceeds {config.MAX_TEXT_CHARS} characters")
    if not FAMILY_RE.match(req.family):
        raise HTTPException(422, "invalid family name")
    try:
        build_id, manifest = await build_store.build(req.texts, req.font_ids, req.family)
    except UnknownFont as exc:
        raise HTTPException(404, str(exc))
    except MissingGlyphs as exc:
        raise HTTPException(
            422,
            detail={
                "error": "missing glyphs",
                "codepoints": [f"U+{cp:04X}" for cp in exc.codepoints],
            },
        )
    return {"build_id": build_id, "manifest": manifest}


@app.get("/builds/{build_id}/download")
async def download_build(build_id: str):
    path = build_store.get_zip(build_id)
    if path is None:
        raise HTTPException(404, "unknown or unfinished build id")
    return FileResponse(path, media_type="application/zip", filename=f"{build_id}.zip")
