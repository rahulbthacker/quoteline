"""Validation: turn two models' readings into per-line verdicts and flags. Deterministic.

Inputs are the matched extractions from the primary and the secondary extractor and the
conditions each reported. Output is one `LineReading` per RFx line (what was read, by whom,
whether they agree, what it normalises to) and a list of `Flag`s. Flags are what become
review items; a flagged cell stays out of every total until a person resolves it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.schemas import Condition, Extraction, LineItem, RFx
from app.services import units
from app.services.normalization import Normalised, normalise, parse_inr_amount

# Flag kinds that put the affected cells into needs_review.
CELL_BLOCKING = {
    "unit_ambiguity", "ocr_disagreement", "footnote_condition", "model_error",
    "carry_forward_unresolved", "unmatched", "outlier",
}  # fmt: skip


@dataclass
class Flag:
    kind: str
    lines: list[str]
    reason: str
    evidence: str | None = None
    detail: dict = field(default_factory=dict)


@dataclass
class LineReading:
    line_id: str
    primary: Extraction | None
    secondary: Extraction | None
    lead: Extraction | None  # the reading shown when both agree
    agreement: float | None  # 1.0 agree, 0.0 disagree, None if only one model read the file
    normalised: Normalised | None
    how: str  # explicit | per_kg | carry_forward | carry_forward_unresolved | not_quoted
    carry_forward_inr: float | None = None


def _priced(row: Extraction | None) -> bool:
    return row is not None and row.raw_value is not None and not row.not_quoted


def readings_agree(a: Extraction, b: Extraction) -> bool:
    """Same number (within tolerance), same unit, same currency."""
    if a.not_quoted or b.not_quoted:
        return a.not_quoted == b.not_quoted
    if a.raw_value is None or b.raw_value is None:
        return a.raw_value == b.raw_value
    tolerance = units.threshold("agreement_tolerance_pct") / 100
    largest = max(abs(a.raw_value), abs(b.raw_value))
    close = largest == 0 or abs(a.raw_value - b.raw_value) / largest <= tolerance
    return close and a.unit_code == b.unit_code and a.raw_currency == b.raw_currency


def _by_line(rows: list[Extraction]) -> dict[str, Extraction]:
    out: dict[str, Extraction] = {}
    for row in rows:
        if row.line_id and row.line_id not in out:
            out[row.line_id] = row
    return out


def _carry_forward_scope(conditions: list[Condition]) -> Condition | None:
    return next((c for c in conditions if c.kind == "same_as_last_year"), None)


def _freight_flag(conditions: list[Condition]) -> Flag | None:
    """Freight must be either included or priced. Anything else is an open cost."""
    statements = [c for c in conditions if c.kind == "freight"]
    if not statements:
        return Flag("missing_freight", [], "the vendor says nothing about freight")
    text = " ".join(c.text for c in statements).lower()
    if re.search(r"\b(not included|excluded|extra|buyer'?s account|to your account)\b", text):
        stated = next((c for c in statements if parse_inr_amount(c.text)), None)
        if stated:
            return None  # extra, but priced
        return Flag(
            "missing_freight", [], "freight is extra and no amount is stated",
            evidence=statements[0].text,
        )  # fmt: skip
    if re.search(r"\b(included|inclusive|delivered|free delivery|door delivery)\b", text):
        return None
    if any(parse_inr_amount(c.text) for c in statements):
        return None
    return Flag(
        "missing_freight",
        [],
        "freight terms are stated without a price",
        evidence=statements[0].text,
    )


def assess_vendor(
    rfx: RFx,
    primary: list[Extraction] | None,
    secondary: list[Extraction] | None,
    primary_conditions: list[Condition],
    secondary_conditions: list[Condition],
    *,
    lead_role: str = "primary",
    errors: dict[str, str] | None = None,
) -> tuple[dict[str, LineReading], list[Flag]]:
    """`primary`/`secondary` are None when that model's read failed outright."""
    errors = errors or {}
    flags: list[Flag] = []
    all_lines = [line.line_id for line in rfx.line_items]
    lines: dict[str, LineItem] = {line.line_id: line for line in rfx.line_items}
    p_rows, s_rows = _by_line(primary or []), _by_line(secondary or [])
    conditions = primary_conditions or secondary_conditions
    carry = _carry_forward_scope(primary_conditions) or _carry_forward_scope(secondary_conditions)

    if primary is None or secondary is None:
        failed = [
            role for role, rows in (("primary", primary), ("secondary", secondary)) if rows is None
        ]
        detail = "; ".join(f"{role}: {errors.get(role, 'failed')}" for role in failed)
        flags.append(
            Flag("model_error", all_lines, f"extraction did not complete ({detail}); nothing from "
                 "this reply is trusted until it is re-read", detail={"failed_roles": failed})
        )  # fmt: skip

    readings: dict[str, LineReading] = {}
    disagreements: list[tuple[str, str]] = []
    low_confidence: list[tuple[str, str]] = []
    ambiguous_units: list[str] = []
    unknown_units: list[str] = []
    foreign: list[str] = []
    not_quoted: list[str] = []
    unresolved_carry: list[str] = []
    unverified: list[str] = []

    for line_id in all_lines:
        line = lines[line_id]
        p, s = p_rows.get(line_id), s_rows.get(line_id)
        lead = (s if lead_role == "secondary" else p) or p or s
        explicit_decline = bool(lead and lead.not_quoted)

        if lead is None or explicit_decline or not _priced(lead):
            if carry and not explicit_decline and lead is None:
                last_year = line.last_year_price_inr
                how = "carry_forward" if last_year is not None else "carry_forward_unresolved"
                if last_year is None:
                    unresolved_carry.append(line_id)
                readings[line_id] = LineReading(line_id, p, s, None, None, None, how, last_year)
            else:
                not_quoted.append(line_id)
                readings[line_id] = LineReading(line_id, p, s, lead, None, None, "not_quoted")
            if _priced(p) or _priced(s):
                disagreements.append((line_id, "one model read a price where the other did not"))
            continue

        agreement = None
        if p is not None and s is not None:
            agreement = 1.0 if readings_agree(p, s) else 0.0
            if agreement == 0.0:
                disagreements.append((line_id, _describe_disagreement(p, s)))
        elif primary is not None and secondary is not None:
            agreement = 0.0
            who = "primary" if p else "secondary"
            disagreements.append((line_id, f"only the {who} model found a price for this line"))

        alternatives = sorted({a for row in (p, s) if row for a in row.alternatives})
        # Self-reported confidence is a weak signal next to two models agreeing, so it only
        # flags when both readers are unsure or one is very unsure.
        floor, hard_floor = (
            units.threshold("min_confidence"),
            units.threshold("hard_min_confidence"),
        )
        scores = [row.confidence for row in (p, s) if row]
        unsure = max(scores) < floor or min(scores) < hard_floor
        if agreement != 0.0 and (alternatives or unsure):
            others = ", ".join(_num(a) for a in alternatives)
            why = (
                f"a character is unclear; it could also read {others}"
                if alternatives
                else f"the readers are not confident ({', '.join(f'{c:.2f}' for c in scores)})"
            )
            low_confidence.append((line_id, why))
        if lead.source_ref.snippet_verified is False:
            unverified.append(line_id)

        result = normalise(lead, line, rfx)
        if result.ambiguous:
            ambiguous_units.append(line_id)
        elif result.problem:
            unknown_units.append(line_id)
        if lead.raw_currency and lead.raw_currency != rfx.currency:
            foreign.append(line_id)
        how = "per_kg" if lead.unit_code == "per_kg" else "explicit"
        readings[line_id] = LineReading(line_id, p, s, lead, agreement, result, how)

    if disagreements:
        for line_id, why in disagreements:
            flags.append(Flag("ocr_disagreement", [line_id], f"the two models disagree: {why}"))
    for line_id, why in low_confidence:
        flags.append(
            Flag("ocr_disagreement", [line_id], f"both models agree on the number, but {why}")
        )
    for line_id in unverified:
        lead = readings[line_id].lead
        flags.append(
            Flag("ocr_disagreement", [line_id],
                 f"the value could not be found at the cited source ({lead.source_ref.locator})",
                 evidence=lead.source_ref.snippet)
        )  # fmt: skip
    for line_id in ambiguous_units:
        lead = readings[line_id].lead
        spec = units.conversion_table()["units"][lead.unit_code]
        flags.append(
            Flag("unit_ambiguity", [line_id], f"quoted '{lead.raw_unit}': {spec['reason']}",
                 evidence=lead.source_ref.snippet)
        )  # fmt: skip
    for line_id in unknown_units:
        flags.append(
            Flag("unit_ambiguity", [line_id], readings[line_id].normalised.problem,
                 evidence=readings[line_id].lead.source_ref.snippet)
        )  # fmt: skip
    if foreign:
        currency = readings[foreign[0]].lead.raw_currency
        flags.append(
            Flag("currency_mismatch", foreign,
                 f"quoted in {currency}; converted to {rfx.currency} at the RFx FX policy rate "
                 f"({rfx.fx_policy.source}, {rfx.fx_policy.rate})", detail={"currency": currency})
        )  # fmt: skip
    if not_quoted:
        flags.append(Flag("not_quoted", not_quoted, _not_quoted_reason(readings, not_quoted)))
    if unresolved_carry:
        flags.append(
            Flag("carry_forward_unresolved", unresolved_carry,
                 f"'{carry.text}' but these lines have no price from last year to carry forward",
                 evidence=carry.text)
        )  # fmt: skip

    unmatched = [
        row for rows in (primary or [], secondary or []) for row in rows if row.line_id is None
    ]
    for description in sorted({row.raw_description or "?" for row in unmatched}):
        flags.append(Flag("unmatched", [], f"'{description}' could not be matched to an RFx line"))

    for condition in _unique_discounts(primary_conditions, secondary_conditions):
        flags.append(_discount_flag(condition, readings, lines))

    freight = _freight_flag(conditions)
    if freight:
        flags.append(freight)
    return readings, flags


