"""Unit and currency recognition against the editable conversion table. Deterministic."""

from __future__ import annotations

import re
from functools import lru_cache

import yaml

from app.config import BACKEND_ROOT

CONVERSION_TABLE = BACKEND_ROOT / "config" / "conversion_table.yaml"


@lru_cache
def conversion_table() -> dict:
    return yaml.safe_load(CONVERSION_TABLE.read_text(encoding="utf-8"))


def threshold(name: str) -> float:
    return float(conversion_table()["thresholds"][name])


def _normalise(text: str) -> str:
    text = text.lower().replace("₹", " ").replace(",", "")
    text = re.sub(r"\b(inr|usd|rs\.?|rupees|dollars?)\b", " ", text)
    text = re.sub(r"\s*/\s*", " per ", text)  # "₹ / 100 pcs" and "/kg" read as "per ..."
    return re.sub(r"\s+", " ", text).strip()


def unit_from_text(raw_unit: str | None) -> str | None:
    """Canonical unit code for a vendor's wording, or None if the table does not know it."""
    if not raw_unit:
        return None
    text = _normalise(raw_unit)
    best: tuple[int, str] | None = None
    for code, spec in conversion_table()["units"].items():
        for alias in spec["aliases"]:
            alias_norm = _normalise(alias)
            if alias_norm and re.search(rf"(?<![a-z0-9]){re.escape(alias_norm)}(?![a-z0-9])", text):
                if best is None or len(alias_norm) > best[0]:
                    best = (len(alias_norm), code)
    return best[1] if best else None


def resolve_unit(raw_unit: str | None, model_code: str) -> tuple[str, str]:
    """Code decides: the table's reading of the vendor's words wins over the model's label.

    Returns (unit_code, how) where how is 'table', 'model' or 'unknown'.
    """
    from_table = unit_from_text(raw_unit)
    if from_table:
        return from_table, "table"
    if model_code and model_code != "unknown" and model_code in conversion_table()["units"]:
        return model_code, "model"
    return "unknown", "unknown"


def is_ambiguous(unit_code: str) -> bool:
    return bool(conversion_table()["units"].get(unit_code, {}).get("ambiguous"))


def currency_code(raw: str | None) -> str | None:
    if not raw:
        return None
    text = raw.strip()
    for code, spec in conversion_table()["currencies"].items():
        if text.upper() == code or any(text.lower() == s.lower() for s in spec["symbols"]):
            return code
    return text.upper()
