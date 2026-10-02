from __future__ import annotations

import uvicorn

uvicorn.run("app.main:app", host="127.0.0.1", port=8000)
