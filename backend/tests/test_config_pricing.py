from __future__ import annotations

import pytest

from app.config import ModelSpec, Settings, parse_chain
from app.llm import pricing


def test_parse_chain_orders_fallbacks():
    chain = parse_chain("anthropic:claude-opus-5-5, gemini:gemini-3.1-pro-preview")
    assert chain == [
        ModelSpec("anthropic", "claude-opus-5-5"),
        ModelSpec("gemini", "gemini-3.1-pro-preview"),
    ]


@pytest.mark.parametrize("bad", ["", "claude-opus-5-5", "openai:gpt-5.6-sol", "gemini:"])
def test_parse_chain_rejects_bad_specs(bad):
    with pytest.raises(ValueError):
        parse_chain(bad)


def test_default_roles_cover_both_providers():
    settings = Settings(_env_file=None)
    providers = {
        spec.provider
        for role in ("EXTRACT_PRIMARY", "EXTRACT_SECONDARY", "JUDGE", "ROUTER", "ANALYST")
        for spec in settings.chain(role)
    }
    assert providers == {"anthropic", "gemini"}
    # Dual-model agreement only means something if the two extractors are different families.
    assert (
        settings.chain("EXTRACT_PRIMARY")[0].provider
        != settings.chain("EXTRACT_SECONDARY")[0].provider
    )


def test_cost_uses_longest_prefix_and_long_prompt_tier():
    assert pricing.cost_usd("claude-opus-5-5", 1_000_000, 1_000_000) == pytest.approx(24.0)
    # Dated snapshot ids resolve to their family entry.
    assert pricing.cost_usd("gemini-3.1-pro-preview", 1_000_000, 0) == pytest.approx(4.0)
    assert pricing.cost_usd("gemini-3.1-pro-preview", 100_000, 0) == pytest.approx(0.2)
    assert pricing.cost_inr("claude-haiku-4-5-20251001", 1000, 1000, 83.42) == pytest.approx(
        0.006 * 83.42, abs=1e-4
    )


def test_unknown_model_is_unpriced_not_guessed():
    assert pricing.cost_inr("some-new-model", 10, 10, 83.42) is None
