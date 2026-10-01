from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from app.schemas.common import CellState, LineId, ReviewKind, Schema, SourceRef, VendorId


class ModelReading(Schema):
    role: Literal["primary", "secondary"]
    model: str
    raw_value: float | None
    raw_unit: str | None
    unit_code: str
    raw_currency: str | None
    confidence: float
    alternatives: list[float] = Field(default_factory=list)
    not_quoted: bool = False
    notes: str | None = None
    match_reason: str | None = None
    source_ref: SourceRef


class NormalizationStep(Schema):
    """One deterministic step. The arithmetic is done in Python, never by a model."""

    op: Literal["unit_factor", "pack_factor", "weight_factor", "fx", "discount", "carry_forward"]
    factor: float
    value_in: float
    value_out: float
    source: str = Field(description="conversion_table.yaml key, RFx field, or FX policy")


class Override(Schema):
    action: Literal["override", "exclude"]
    value: float | None
    actor: str
    reason: str
    at: datetime


class QuoteCell(Schema):
    vendor_id: VendorId
    line_id: LineId
    state: CellState
    inr_per_base: float | None = Field(
        default=None,
        description="Counted value. None unless the cell is confident or overridden with a value.",
    )
    display_inr: float | None = Field(
        default=None, description="Provisional value shown for a cell in review; never totalled"
    )
    extended_inr: float | None = None
    excluded: bool = False
    is_lowest: bool = False
    how: str = "explicit"
    raw_display: str | None = None
    annotation: str | None = None
    readings: list[ModelReading] = Field(default_factory=list)
    agreement: float | None = None
    normalization_trace: list[NormalizationStep] = Field(default_factory=list)
    flag_reason: str | None = None
    review_item_ids: list[str] = Field(default_factory=list)
    resolution_note: str | None = None
    override: Override | None = None


class ReviewOption(Schema):
    option_id: str
    label: str
    inr_per_base: float | None = None
    note: str | None = None
    normalization_trace: list[NormalizationStep] = Field(default_factory=list)
    lines: list[LineId] = Field(default_factory=list)


class CellRef(Schema):
    vendor_id: VendorId
    line_id: LineId


class ReviewItem(Schema):
    id: str
    vendor_id: VendorId
    vendor_name: str
    cells: list[CellRef]
    kind: ReviewKind
    title: str
    reason: str
    evidence: str | None = None
    source: SourceRef | None = None
    readings: list[ModelReading] = Field(default_factory=list)
    agreement: float | None = None
    options: list[ReviewOption] = Field(default_factory=list)
    blocks_cells: bool = Field(description="True if the cells stay out of totals while open")
    status: Literal["open", "resolved", "asked_vendor"] = "open"
    resolution: dict[str, Any] | None = None
    detail: dict[str, Any] = Field(default_factory=dict)


class VendorTotals(Schema):
    extended_inr: float
    lines_counted: int
    needs_review: int
    not_quoted: int
    excluded: int


class Freight(Schema):
    kind: Literal["included", "lump_sum", "extra_unpriced", "not_stated"]
    amount_inr: float | None = None
    statement: str | None = None


class GridVendor(Schema):
    vendor_id: VendorId
    name: str
    has_reply: bool
    format: str | None = None
    format_label: str | None = None
    file: str | None = None
    lines_quoted: int = 0
    currency: str | None = None
    quality: Literal["Pass", "Partial", "Fail"] | None = None
    freight: Freight
    totals: VendorTotals
    agreement: float | None = None
    models: dict[str, str | None] = Field(default_factory=dict)
    extraction_error: str | None = None


class GridLine(Schema):
    line_id: LineId
    description: str
    qty: int
    uom: str
    last_year_inr: float | None
    cells: dict[VendorId, QuoteCell]


class Assumptions(Schema):
    base_unit: str
    fx: str
    freight: str
    tax: str


class RunStats(Schema):
    model_calls: int
    failed_calls: int
    cost_inr: float
    latency_s: float
    agreement: float | None


class Grid(Schema):
    rfx_id: str
    title: str
    assumptions: Assumptions
    vendors: list[GridVendor]
    lines: list[GridLine]
    review_open: int
    review_blocking_cells: int
    counts: dict[str, int]
    run: RunStats
