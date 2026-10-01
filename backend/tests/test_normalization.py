"""Normalisation is arithmetic, so it is tested exactly, against the golden set's truth."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.schemas import Extraction, RFx, SourceRef
from app.services.normalization import normalise, pack_size, parse_inr_amount

DATA = Path(__file__).resolve().parents[2] / "data"
UNIT = {
    "per_pc": "per_piece",
    "per_100": "per_100",
    "per_1000": "per_1000",
    "per_kg": "per_kg",
    "per_box": "per_box",
}


@pytest.fixture(scope="module")
def rfx() -> RFx:
    return RFx.model_validate_json((DATA / "rfx" / "RFX-0147.json").read_text(encoding="utf-8"))


def reading(value, unit_code, currency="INR", pack_note=None, snippet="s") -> Extraction:
    return Extraction(
        vendor_id="v", raw_value=value, unit_code=unit_code, raw_currency=currency,
        pack_note=pack_note, source_ref=SourceRef(file="f", locator="l", snippet=snippet),
        confidence=1.0, model="none", prompt_version="none",
    )  # fmt: skip


@pytest.mark.parametrize("vendor", ["meridian", "sribalaji", "kaveri", "northbox", "anand"])
def test_every_golden_reading_normalises_to_the_golden_value(vendor: str, rfx: RFx):
    golden = json.loads((DATA / "golden" / f"{vendor}.json").read_text(encoding="utf-8"))
    lines = {line.line_id: line for line in rfx.line_items}
    checked = 0
    for item in golden["lines"]:
        if item["raw_value"] is None:
            continue
        note = "packed 100 per bundle" if item["raw_unit"] == "per_box" else None
        row = reading(item["raw_value"], UNIT[item["raw_unit"]], item["raw_currency"], note)
        result = normalise(row, lines[item["line_id"]], rfx)
        if item["raw_unit"] == "per_box":
            assert result.ambiguous and result.value is None
            by_id = {c.interpretation: c.inr_per_base for c in result.candidates}
            assert by_id["per_piece"] == pytest.approx(item["normalised_inr_per_1000"], abs=0.01)
            assert by_id["per_pack"] == pytest.approx(
                item["normalised_inr_per_1000"] / 100, abs=0.01
            )
        else:
            assert not result.ambiguous
            assert result.value == pytest.approx(item["normalised_inr_per_1000"], abs=0.01)
        checked += 1
    assert checked >= 22


def test_trace_records_every_factor_and_its_source(rfx: RFx):
    line = next(item for item in rfx.line_items if item.line_id == "L01")
    per_kg = normalise(reading(42.0, "per_kg"), line, rfx)
    assert [s.op for s in per_kg.candidates[0].steps] == ["weight_factor", "unit_factor"]
    assert per_kg.candidates[0].steps[0].factor == line.spec.board_weight_kg_per_pc
    assert "board_weight_kg_per_pc" in per_kg.candidates[0].steps[0].source

    usd = normalise(reading(668.4, "per_1000", "USD"), line, rfx)
    fx = usd.candidates[0].steps[-1]
    assert fx.op == "fx" and fx.factor == 83.42 and "RBI" in fx.source
    assert usd.value == pytest.approx(668.4 * 83.42, abs=0.01)


def test_per_set_is_only_unambiguous_on_a_line_counted_in_sets(rfx: RFx):
    sets_line = next(item for item in rfx.line_items if item.uom == "sets")
    box_line = next(item for item in rfx.line_items if item.line_id == "L01")
    assert not normalise(reading(8.2, "per_set"), sets_line, rfx).ambiguous
    assert normalise(reading(8.2, "per_set"), box_line, rfx).ambiguous


def test_unconvertible_readings_say_why(rfx: RFx):
    line = next(item for item in rfx.line_items if item.line_id == "L01")
    assert "conversion table" in normalise(reading(5.0, "unknown"), line, rfx).problem
    assert "FX policy" in normalise(reading(5.0, "per_piece", "EUR"), line, rfx).problem
    assert normalise(reading(None, "per_piece"), line, rfx).problem == "no price was read"


def test_pack_size_and_amount_parsing():
    assert pack_size("packed 100 per bundle") == 100
    assert pack_size("in bundles of 25") == 25
    assert pack_size("FOB Chennai") is None
    assert parse_inr_amount("lines above ₹1 L") == 100_000
    assert parse_inr_amount("orders over Rs. 2,50,000") == 250_000
    assert parse_inr_amount("above 1.5 lakh") == 150_000
    assert parse_inr_amount("4% discount") is None
