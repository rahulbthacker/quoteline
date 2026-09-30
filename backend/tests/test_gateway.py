"""Gateway behaviour: retry once, fall through the chain, trace every attempt.

The stub clients here stand in for provider SDKs so the retry and tracing logic can be
tested without spending tokens. They live in tests only; the app has no simulated path.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel
from sqlalchemy import select

from app.config import Settings
from app.db import session_scope
from app.llm import gateway
from app.llm.contracts import LLMRequest, ModelCallError, ProviderError, ProviderResult
from app.llm.providers.base import validate_output
from app.models.trace import TraceRow


class Answer(BaseModel):
    value: int


class ScriptedClient:
    def __init__(self, name: str, outcomes: list):
        self.name = name
        self.outcomes = list(outcomes)
        self.calls = 0

    def complete(self, model: str, req: LLMRequest) -> ProviderResult:
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        text = outcome
        return ProviderResult(
            text=text,
            parsed=validate_output(req, text, None),
            input_tokens=1000,
            output_tokens=500,
            served_model=model,
            request_id=f"req-{self.calls}",
        )


def settings_with(**chains: str) -> Settings:
    return Settings(_env_file=None, **chains)


def request() -> LLMRequest:
    return LLMRequest(
        role="EXTRACT_PRIMARY", prompt_version="test_v1", text="q", output_schema=Answer
    )


def traces() -> list[TraceRow]:
    with session_scope() as session:
        return list(session.scalars(select(TraceRow).order_by(TraceRow.created_at)).all())


def test_success_writes_one_priced_trace():
    client = ScriptedClient("anthropic", ['{"value": 7}'])
    result = gateway.call(
        request(), run_id="run-1", settings=settings_with(), clients={"anthropic": client}
    )
    assert result.parsed == Answer(value=7)
    (row,) = traces()
    assert (row.status, row.role, row.prompt_version) == ("ok", "EXTRACT_PRIMARY", "test_v1")
    assert (row.input_tokens, row.output_tokens, row.parent_run_id) == (1000, 500, "run-1")
    # 1000 in at $4/M + 500 out at $20/M = $0.014
    assert row.cost_inr == pytest.approx(0.014 * 83.42, abs=1e-4)
    assert row.provider_request_id == "req-1"


def test_retryable_failure_is_retried_once_and_both_attempts_are_traced():
    client = ScriptedClient(
        "anthropic", [ProviderError("HTTP 529: overloaded", retryable=True), '{"value": 1}']
    )
    result = gateway.call(request(), settings=settings_with(), clients={"anthropic": client})
    assert result.attempts == 2
    assert [(r.attempt, r.status) for r in traces()] == [(1, "error"), (2, "ok")]


def test_schema_violation_counts_as_a_failed_call():
    client = ScriptedClient("anthropic", ['{"value": "seven"}', '{"value": 7}'])
    result = gateway.call(request(), settings=settings_with(), clients={"anthropic": client})
    assert result.parsed.value == 7
    first = traces()[0]
    assert first.status == "error" and "schema validation" in first.error


def test_non_retryable_failure_skips_to_next_model_in_chain():
    primary = ScriptedClient("anthropic", [ProviderError("HTTP 401: bad key", retryable=False)])
    backup = ScriptedClient("gemini", ['{"value": 3}'])
    result = gateway.call(
        request(),
        settings=settings_with(extract_primary="anthropic:claude-opus-5-5,gemini:gemini-3.1-pro"),
        clients={"anthropic": primary, "gemini": backup},
    )
    assert (result.provider, primary.calls, backup.calls) == ("gemini", 1, 1)
    assert [(r.provider, r.status) for r in traces()] == [("anthropic", "error"), ("gemini", "ok")]


def test_exhausted_chain_raises_and_never_drops_silently():
    client = ScriptedClient(
        "anthropic",
        [ProviderError("timeout", retryable=True), ProviderError("timeout", retryable=True)],
    )
    with pytest.raises(ModelCallError) as excinfo:
        gateway.call(request(), settings=settings_with(), clients={"anthropic": client})
    assert len(excinfo.value.attempts) == 2
    assert client.calls == 2  # one call plus exactly one retry
    assert [r.status for r in traces()] == ["error", "error"]


def test_missing_api_key_fails_loudly_and_is_traced(monkeypatch):
    settings = settings_with(anthropic_api_key="")
    monkeypatch.setattr(gateway, "get_settings", lambda: settings)
    gateway._cached_client.cache_clear()
    try:
        # No injected clients: the real client factory runs and must refuse without a key.
        with pytest.raises(ModelCallError) as excinfo:
            gateway.call(request(), settings=settings)
    finally:
        gateway._cached_client.cache_clear()
    assert "ANTHROPIC_API_KEY is not set" in str(excinfo.value)
    assert traces()[0].status == "error"
