"""Deterministic cost of a call in INR from token counts and the price table."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

PRICING_FILE = Path(__file__).with_name("pricing.yaml")
LONG_PROMPT_THRESHOLD = 200_000


@lru_cache
def load_prices() -> dict[str, dict]:
    return yaml.safe_load(PRICING_FILE.read_text())["models"]


def price_entry(model: str) -> dict | None:
    matches = [key for key in load_prices() if model.startswith(key)]
    return load_prices()[max(matches, key=len)] if matches else None


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float | None:
    entry = price_entry(model)
    if entry is None:
        return None
    if input_tokens > LONG_PROMPT_THRESHOLD and "over_200k" in entry:
        entry = entry["over_200k"]
    return (input_tokens * entry["input"] + output_tokens * entry["output"]) / 1_000_000


def cost_inr(model: str, input_tokens: int, output_tokens: int, usd_inr: float) -> float | None:
    usd = cost_usd(model, input_tokens, output_tokens)
    return None if usd is None else round(usd * usd_inr, 4)
