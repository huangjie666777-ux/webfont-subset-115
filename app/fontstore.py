import io
import json
import os
import uuid

from fontTools.ttLib import TTFont, TTLibError

from . import config


class FontRejected(Exception):
    pass


def _coverage(font):
    cmap = font.getBestCmap()
    if not cmap:
        return set()
    return {cp for cp, name in cmap.items() if name != ".notdef"}


def validate_and_load(data):
    if len(data) < 4:
        raise FontRejected("file too small to be a font")
    if data[:4] == b"ttcf":
        raise FontRejected("TrueType/OpenType collections are not supported")
    try:
        font = TTFont(io.BytesIO(data), lazy=True)
    except TTLibError as exc:
        raise FontRejected(f"unparseable or corrupt font: {exc}")
    try:
        if "glyf" not in font:
            raise FontRejected("only TrueType fonts with a glyf table are supported")
        if "fvar" in font:
            raise FontRejected("variable fonts are not supported")
        coverage = _coverage(font)
    finally:
        font.close()
    return coverage


class FontStore:
    def __init__(self, font_dir=None):
        self.font_dir = font_dir or config.FONT_DIR
        os.makedirs(self.font_dir, exist_ok=True)

    def _path(self, font_id):
        return os.path.join(self.font_dir, f"{font_id}.ttf")

    def _meta_path(self, font_id):
        return os.path.join(self.font_dir, f"{font_id}.json")

    def add(self, data):
        coverage = validate_and_load(data)
        font_id = uuid.uuid4().hex
        tmp = self._path(font_id) + ".tmp"
        with open(tmp, "wb") as fh:
            fh.write(data)
        os.replace(tmp, self._path(font_id))
        meta = {
            "font_id": font_id,
            "size": len(data),
            "coverage": sorted(coverage),
        }
        with open(self._meta_path(font_id), "w") as fh:
            json.dump(meta, fh)
        return font_id, coverage

    def exists(self, font_id):
        return os.path.exists(self._path(font_id)) and os.path.exists(self._meta_path(font_id))

    def load_meta(self, font_id):
        if not self.exists(font_id):
            raise KeyError(font_id)
        with open(self._meta_path(font_id)) as fh:
            return json.load(fh)

    def load_font(self, font_id):
        if not self.exists(font_id):
            raise KeyError(font_id)
        return TTFont(self._path(font_id), lazy=True)

    def coverage(self, font_id):
        return set(self.load_meta(font_id)["coverage"])
