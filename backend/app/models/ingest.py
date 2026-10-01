"""App state for the RFx, the replies and what the models read from them."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _now() -> datetime:
    return datetime.now(UTC)


class RfxRow(Base):
    __tablename__ = "rfx"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class VendorRow(Base):
    __tablename__ = "vendors"

    rfx_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    vendor_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    contact: Mapped[str | None] = mapped_column(String(128))
    email: Mapped[str | None] = mapped_column(String(128))
    city: Mapped[str | None] = mapped_column(String(64))
    position: Mapped[int] = mapped_column(Integer, default=0)  # column order in the grid


class ReplyFileRow(Base):
    __tablename__ = "reply_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rfx_id: Mapped[str] = mapped_column(String(32), index=True)
    vendor_id: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(256))
    path: Mapped[str | None] = mapped_column(String(512))
    parent: Mapped[str | None] = mapped_column(String(256))  # the email that carried it
    format: Mapped[str] = mapped_column(String(16))
    kind: Mapped[str] = mapped_column(String(32))
    needs_vision: Mapped[bool] = mapped_column(Boolean, default=False)
    pages: Mapped[int | None] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    summary: Mapped[str | None] = mapped_column(Text)
    routing: Mapped[dict | None] = mapped_column(JSON)
    parsed_text: Mapped[str | None] = mapped_column(Text)  # what the models were shown
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    run_id: Mapped[str] = mapped_column(String(64))


class ExtractionCallRow(Base):
    """One per (quote file, extractor role): did the read succeed, and how well did it agree."""

    __tablename__ = "extraction_calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rfx_id: Mapped[str] = mapped_column(String(32), index=True)
    vendor_id: Mapped[str] = mapped_column(String(32), index=True)
    file: Mapped[str] = mapped_column(String(256))
    role: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16))  # ok | model_error
    error: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(String(64))
    call_id: Mapped[str | None] = mapped_column(String(32))
    agreement: Mapped[float | None] = mapped_column(Float)
    notes: Mapped[str | None] = mapped_column(Text)
    run_id: Mapped[str] = mapped_column(String(64))


class ExtractionRow(Base):
    __tablename__ = "extractions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rfx_id: Mapped[str] = mapped_column(String(32), index=True)
    vendor_id: Mapped[str] = mapped_column(String(32), index=True)
    file: Mapped[str] = mapped_column(String(256))
    role: Mapped[str] = mapped_column(String(32))
    line_id: Mapped[str | None] = mapped_column(String(8), index=True)
    payload: Mapped[dict] = mapped_column(JSON)  # schemas.Extraction
    run_id: Mapped[str] = mapped_column(String(64))


class ConditionRow(Base):
    __tablename__ = "conditions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rfx_id: Mapped[str] = mapped_column(String(32), index=True)
    vendor_id: Mapped[str] = mapped_column(String(32), index=True)
    file: Mapped[str] = mapped_column(String(256))
    role: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict] = mapped_column(JSON)  # schemas.Condition
    run_id: Mapped[str] = mapped_column(String(64))
