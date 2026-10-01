"""Quoteline API."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import admin, compare, decide, rfx
from app.db import init_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Quoteline", version="0.1.0", lifespan=lifespan)
for module in (admin, rfx, compare, decide):
    app.include_router(module.router)
