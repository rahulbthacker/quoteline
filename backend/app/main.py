"""Quoteline API, and in demo mode the built frontend as well.

API routes are served both at the root (used by tests and the Vite dev proxy) and under
/api (used by the built frontend). When frontend/dist exists, browser navigations get the
single-page app; everything else is the API.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse

from app.api import admin, compare, decide, rfx
from app.config import REPO_ROOT
from app.db import init_db

DIST = REPO_ROOT / "frontend" / "dist"


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Quoteline", version="0.1.0", lifespan=lifespan)
for module in (admin, rfx, compare, decide):
    app.include_router(module.router)
    app.include_router(module.router, prefix="/api", include_in_schema=False)


@app.middleware("http")
async def single_page_app(request: Request, call_next):
    path = request.url.path
    if request.method == "GET" and not path.startswith("/api") and DIST.is_dir():
        asset = (DIST / path.lstrip("/")).resolve()
        if path != "/" and asset.is_file() and DIST.resolve() in asset.parents:
            return FileResponse(asset)
        if "text/html" in request.headers.get("accept", ""):
            return FileResponse(DIST / "index.html")
    return await call_next(request)
