from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import ConfigDict

from app.schemas.common import Schema


class Trace(Schema):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    call_id: str
    parent_run_id: str | None
    rfx_id: str | None
    role: str
    provider: str
    model: str
    served_model: str | None
    prompt_version: str
    attempt: int
    status: Literal["ok", "error"]
    error: str | None
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: int
    cost_inr: float | None
    agreement: float | None
    provider_request_id: str | None
    created_at: datetime
