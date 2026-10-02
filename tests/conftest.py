import os
import tempfile

_DATA = tempfile.mkdtemp(prefix="fontsubset-test-")
os.environ["FONT_SUBSET_DATA"] = _DATA
os.environ.setdefault("MAX_FONT_BYTES", str(2 * 1024 * 1024))
