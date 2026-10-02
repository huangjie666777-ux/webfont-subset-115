import io
import json
import os
import zipfile

import pytest
from fastapi.testclient import TestClient
from fontTools.ttLib import TTFont, newTable

os.environ["FONT_SUBSET_DATA_DIR"] = "/tmp/fontsubset-test-data"

from app import config
from app.fontstore import FontStore
from app.builder import BuildStore
from app.main import app, font_store, build_store
from app.planner import extract_codepoints, merge_ranges, unicode_range

SANS = "examples/fonts/DejaVuSans.ttf"
SERIF = "examples/fonts/DejaVuSerif.ttf"


@pytest.fixture(autouse=True)
def fresh_dirs(tmp_path, monkeypatch):
    font_dir = tmp_path / "fonts"
    build_dir = tmp_path / "builds"
    font_store.font_dir = str(font_dir)
    os.makedirs(font_dir, exist_ok=True)
    build_store.build_dir = str(build_dir)
    os.makedirs(build_dir, exist_ok=True)
    yield


@pytest.fixture
def client():
    return TestClient(app)


def upload(client, path):
    with open(path, "rb") as fh:
        resp = client.post("/fonts", files={"file": (os.path.basename(path), fh, "font/ttf")})
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_upload_ok(client):
    info = upload(client, SANS)
    assert info["font_id"]
    assert info["coverage_count"] > 0
    assert "U+0041" in info["coverage"]
    got = client.get(f"/fonts/{info['font_id']}")
    assert got.status_code == 200
    assert got.json()["font_id"] == info["font_id"]


def test_upload_rejects_corrupt(client):
    resp = client.post("/fonts", files={"file": ("bad.ttf", b"not a font at all", "font/ttf")})
    assert resp.status_code == 422


def test_upload_rejects_collection(client):
    with open(SANS, "rb") as fh:
        data = b"ttcf" + fh.read()[4:]
    resp = client.post("/fonts", files={"file": ("coll.ttc", data, "font/ttf")})
    assert resp.status_code == 422
    assert "collection" in resp.json()["detail"]


def test_upload_rejects_variable(client):
    font = TTFont(SANS)
    fvar = newTable("fvar")
    fvar.axes = []
    fvar.instances = []
    font["fvar"] = fvar
    buf = io.BytesIO()
    font.save(buf)
    resp = client.post("/fonts", files={"file": ("var.ttf", buf.getvalue(), "font/ttf")})
    assert resp.status_code == 422
    assert "variable" in resp.json()["detail"]


def test_upload_rejects_cff_only(client):
    font = TTFont(SANS)
    del font["glyf"]
    del font["loca"]
    buf = io.BytesIO()
    font.save(buf)
    resp = client.post("/fonts", files={"file": ("cff.otf", buf.getvalue(), "font/ttf")})
    assert resp.status_code == 422
    assert "glyf" in resp.json()["detail"]


def test_extract_codepoints():
    cps = extract_codepoints(["ab\ta\nb\r", "ca"])
    assert cps == [ord("a"), ord("b"), ord("c")]


def test_unicode_range_merging():
    assert unicode_range([0x41, 0x42, 0x43, 0x50]) == "U+0041-0043, U+0050"
    assert merge_ranges([1, 2, 4]) == [(1, 2), (4, 4)]


def test_build_and_download(client):
    sans = upload(client, SANS)
    serif = upload(client, SERIF)
    resp = client.post("/builds", json={
        "texts": ["Hello\tWorld\n", "Hello again"],
        "font_ids": [sans["font_id"], serif["font_id"]],
        "family": "Demo",
    })
    assert resp.status_code == 201, resp.text
    body = resp.json()
    build_id = body["build_id"]
    manifest = body["manifest"]
    # all codepoints assigned to the first font (DejaVuSans covers them)
    assert len(manifest["fonts"]) == 1
    entry = manifest["fonts"][0]
    assert entry["source_font_id"] == sans["font_id"]
    assert entry["output_bytes"] < entry["original_bytes"]
    assert "U+0048" in entry["codepoints"]

    dl = client.get(f"/builds/{build_id}/download")
    assert dl.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(dl.content))
    names = set(zf.namelist())
    assert "fonts.css" in names
    assert "manifest.json" in names
    font_names = [n for n in names if n.startswith("fonts/")]
    assert len(font_names) == 1
    css = zf.read("fonts.css").decode()
    assert "font-family: 'Demo'" in css
    assert f"url('fonts/{sans['font_id']}.woff2')" in css
    assert "unicode-range:" in css
    # woff2 output is a valid subset
    raw = zf.read(font_names[0])
    assert raw[:4] == b"wOF2"
    sub = TTFont(io.BytesIO(raw))
    cmap = sub.getBestCmap()
    assert ord("H") in cmap
    assert ord("~") not in cmap  # not requested, not included
    names_table = sub["name"]
    assert any(n.nameID == 0 for n in names_table.names)  # copyright kept
    man = json.loads(zf.read("manifest.json"))
    assert man["fonts"][0]["source_font_id"] == sans["font_id"]


