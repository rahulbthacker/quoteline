from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.common import Actor, CellState, LineId, ReviewKind, Schema, SourceRef, VendorId


class ModelReading(Schema):
    model: str
    raw_value: float | None
    raw_unit: str | None
    raw_currency: str | None
    confidence: float
    source_ref: SourceRef


class NormalizationStep(Schema):
    """One deterministic step. The arithmetic is done in Python, never by a model."""

    op: Literal["unit_factor", "pack_factor", "weight_factor", "fx", "discount", "carry_forward"]
    factor: float
    value_in: float
    value_out: float
    source: str = Field(description="conversion_table.yaml key, RFx field, or FX policy")


class Override(Schema):
    value: float
    actor: Actor
    reason: str
    at: datetime


class QuoteCell(Schema):
    vendor_id: VendorId
    line_id: LineId
    state: CellState
    inr_per_base: float | None = Field(
        default=None, description="None for not_quoted. Never rendered as 0 or blank."
    )
    raw_display: str | None = None
    readings: list[ModelReading] = Field(default_factory=list)
    agreement: float | None = None
    normalization_trace: list[NormalizationStep] = Field(default_factory=list)
    flag_reason: str | None = None
    override: Override | None = None


class ReviewOption(Schema):
    option_id: str
    label: str
    inr_per_base: float | None = None
    normalization_trace: list[NormalizationStep] = Field(default_factory=list)


class CellRef(Schema):
    vendor_id: VendorId
    line_id: LineId


class ReviewItem(Schema):
    id: str
    cells: list[CellRef]
    kind: ReviewKind
    reason: str
    options: list[ReviewOption] = Field(default_factory=list)
    status: Literal["open", "resolved", "asked_vendor"] = "open"
