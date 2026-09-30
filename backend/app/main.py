"""Quoteline API."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import ROLES, get_settings
from app.db import get_session, init_db
from app.models.trace import TraceRow
from app.schemas import Trace

SessionDep = Annotated[Session, Depends(get_session)]


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Quoteline", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "roles": {role: [str(spec) for spec in settings.chain(role)] for role in ROLES},
    }


@app.get("/traces", response_model=list[Trace])
def list_traces(session: SessionDep, run_id: str | None = None, limit: int = 200) -> list[TraceRow]:
    query = select(TraceRow)
    if run_id:
        query = query.where(TraceRow.parent_run_id == run_id)
    return list(session.scalars(query.order_by(TraceRow.created_at.desc()).limit(limit)).all())
