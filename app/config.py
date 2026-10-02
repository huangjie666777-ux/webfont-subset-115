import os

DATA_DIR = os.environ.get("FONT_SUBSET_DATA_DIR", "data")
FONT_DIR = os.path.join(DATA_DIR, "fonts")
BUILD_DIR = os.path.join(DATA_DIR, "builds")

MAX_UPLOAD_BYTES = int(os.environ.get("FONT_SUBSET_MAX_UPLOAD_BYTES", 20 * 1024 * 1024))
MAX_TEXT_CHARS = int(os.environ.get("FONT_SUBSET_MAX_TEXT_CHARS", 200_000))
MAX_TEXTS = int(os.environ.get("FONT_SUBSET_MAX_TEXTS", 10_000))
