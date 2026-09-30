"""Shared value types. Pydantic is the contract for every structure that crosses a boundary."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Schema(BaseModel):
    model_config = ConfigDict(extra="forbid")


VendorId = str  # slug, e.g. "meridian"
LineId = str  # "L01".."L30"

CellState = Literal["confident", "needs_review", "not_quoted", "overridden"]

ReviewKind = Literal[
    "unit_ambiguity",
    "ocr_disagreement",
    "footnote_condition",
    "not_quoted",
    "model_error",
    "outlier",
    "missing_freight",
    "unmatched",
    "currency_mismatch",
]


class SourceRef(Schema):
    """Where a value came from. No value reaches the grid without one (non-negotiable 4)."""

    file: str
    locator: str = Field(description="Sheet!cell, page N, paragraph N, image region, email line")
    snippet: str = Field(description="Verbatim text the value was read from")
    bbox: tuple[float, float, float, float] | None = None


class Actor(Schema):
    kind: Literal["system", "user"]
    id: str = "system"


class Timestamped(Schema):
    at: datetime
