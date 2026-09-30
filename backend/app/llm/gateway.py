"""The single entry point for model calls.

Every call in the app goes through `call()`, which
  1. resolves the role's fallback chain from config,
  2. retries a failed call once, then moves to the next model in the chain,
  3. writes one Trace row per attempt (model, prompt version, tokens, latency, cost),
  4. raises ModelCallError when the chain is exhausted, so the caller can flag the item
     needs_review / model_error instead of dropping it.
There is no offline or simulated path: without a key the call fails and is traced as failed.
"""

from __future__ import annotations

import time
import uuid
from functools import lru_cache

from app.config import Provider, Settings, get_settings
from app.db import session_scope
from app.llm import pricing
from app.llm.contracts import (
    FailedAttempt,
    LLMRequest,
    LLMResult,
    ModelCallError,
    ProviderError,
)
from app.llm.providers import build_client
from app.llm.providers.base import ProviderClient
from app.models.trace import TraceRow

MAX_ATTEMPTS_PER_MODEL = 2  # one call plus one retry


@lru_cache
def _cached_client(provider: Provider) -> ProviderClient:
    return build_client(provider, get_settings())


def _write_trace(row: TraceRow) -> None:
    with session_scope() as session:
        session.add(row)


def call(
    req: LLMRequest,
    *,
    run_id: str | None = None,
    rfx_id: str | None = None,
    settings: Settings | None = None,
    clients: dict[Provider, ProviderClient] | None = None,
) -> LLMResult:
    settings = settings or get_settings()
    failures: list[FailedAttempt] = []
    total_attempts = 0

    for spec in settings.chain(req.role):
        for attempt in range(1, MAX_ATTEMPTS_PER_MODEL + 1):
            total_attempts += 1
            call_id = uuid.uuid4().hex
            started = time.perf_counter()
            error: ProviderError | None = None
            result = None
            try:
                client = clients[spec.provider] if clients else _cached_client(spec.provider)
                result = client.complete(spec.model, req)
            except ProviderError as exc:
                error = exc
            latency_ms = int((time.perf_counter() - started) * 1000)

            if result is not None:
                cost = pricing.cost_inr(
                    result.served_model,
                    result.input_tokens,
                    result.output_tokens,
                    settings.cost_usd_inr,
                )
                _write_trace(
                    TraceRow(
                        call_id=call_id,
                        parent_run_id=run_id,
                        rfx_id=rfx_id,
                        role=req.role,
                        provider=spec.provider,
                        model=spec.model,
                        served_model=result.served_model,
                        prompt_version=req.prompt_version,
                        attempt=attempt,
                        status="ok",
                        input_tokens=result.input_tokens,
                        output_tokens=result.output_tokens,
                        latency_ms=latency_ms,
                        cost_inr=cost,
                        provider_request_id=result.request_id,
                    )
                )
                return LLMResult(
                    call_id=call_id,
                    provider=spec.provider,
                    model=spec.model,
                    served_model=result.served_model,
                    text=result.text,
                    parsed=result.parsed,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    latency_ms=latency_ms,
                    cost_inr=cost,
                    attempts=total_attempts,
                )

            assert error is not None
            _write_trace(
                TraceRow(
                    call_id=call_id,
                    parent_run_id=run_id,
                    rfx_id=rfx_id,
                    role=req.role,
                    provider=spec.provider,
                    model=spec.model,
                    prompt_version=req.prompt_version,
                    attempt=attempt,
                    status="error",
                    error=str(error)[:2000],
                    latency_ms=latency_ms,
                )
            )
            failures.append(FailedAttempt(spec.provider, spec.model, attempt, str(error)))
            if not error.retryable:
                break  # same request cannot succeed on this model; try the next in the chain

    raise ModelCallError(req.role, failures)
