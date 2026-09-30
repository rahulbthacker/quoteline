from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ValidationError

from app.llm.contracts import LLMRequest, ProviderError, ProviderResult


class ProviderClient(Protocol):
    name: str

    def complete(self, model: str, req: LLMRequest) -> ProviderResult: ...


def validate_output(req: LLMRequest, text: str, parsed: BaseModel | None) -> BaseModel | None:
    """Every agent returns Pydantic-validated output; a schema miss is a failed (retryable) call."""
    if req.output_schema is None:
        return None
    if isinstance(parsed, req.output_schema):
        return parsed
    try:
        return req.output_schema.model_validate_json(text)
    except ValidationError as exc:
        raise ProviderError(f"output failed schema validation: {exc}", retryable=True) from exc
