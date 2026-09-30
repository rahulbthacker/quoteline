"""One row per model call attempt, successful or not (non-negotiable 7)."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class TraceRow(Base):
    __tablename__ = "traces"

    call_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    parent_run_id: Mapped[str | None] = mapped_column(String(64), index=True)
    rfx_id: Mapped[str | None] = mapped_column(String(32), index=True)
    role: Mapped[str] = mapped_column(String(32))
    provider: Mapped[str] = mapped_column(String(16))
    model: Mapped[str] = mapped_column(String(64))  # as requested
    served_model: Mapped[str | None] = mapped_column(String(64))  # as reported by the provider
    prompt_version: Mapped[str] = mapped_column(String(64))
    attempt: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16))  # ok | error
    error: Mapped[str | None] = mapped_column(Text)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int] = mapped_column(Integer)
    cost_inr: Mapped[float | None] = mapped_column(Float)  # null when the model has no price entry
    agreement: Mapped[float | None] = mapped_column(Float)  # extraction only, set by the service
    provider_request_id: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
