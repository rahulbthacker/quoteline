"""Validation rules, tested with readings built from the golden set (no model involved).

If two exact readers report what each file says, validation must raise exactly the flags the
dataset was built to provoke, and nothing else. Then each rule is tested on its own.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.eval import golden
from app.schemas import Condition, Extraction, LineMatch, RFx, SourceRef
from app.services.validation import CELL_BLOCKING, assess_vendor

DATA = Path(__file__).resolve().parents[2] / "data"


@pytest.fixture(scope="module")
def rfx() -> RFx:
    return RFx.model_validate_json((DATA / "rfx" / "RFX-0147.json").read_text(encoding="utf-8"))


def reading(line_id, value, unit_code, currency="INR", *, model="m", confidence=0.95, **extra):
    return Extraction(
        vendor_id="v", line_id=line_id, raw_value=value, raw_unit=unit_code.replace("_", " "),
        unit_code=unit_code, raw_currency=currency, confidence=confidence, model=model,
        prompt_version="t", source_ref=SourceRef(file="f", locator="l", snippet="s"),
        match=LineMatch(line_id=line_id, score=1.0, method="spec", reason="t"), **extra,
    )  # fmt: skip


def condition(kind, text, **extra) -> Condition:
    return Condition(
        kind=kind, text=text, model="m", prompt_version="t",
        source_ref=SourceRef(file="f", locator="l", snippet=text), **extra,
    )  # fmt: skip


def exact_reader(vendor: str) -> tuple[list[Extraction], list[Condition]]:
    """What a perfect extractor would report for this vendor's file."""
    truth = golden.load(vendor)
    rows = []
    for item in truth["lines"]:
        if item["raw_value"] is not None:
            extra = {"pack_note": "packed 100 per bundle"} if item["raw_unit"] == "per_box" else {}
            rows.append(
                reading(item["line_id"], item["raw_value"], golden.UNIT_CODE[item["raw_unit"]],
                        item["raw_currency"], **extra)
            )  # fmt: skip
        elif vendor == "kaveri" and not item["quoted"]:
            rows.append(reading(item["line_id"], None, "unknown", "USD", not_quoted=True))
    conditions = [condition("freight", truth["freight"]["statement"])]
    if vendor == "sribalaji":
        conditions.append(
            condition(
                "discount", truth["discount"]["text"], percent=4.0, applies_to="lines above ₹1 L"
            )
        )
    if vendor == "anand":
        conditions.append(
            condition("same_as_last_year", "rest same as last year", applies_to="rest")
        )
    return rows, conditions


@pytest.mark.parametrize("vendor", golden.VENDORS)
def test_exact_readings_raise_exactly_the_expected_flags(vendor: str, rfx: RFx):
    truth = golden.load(vendor)
    rows, conditions = exact_reader(vendor)
    if (
        vendor == "northbox"
    ):  # the blot: a truthful reader reports the alternative it cannot rule out
        for row in rows:
            if row.line_id == "L05":
                row.alternatives, row.confidence = [3985.0], 0.5
    readings, flags = assess_vendor(
        rfx, rows, [r.model_copy() for r in rows], conditions, conditions
    )
    raised: dict[str, set[str]] = {}
    for flag in flags:
        raised.setdefault(flag.kind, set()).update(flag.lines)
    expected = {item["kind"]: set(item["lines"]) for item in truth["expected_review_items"]}
    assert raised == expected

    blocked = {line for flag in flags if flag.kind in CELL_BLOCKING for line in flag.lines}
    for item in truth["lines"]:
        got = readings[item["line_id"]]
        if item["expected_state"] == "not_quoted":
            assert got.how == "not_quoted"
        else:
            assert (item["line_id"] in blocked) == (item["expected_state"] == "needs_review")
        if got.normalised is not None and got.normalised.value is not None:
            assert got.normalised.value == pytest.approx(item["normalised_inr_per_1000"], abs=0.01)
        if got.how == "carry_forward":
            assert got.carry_forward_inr == item["normalised_inr_per_1000"]


def flags_for(rfx, primary, secondary, conditions=None):
    conditions = conditions or [condition("freight", "freight included")]
    _, flags = assess_vendor(rfx, primary, secondary, conditions, conditions)
    return {(flag.kind, tuple(flag.lines)) for flag in flags if flag.kind != "not_quoted"}


def test_disagreement_beyond_tolerance_is_flagged_and_within_is_not(rfx: RFx):
    a = [reading("L01", 54910.0, "per_1000")]
    assert flags_for(rfx, a, [reading("L01", 54990.0, "per_1000")]) == set()  # 0.15%
    assert flags_for(rfx, a, [reading("L01", 55410.0, "per_1000")]) == {
        ("ocr_disagreement", ("L01",))
    }
    assert flags_for(rfx, a, [reading("L01", 54910.0, "per_100")]) == {
        ("ocr_disagreement", ("L01",))
    }
    assert flags_for(rfx, a, []) == {("ocr_disagreement", ("L01",))}  # one model missed the row


def test_confidence_only_flags_when_both_unsure_or_one_very_unsure(rfx: RFx):
    def pair(c1, c2):
        return flags_for(
            rfx,
            [reading("L01", 54910.0, "per_1000", confidence=c1)],
            [reading("L01", 54910.0, "per_1000", confidence=c2)],
        )

    assert pair(0.75, 0.95) == set()  # agreement outweighs one reader's hedging
    assert pair(0.75, 0.70) == {("ocr_disagreement", ("L01",))}
    assert pair(0.95, 0.40) == {("ocr_disagreement", ("L01",))}


def test_value_not_found_at_its_cited_source_is_flagged(rfx: RFx):
    row = reading("L01", 54910.0, "per_1000")
    row.source_ref.snippet_verified = False
    assert flags_for(rfx, [row], [reading("L01", 54910.0, "per_1000")]) == {
        ("ocr_disagreement", ("L01",))
    }


def test_failed_model_flags_every_line(rfx: RFx):
    _, flags = assess_vendor(
        rfx, [reading("L01", 54910.0, "per_1000")], None, [], [], errors={"secondary": "HTTP 503"}
    )
    error = next(flag for flag in flags if flag.kind == "model_error")
    assert len(error.lines) == 30 and "HTTP 503" in error.reason


def test_freight_rules(rfx: RFx):
    def freight(text):
        return ("missing_freight", ()) in flags_for(rfx, [], [], [condition("freight", text)])

    assert freight("freight extra")
    assert freight("FOB Chennai; onward freight to Pune is to the buyer's account.")
    assert not freight("Rates are delivered to your Chakan plant; freight is included.")
    assert not freight(
        "Freight extra at ₹5,20,000 lump sum for the contract period, delivered Chakan."
    )
    _, flags = assess_vendor(rfx, [], [], [], [])
    assert any(flag.kind == "missing_freight" for flag in flags)  # silence is also missing


def test_discount_scope_is_computed_both_ways(rfx: RFx):
    truth = json.loads((DATA / "golden" / "sribalaji.json").read_text(encoding="utf-8"))
    rows, conditions = exact_reader("sribalaji")
    _, flags = assess_vendor(rfx, rows, rows, conditions, conditions)
    flag = next(flag for flag in flags if flag.kind == "footnote_condition")
    assert flag.detail["lines_by_rate"] == truth["discount"]["qualifying_lines_by_rate"]
    assert flag.detail["lines_by_line_value"] == truth["discount"]["qualifying_lines_by_line_value"]
    assert flag.detail["percent"] == 4.0 and flag.detail["threshold_inr"] == 100_000
