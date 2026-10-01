"""Normalisation: raw reading -> INR per 1,000 pcs. Pure Python, no model.

raw_value x unit factor x pack factor x FX -> inr_per_base, with every step recorded.
Factors come from config/conversion_table.yaml, the RFx line (board weight) and the RFx FX
policy. Ambiguous units return one candidate per interpretation and no single answer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.schemas import Extraction, LineItem, NormalizationStep, RFx
from app.services.units import conversion_table


@dataclass
class Candidate:
    """One way of reading the unit, fully computed."""

    interpretation: str
    label: str
    inr_per_base: float
    steps: list[NormalizationStep] = field(default_factory=list)


@dataclass
class Normalised:
    candidates: list[Candidate]
    ambiguous: bool
    problem: str | None = None  # why nothing could be computed

    @property
    def value(self) -> float | None:
        return self.candidates[0].inr_per_base if len(self.candidates) == 1 else None


def pack_size(note: str | None) -> int | None:
    """Pack size stated next to the price: 'packed 100 per bundle' -> 100."""
    if not note:
        return None
    match = re.search(
        r"(\d[\d,]*)\s*(?:per|/|in a|to a)\s*(?:bundle|pack|box|carton)", note.lower()
    )
    if not match:
        match = re.search(r"(?:bundle|pack)s? of\s*(\d[\d,]*)", note.lower())
    return int(match.group(1).replace(",", "")) if match else None


def _fx_steps(
    value: float, currency: str | None, rfx: RFx
) -> tuple[float, list[NormalizationStep]] | None:
    if currency in (None, rfx.currency):
        return value, []
    policy = rfx.fx_policy
    if currency != policy.foreign_currency:
        return None
    out = round(value * policy.rate, 2)
    step = NormalizationStep(
        op="fx", factor=policy.rate, value_in=value, value_out=out,
        source=f"{policy.source}, {currency} 1 = ₹{policy.rate} as of {policy.as_of.isoformat()}",
    )  # fmt: skip
    return out, [step]


def _apply(
    op: dict, value: float, row: Extraction, line: LineItem
) -> tuple[float, list[NormalizationStep]] | str:
    """Apply one to_base rule from the conversion table."""
    code = row.unit_code
    if op["op"] == "multiply":
        out = round(value * op["factor"], 4)
        return out, [
            NormalizationStep(
                op="unit_factor", factor=op["factor"], value_in=value, value_out=out,
                source=f"conversion_table.units.{code}",
            )
        ]  # fmt: skip
    if op["op"] == "weight":
        weight = line.spec.board_weight_kg_per_pc
        if not weight:
            return (
                f"{line.line_id} has no board weight in the RFx; a per-kg price cannot be converted"
            )
        per_pc = round(value * weight, 6)
        out = round(per_pc * op["factor"], 4)
        return out, [
            NormalizationStep(
                op="weight_factor", factor=weight, value_in=value, value_out=per_pc,
                source=f"RFx {line.line_id} spec.board_weight_kg_per_pc",
            ),
            NormalizationStep(
                op="unit_factor", factor=op["factor"], value_in=per_pc, value_out=out,
                source=f"conversion_table.units.{code}",
            ),
        ]  # fmt: skip
    if op["op"] == "pack":
        stated = row.pack_note or row.source_ref.snippet
        size = pack_size(stated)
        if not size:
            return "no pack size is stated, so a per-pack price cannot be converted"
        per_pc = round(value / size, 6)
        out = round(per_pc * op["factor"], 4)
        return out, [
            NormalizationStep(
                op="pack_factor", factor=1 / size, value_in=value, value_out=per_pc,
                source=f"pack of {size} stated by the vendor: '{stated}'",
            ),
            NormalizationStep(
                op="unit_factor", factor=op["factor"], value_in=per_pc, value_out=out,
                source=f"conversion_table.units.{code}",
            ),
        ]  # fmt: skip
    return f"unknown conversion rule {op['op']}"


def normalise(row: Extraction, line: LineItem, rfx: RFx) -> Normalised:
    """Every defensible reading of one row, in INR per 1,000 of the line's unit."""
    if row.raw_value is None:
        return Normalised([], False, "no price was read")
    unit = conversion_table()["units"].get(row.unit_code)
    if unit is None:
        return Normalised([], True, f"unit '{row.raw_unit}' is not in the conversion table")

    ambiguous = bool(unit.get("ambiguous"))
    # A price "per set" is unambiguous when the RFx itself counts the line in sets.
    if row.unit_code == "per_set" and line.uom.lower().startswith("set"):
        ambiguous = False
    rules = unit["interpretations"] if unit.get("ambiguous") else [
        {"id": row.unit_code, "label": unit["label"], "to_base": unit["to_base"]}
    ]  # fmt: skip

    candidates: list[Candidate] = []
    problems: list[str] = []
    for rule in rules:
        applied = _apply(rule["to_base"], row.raw_value, row, line)
        if isinstance(applied, str):
            problems.append(applied)
            continue
        value, steps = applied
        converted = _fx_steps(value, row.raw_currency, rfx)
        if converted is None:
            problems.append(f"no FX policy for {row.raw_currency}")
            continue
        final, fx_steps = converted
        candidates.append(Candidate(rule["id"], rule["label"], round(final, 2), steps + fx_steps))
    if not candidates:
        return Normalised([], ambiguous, "; ".join(problems))
    if not ambiguous:
        candidates = candidates[:1]
    return Normalised(candidates, ambiguous and len(rules) > 0, None)


_AMOUNT = re.compile(
    r"(?:₹|rs\.?|inr)?\s*(\d[\d,]*(?:\.\d+)?)\s*(lakhs?|lacs?|l\b|crores?|cr\b|k\b)?", re.I
)
_SCALE = {
    "l": 1e5,
    "lakh": 1e5,
    "lakhs": 1e5,
    "lac": 1e5,
    "lacs": 1e5,
    "cr": 1e7,
    "crore": 1e7,
    "crores": 1e7,
    "k": 1e3,
}


def parse_inr_amount(text: str | None) -> float | None:
    """'above ₹1 L' -> 100000.0. The first money-like amount in the text, or None."""
    if not text:
        return None
    for match in _AMOUNT.finditer(text):
        number, scale = match.group(1), (match.group(2) or "").lower()
        has_symbol = bool(re.match(r"\s*(₹|rs\.?|inr)", match.group(0), re.I))
        if not (scale or has_symbol):
            continue  # a bare number such as the '4' in '4%' is not an amount
        return float(number.replace(",", "")) * _SCALE.get(scale, 1)
    return None