def test_build_missing_glyph_rejected(client):
    sans = upload(client, SANS)
    resp = client.post("/builds", json={
        "texts": ["abc中"],  # CJK not in DejaVuSans
        "font_ids": [sans["font_id"]],
    })
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["codepoints"] == ["U+4E2D"]
    # no build id was registered
    assert client.get("/builds/whatever/download").status_code == 404


def test_build_unknown_font(client):
    resp = client.post("/builds", json={"texts": ["a"], "font_ids": ["nope"]})
    assert resp.status_code == 404


def test_fallback_assignment(client):
    # first font lacks the glyphs, second font provides them
    sans = upload(client, SANS)
    serif = upload(client, SERIF)
    # DejaVuSans has no U+1D400 (math bold A); check coverage first
    sans_cov = set(client.get(f"/fonts/{sans['font_id']}").json()["coverage"])
    pick = next(cp for cp in range(0x300, 0x1FFFF)
                if f"U+{cp:04X}" not in sans_cov
                and f"U+{cp:04X}" in set(client.get(f"/fonts/{serif['font_id']}").json()["coverage"]))
    resp = client.post("/builds", json={
        "texts": ["A" + chr(pick)],
        "font_ids": [sans["font_id"], serif["font_id"]],
    })
    assert resp.status_code == 201, resp.text
    fonts = resp.json()["manifest"]["fonts"]
    assert len(fonts) == 2
    by_id = {f["source_font_id"]: f for f in fonts}
    assert by_id[sans["font_id"]]["codepoints"] == ["U+0041"]
    assert by_id[serif["font_id"]]["codepoints"] == [f"U+{pick:04X}"]


def test_unused_font_not_emitted(client):
    sans = upload(client, SANS)
    serif = upload(client, SERIF)
    resp = client.post("/builds", json={
        "texts": ["abc"],
        "font_ids": [sans["font_id"], serif["font_id"]],
    })
    assert resp.status_code == 201
    fonts = resp.json()["manifest"]["fonts"]
    assert [f["source_font_id"] for f in fonts] == [sans["font_id"]]


def test_gsub_closure_kept(client):
    sans = upload(client, SANS)
    resp = client.post("/builds", json={
        "texts": ["fi"],
        "font_ids": [sans["font_id"]],
    })
    assert resp.status_code == 201
    build_id = resp.json()["build_id"]
    dl = client.get(f"/builds/{build_id}/download")
    zf = zipfile.ZipFile(io.BytesIO(dl.content))
    sub = TTFont(io.BytesIO(zf.read(f"fonts/{sans['font_id']}.woff2")))
    assert "GSUB" in sub
    # ligature glyph "fi" (U+FB01) must survive via the GSUB closure
    assert "fi" in sub.getGlyphOrder()


def test_concurrent_builds(client):
    sans = upload(client, SANS)
    from concurrent.futures import ThreadPoolExecutor

    def do_build(i):
        return client.post("/builds", json={
            "texts": [f"text number {i}"],
            "font_ids": [sans["font_id"]],
        })

    with ThreadPoolExecutor(max_workers=4) as ex:
        resps = list(ex.map(do_build, range(8)))
    ids = set()
    for r in resps:
        assert r.status_code == 201, r.text
        ids.add(r.json()["build_id"])
    assert len(ids) == 8
    for bid in ids:
        assert client.get(f"/builds/{bid}/download").status_code == 200
