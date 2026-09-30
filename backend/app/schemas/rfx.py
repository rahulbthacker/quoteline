from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import Field

from app.schemas.common import LineId, Schema


class LineSpec(Schema):
    ply: int | None = None
    gsm: int | None = None
    dims_mm: tuple[int, ...] | None = Field(default=None, description="L x W x H as quoted")
    print: str | None = None
    board_weight_kg_per_pc: float | None = Field(
        default=None, description="Used to convert per-kg quotes; recorded in the trace"
    )


class LineItem(Schema):
    line_id: LineId
    description: str
    spec: LineSpec
    qty: int
    uom: str
    last_year_price_inr: float | None = Field(
        default=None, description="INR per base unit; resolves 'rest same as last year'"
    )


class FxPolicy(Schema):
    source: str
    rate: float = Field(description="INR per 1 unit of foreign currency")
    foreign_currency: str = "USD"
    as_of: date


class Question(Schema):
    question_id: str
    text: str
    mandatory: bool = False


class Terms(Schema):
    payment: str | None = None
    delivery: str | None = None
    validity_days: int | None = None
    assumptions: list[str] = Field(default_factory=list)


class RFx(Schema):
    id: str
    title: str
    category: str
    base_unit: Literal["per_1000_pcs"] = "per_1000_pcs"
    currency: Literal["INR"] = "INR"
    fx_policy: FxPolicy
    freight_policy: str
    tax_policy: str
    terms: Terms
    questionnaire: list[Question]
    line_items: list[LineItem]
