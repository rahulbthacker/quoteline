"""Provider-neutral request/response types for the LLM gateway."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel

from app.config import Role

Effort = Literal["low", "medium", "high", "xhigh", "max"]


@dataclass(frozen=True)
class ImagePart:
    media_type: str  # image/jpeg, image/png
    data: bytes


@dataclass(frozen=True)
class LLMRequest:
    role: Role
    prompt_version: str  # from the prompt file's version header, e.g. "extractor_v3"
    text: str
    system: str | None = None
    images: tuple[ImagePart, ...] = ()
    output_schema: type[BaseModel] | None = None
    max_tokens: int = 16000
    effort: Effort | None = None


@dataclass
class ProviderResult:
    text: str
    parsed: BaseModel | None
    input_tokens: int
    output_tokens: int
    served_model: str
    request_id: str | None = None


@dataclass
class LLMResult:
    call_id: str
    provider: str
    model: str
    served_model: str
    text: str
    parsed: Any
    input_tokens: int
    output_tokens: int
    latency_ms: int
    cost_inr: float | None
    attempts: int = 1


class ProviderError(Exception):
    """A provider call failed. `retryable` says whether the same request may succeed again."""

    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


@dataclass
class FailedAttempt:
    provider: str
    model: str
    attempt: int
    error: str


class ModelCallError(Exception):
    """Every model in the role's chain failed. Callers flag the item needs_review/model_error."""

    def __init__(self, role: str, attempts: list[FailedAttempt]) -> None:
        self.role = role
        self.attempts = attempts
        detail = "; ".join(f"{a.provider}:{a.model}#{a.attempt}: {a.error}" for a in attempts)
        super().__init__(f"All models failed for role {role}: {detail}")
