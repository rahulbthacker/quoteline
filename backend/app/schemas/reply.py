from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.common import LineId, Schema, SourceRef, VendorId

Channel = Literal["email"]
FileFormat = Literal["xlsx", "pdf", "docx", "image", "eml"]
DocumentKind = Literal[
    "quote", "questionnaire_response", "certificate", "msds", "spec_sheet", "other"
]
UnitCode = Literal[
    "per_piece", "per_100", "per_1000", "per_kg", "per_box", "per_bundle", "per_set", "unknown"
]
ConditionKind = Literal[
    "discount", "freight", "same_as_last_year", "unit_basis", "validity", "payment", "other"
]


class ReplyFile(Schema):
    path: str
    format: FileFormat
    kind: DocumentKind = "other"
    pages: int | None = None
    sha256: str
    parent: str | None = Field(default=None, description="Set for files carried inside an email")


class QuestionnaireAnswer(Schema):
    question_id: str
    answer_text: str | None = None
    source_ref: SourceRef | None = None


class VendorReply(Schema):
    vendor_id: VendorId
    channel: Channel = "email"
    received_at: datetime
    files: list[ReplyFile]
    format_detected: FileFormat | None = None
    lines_quoted_count: int | None = None
    freight_statement: str | None = None
    currency_detected: str | None = None
    questionnaire_answers: list[QuestionnaireAnswer] = Field(default_factory=list)
    attachments: list[ReplyFile] = Field(default_factory=list)


class Condition(Schema):
    """A conditional or vendor-wide statement. The extractor never turns it into a number."""

    kind: ConditionKind
    text: str = Field(description="Verbatim")
    applies_to: str | None = Field(default=None, description="Scope as the vendor words it")
    percent: float | None = Field(default=None, description="Only if the text states a percentage")
    amount: float | None = Field(default=None, description="Only if the text states an amount")
    source_ref: SourceRef
    model: str
    prompt_version: str


class ReadSpec(Schema):
    """What the model read about the item, used only to match the row to an RFx line."""

    ply: int | None = None
    gsm: int | None = None
    dims_mm: list[int] = Field(default_factory=list)
    print_colours: int | None = None


class LineMatch(Schema):
    line_id: LineId | None
    score: float
    method: Literal["spec", "spec+reference", "model_tiebreak", "scope", "unmatched"]
    reason: str
    runner_up: LineId | None = None


class Extraction(Schema):
    """One per vendor row per model. Raw as read: no unit or currency conversion."""

    vendor_id: VendorId
    line_id: LineId | None = None  # null until matched
    raw_description: str | None = None
    raw_value: float | None = None
    raw_unit: str | None = None  # verbatim
    unit_code: UnitCode = "unknown"
    raw_currency: str | None = None
    not_quoted: bool = False  # the vendor explicitly declines this item
    scope: Literal["item", "category"] = "item"
    scope_text: str | None = None  # e.g. "the 5-ply" for a rate that covers a family of lines
    pack_note: str | None = None  # verbatim packing statement near the price, if any
    alternatives: list[float] = Field(default_factory=list)  # other readings of unclear digits
    spec: ReadSpec = Field(default_factory=ReadSpec)
    rfx_reference: str | None = None  # buyer's line number if the document shows one
    source_ref: SourceRef
    confidence: float = Field(ge=0, le=1)
    model: str
    prompt_version: str
    notes: str | None = None
    match: LineMatch | None = None
