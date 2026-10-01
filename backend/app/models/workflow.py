"""Tables for everything a person decides: review items, overrides, quality, award, audit."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _now() -> datetime:
    return datetime.now(UTC)


class ReviewItemRow(Base):
    """A flag that needs a person. The id is stable across recomputation."""

    __tablename__ = "review_items"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    rfx_id: Mapped[str] = mapped_column(String(32), index=True)
    vendor_id: Mapped[str] = mapped_column(String(32), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    lines: Mapped[list] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16), default="open")  # open|asked_vendor|resolved
    resolution: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class CellDecisionRow(Base):
    """A buyer's override or exclusion of one cell. One live decision per cell."""

    __tablename__ = "cell_decisions"

    rfx_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    vendor_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    line_id: Mapped[str] = mapped_column(String(8), primary_key=True)
    action: Mapped[str] = mapped_column(String(16))  # override | exclude
    value: Mapped[float | None] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(String(64))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AuditEventRow(Base):
    """Append-only. Nothing in the app updates or deletes a row here."""

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rfx_id: Mapped[str] = mapped_column(String(32), index=True)
    actor_kind: Mapped[str] = mapped_column(String(8))  # system | user
    actor_id: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64))
    summary: Mapped[str] = mapped_column(Text)
    before: Mapped[dict | None] = mapped_column(JSON)
    after: Mapped[dict | None] = mapped_column(JSON)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class VendorQualityRow(Base):
    __tablename__ = "vendor_quality"

    rfx_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    vendor_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    answers: Mapped[list] = mapped_column(JSON)  # per question: status, answer, evidence
    overrides: Mapped[dict] = mapped_column(JSON, default=dict)  # question_id -> evaluator override
    model: Mapped[str | None] = mapped_column(String(64))
    call_id: Mapped[str | None] = mapped_column(String(32))
    error: Mapped[str | None] = mapped_column(Text)
    run_id: Mapped[str | None] = mapped_column(String(64))


class ScenarioRow(Base):
    __tablename__ = "scenarios"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    rfx_id: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(128))
    payload: Mapped[dict] = mapped_column(JSON)  # filters, source question, query, result
    created_by: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AwardRow(Base):
    __tablename__ = "awards"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    rfx_id: Mapped[str] = mapped_column(String(32), index=True)
    scenario_id: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(24), default="draft")
    approvals: Mapped[list] = mapped_column(JSON, default=list)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class OutboxRow(Base):
    """The email stub's log. Every row is a real .eml file under mail/outbox/."""

    __tablename__ = "outbox"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rfx_id: Mapped[str] = mapped_column(String(32), index=True)
    vendor_id: Mapped[str | None] = mapped_column(String(32))
    kind: Mapped[str] = mapped_column(String(24))  # rfx | clarification | approval_request
    to_address: Mapped[str] = mapped_column(String(128))
    subject: Mapped[str] = mapped_column(String(256))
    body: Mapped[str] = mapped_column(Text)
    path: Mapped[str] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(16))  # draft | sent
    review_item_id: Mapped[str | None] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AnalysisRow(Base):
    """One analyst exchange: the question, the query that ran, the rows and the answer."""

    __tablename__ = "analyses"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    rfx_id: Mapped[str] = mapped_column(String(32), index=True)
    question: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSON)
    asked_by: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
