from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.common import LineId, Schema, SourceRef, VendorId

Channel = Literal["email"]
FileFormat = Literal["xlsx", "pdf", "docx", "image", "eml"]


class ReplyFile(Schema):
    path: str
    format: FileFormat
    pages: int | None = None
    sha256: str


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
    """A conditional statement the extractor must not turn into a number."""

    kind: Literal["discount", "freight", "same_as_last_year", "validity", "other"]
    text: str = Field(description="Verbatim")


class Extraction(Schema):
    """One per vendor line per model. Raw as read: no unit or currency conversion."""

    vendor_id: VendorId
    line_id: LineId | None = None  # null until matched
    raw_description: str | None = None
    raw_value: float | None = None
    raw_unit: str | None = None
    raw_currency: str | None = None
    condition: Condition | None = None
    source_ref: SourceRef
    confidence: float = Field(ge=0, le=1)
    model: str
    prompt_version: str
    notes: str | None = None