def _num(value: float | None) -> str:
    if value is None:
        return "no legible value"
    return f"{value:,.2f}".rstrip("0").rstrip(".")


def _describe_disagreement(p: Extraction, s: Extraction) -> str:
    if p.raw_value != s.raw_value:
        return f"{p.model} read {_num(p.raw_value)}, {s.model} read {_num(s.raw_value)}"
    if p.unit_code != s.unit_code:
        return f"unit read as '{p.raw_unit}' by {p.model} and '{s.raw_unit}' by {s.model}"
    return f"currency read as {p.raw_currency} by {p.model} and {s.raw_currency} by {s.model}"


def _not_quoted_reason(readings: dict[str, LineReading], lines: list[str]) -> str:
    declined = [
        lid for lid in lines if readings[lid].lead is not None and readings[lid].lead.not_quoted
    ]
    if declined and len(declined) == len(lines):
        return "the vendor declines to quote: " + readings[declined[0]].lead.source_ref.snippet
    return "no price found for these lines; silence is treated as not quoted, never as zero"


def _unique_discounts(primary: list[Condition], secondary: list[Condition]) -> list[Condition]:
    """The same footnote reported by both models is one condition."""
    by_percent: dict[float | None, Condition] = {}
    for condition in primary + secondary:
        if condition.kind == "discount":
            by_percent.setdefault(condition.percent, condition)
    return list(by_percent.values())


