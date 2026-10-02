from __future__ import annotations

import contextlib
import io
import json
import socket
import threading
import time
import urllib.error
import urllib.request
import zipfile

import uvicorn

from app.fonts import font_id_of
from app.main import app

SANS = "examples/fonts/DejaVuSans.ttf"
SERIF = "examples/fonts/DejaVuSerif.ttf"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@contextlib.contextmanager
def server():
    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server_obj = uvicorn.Server(config)
    thread = threading.Thread(target=server_obj.run, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            urllib.request.urlopen(base, timeout=1).read()
            break
        except Exception:
            time.sleep(0.05)
    try:
        yield base
    finally:
        server_obj.should_exit = True
        thread.join(timeout=5)


def _multipart(path: str, field: str = "file") -> tuple[bytes, str]:
    boundary = "----testboundary123"
    data = open(path, "rb").read()
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{field}"; filename="f.ttf"\r\n'
        "Content-Type: font/ttf\r\n\r\n"
    ).encode() + data + f"\r\n--{boundary}--\r\n".encode()
    return body, f"multipart/form-data; boundary={boundary}"


def _post_json(url: str, payload: dict):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _upload(base: str, path: str):
    body, ctype = _multipart(path)
    req = urllib.request.Request(
        f"{base}/fonts", data=body, headers={"Content-Type": ctype}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def test_full_flow():
    with server() as base:
        sans = _upload(base, SANS)
        serif = _upload(base, SERIF)
        sid, rid = sans["font_id"], serif["font_id"]
        # Re-upload same bytes: same ID, not overwritten
        again = _upload(base, SANS)
        assert again["font_id"] == sid and again["already_present"] is True

        # \u02ef exists only in serif; TAB/CR/LF ignored
        status, resp = _post_json(
            f"{base}/builds",
            {"texts": ["AB\tA\n\u02ef"], "font_ids": [sid, rid]},
        )
        assert status == 200, resp
        job = resp["job_id"]
        # both fonts used: A/B -> sans, \u02ef -> serif
        assert resp["fonts"] == [
            f"fonts/font1-{sid[:12]}.woff2",
            f"fonts/font2-{rid[:12]}.woff2",
        ]

        with urllib.request.urlopen(f"{base}/builds/{job}/download", timeout=30) as d:
            blob = d.read()
            assert d.headers["Content-Type"] == "application/zip"
        zf = zipfile.ZipFile(io.BytesIO(blob))
        names = zf.namelist()
        assert names == [
            "fonts.css",
            "manifest.json",
            f"fonts/font1-{sid[:12]}.woff2",
            f"fonts/font2-{rid[:12]}.woff2",
        ]
        css = zf.read("fonts.css").decode()
        assert css.count("@font-face") == 2
        assert "font-family: \"SubsetWeb\"" in css
        assert "fonts/font1-" in css and "U+0041-0042" in css
        assert "U+02EF" in css
        for n in names[2:]:
            assert zf.read(n)[:4] == b"wOF2"
        manifest = json.loads(zf.read("manifest.json"))
        for f in manifest["fonts"]:
            assert f["output_bytes"] < f["original_bytes"]
            assert f["source_font_id"] in (sid, rid)
        assert manifest["requested_codepoints"] == ["U+0041", "U+0042", "U+02EF"]


def test_missing_codepoints_rejected():
    with server() as base:
        sans = _upload(base, SANS)
        status, resp = _post_json(
            f"{base}/builds",
            {"texts": ["\u4e2d\u6587"], "font_ids": [sans["font_id"]]},
        )
        assert status == 422
        assert resp["missing"] == ["U+4E2D", "U+6587"]


def test_bad_uploads_and_limits():
    with server() as base:
        # corrupt
        body = (
            b"------b\r\nContent-Disposition: form-data; name=\"file\"; filename=\"x.ttf\"\r\n\r\n"
            b"junkdata\r\n------b--\r\n"
        )
        req = urllib.request.Request(
            f"{base}/fonts",
            data=body,
            headers={"Content-Type": "multipart/form-data; boundary=----b"},
            method="POST",
        )
        try:
            urllib.request.urlopen(req)
            assert False
        except urllib.error.HTTPError as e:
            assert e.code == 422

        # unknown font id
        status, resp = _post_json(
            f"{base}/builds", {"texts": ["A"], "font_ids": ["0" * 64]}
        )
        assert status == 404

        # download of random job
        try:
            urllib.request.urlopen(f"{base}/builds/{'f'*32}/download")
            assert False
        except urllib.error.HTTPError as e:
            assert e.code == 404


def test_concurrent_builds_and_size_limit():
    with server() as base:
        sans = _upload(base, SANS)
        sid = sans["font_id"]
        results = {}

        def build(i):
            results[i] = _post_json(f"{base}/builds", {"texts": [chr(0x41 + i)], "font_ids": [sid]})

        threads = [threading.Thread(target=build, args=(i,)) for i in range(4)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        jobs = set()
        for code, resp in results.values():
            assert code == 200
            jobs.add(resp["job_id"])
        assert len(jobs) == 4  # no clobbering

        # upload size limit (env MAX_FONT_BYTES=2MiB)
        big = SANS  # 757KB, fine
        _upload(base, big)
        oversized = b"\x00\x01\x00\x00" + b"\x00" * (3 * 1024 * 1024)
        boundary = "x"
        body = (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"z\"\r\n\r\n"
        ).encode() + oversized + f"\r\n--{boundary}--\r\n".encode()
        req = urllib.request.Request(
            f"{base}/fonts",
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        try:
            urllib.request.urlopen(req, timeout=30)
            assert False
        except urllib.error.HTTPError as e:
            assert e.code in (413, 422)


def test_original_font_not_modified():
    data = open(SANS, "rb").read()
    assert font_id_of(data)
    with server() as base:
        info = _upload(base, SANS)
        _post_json(
            f"{base}/builds",
            {"texts": ["HELLO"], "font_ids": [info["font_id"]]},
        )
    assert open(SANS, "rb").read() == data
