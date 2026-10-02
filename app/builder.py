import asyncio
import json
import os
import shutil
import uuid

from . import config, packager, planner, subsetter


class UnknownFont(Exception):
    def __init__(self, font_id):
        self.font_id = font_id
        super().__init__(f"unknown font id: {font_id}")


class BuildStore:
    def __init__(self, font_store, build_dir=None):
        self.font_store = font_store
        self.build_dir = build_dir or config.BUILD_DIR
        os.makedirs(self.build_dir, exist_ok=True)
        self._lock = asyncio.Lock()

    def _zip_path(self, build_id):
        return os.path.join(self.build_dir, build_id, "subset.zip")

    def get_zip(self, build_id):
        path = self._zip_path(build_id)
        if not os.path.exists(path):
            return None
        return path

    async def build(self, texts, font_ids, family="SubsetSans"):
        codepoints = planner.extract_codepoints(texts)
        coverages = []
        seen_ids = []
        for font_id in font_ids:
            if font_id in seen_ids:
                continue
            seen_ids.append(font_id)
            try:
                coverages.append((font_id, self.font_store.coverage(font_id)))
            except KeyError:
                raise UnknownFont(font_id)
        per_font = planner.plan(codepoints, coverages)

        build_id = uuid.uuid4().hex
        tmp_dir = os.path.join(self.build_dir, f".tmp-{build_id}")
        final_dir = os.path.join(self.build_dir, build_id)
        try:
            font_entries = []
            for font_id, _ in coverages:
                cps = per_font.get(font_id)
                if not cps:
                    continue  # unused fonts are not emitted
                font = self.font_store.load_font(font_id)
                try:
                    woff2 = await asyncio.to_thread(subsetter.subset_font, font, cps)
                finally:
                    font.close()
                font_entries.append({
                    "font_id": font_id,
                    "filename": f"{font_id}.woff2",
                    "codepoints": cps,
                    "woff2_bytes": woff2,
                    "original_bytes": self.font_store.load_meta(font_id)["size"],
                })
            zip_bytes, manifest = packager.build_zip(family, font_entries)

            os.makedirs(tmp_dir, exist_ok=False)
            with open(os.path.join(tmp_dir, "subset.zip"), "wb") as fh:
                fh.write(zip_bytes)
            with open(os.path.join(tmp_dir, "manifest.json"), "w") as fh:
                json.dump(manifest, fh, indent=2, ensure_ascii=False)
            async with self._lock:
                os.replace(tmp_dir, final_dir)
        except BaseException:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            shutil.rmtree(final_dir, ignore_errors=True)
            raise
        return build_id, manifest