def _discount_flag(
    condition: Condition, readings: dict[str, LineReading], lines: dict[str, LineItem]
) -> Flag:
    """A stated discount that is not in the quoted rates. Work out which lines it could touch."""
    threshold = parse_inr_amount(condition.applies_to) or parse_inr_amount(condition.text)
    priced = {
        line_id: reading.normalised.value
        for line_id, reading in readings.items()
        if reading.normalised is not None and reading.normalised.value is not None
    }
    detail: dict = {
        "percent": condition.percent,
        "threshold_inr": threshold,
        "text": condition.text,
    }
    if threshold is None:
        return Flag(
            "footnote_condition", sorted(priced),
            f"a discount is stated but not applied in the quoted rates, and its scope is unclear: "
            f"'{condition.text}'", evidence=condition.text, detail=detail,
        )  # fmt: skip
    by_rate = sorted(lid for lid, value in priced.items() if value > threshold)
    by_value = sorted(
        lid for lid, value in priced.items() if value * lines[lid].qty / 1000 > threshold
    )
    detail |= {"lines_by_rate": by_rate, "lines_by_line_value": by_value}
    return Flag(
        "footnote_condition", by_rate,
        f"'{condition.text}' is not applied in the quoted rates. Read as rate above "
        f"₹{threshold:,.0f} per 1,000 it covers {len(by_rate)} line(s); read as line value above "
        f"₹{threshold:,.0f} it covers {len(by_value)}.", evidence=condition.text, detail=detail,
    )  # fmt: skip
