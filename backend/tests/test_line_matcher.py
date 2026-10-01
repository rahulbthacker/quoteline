"""The deterministic matcher against every vendor's own wording, taken from the golden set.

No model is involved: rows are built from the golden descriptions the way an exact reader
would report them, and `mode="deterministic"` forbids the tie-break call.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.schemas import Extraction, ReadSpec, RFx, SourceRef
from app.services import line_matcher, units

DATA = Path(__file__).resolve().parents[2] / "data"


@pytest.fixture(scope="module")
def rfx() -> RFx:
    return RFx.model_validate_json((DATA / "rfx" / "RFX-0147.json").read_text(encoding="utf-8"))


def row(description: str, **spec) -> Extraction:
    return Extraction(
        vendor_id="v",
        raw_description=description,
        raw_value=1.0,
        spec=ReadSpec(**spec),
        source_ref=SourceRef(file="f", locator="x", snippet=description),
        confidence=1.0,
        model="none",
        prompt_version="none",
    )


@pytest.mark.parametrize("vendor", ["meridian", "sribalaji", "kaveri", "northbox"])
def test_vendor_wording_matches_the_right_line_without_a_model(vendor: str, rfx: RFx):
    golden = json.loads((DATA / "golden" / f"{vendor}.json").read_text(encoding="utf-8"))
    by_id = {line.line_id: line for line in rfx.line_items}
    rows, expected = [], []
    for item in golden["lines"]:
        if not item["quoted"]:
            continue
        line = by_id[item["line_id"]]
        spec = {}
        if vendor == "kaveri":  # the ply is named in the surrounding sentence
            spec = {"ply": line.spec.ply}
        if vendor == "meridian":  # dimensions sit in their own L / W / H columns
            spec = {"dims_mm": list(line.spec.dims_mm or [])}
        rows.append(row(item["vendor_description"], **spec))
        expected.append(item["line_id"])
    matched = line_matcher.match_rows(rows, rfx, run_id="t", mode="deterministic")
    got = {m.raw_description: m.line_id for m in matched}
    wrong = [
        (r.raw_description, want, got[r.raw_description])
        for r, want in zip(rows, expected, strict=True)
        if got[r.raw_description] != want
    ]
    assert not wrong
    assert all(m.match.method in ("spec", "spec+reference") for m in matched)


def test_a_partition_for_a_box_is_not_the_box(rfx: RFx):
    matched = line_matcher.match_rows(
        [row("Partition Assy 12 Cell 3 Ply 120 GSM (to suit 400x300x300)")],
        rfx, run_id="t", mode="deterministic",
    )  # fmt: skip
    assert matched[0].line_id == "L06"


def test_vendor_serial_numbers_do_not_override_the_specification(rfx: RFx):
    wrong_reference = row("RSC Carton 5 Ply 150 GSM KLB 600 x 400 x 400")
    wrong_reference.rfx_reference = "7"  # the vendor's own serial, not the buyer's line
    matched = line_matcher.match_rows([wrong_reference], rfx, run_id="t", mode="deterministic")
    assert matched[0].line_id == "L01"


def test_unknown_item_is_flagged_not_forced(rfx: RFx):
    matched = line_matcher.match_rows(
        [row("Stretch film 23 micron, 500 mm roll")], rfx, run_id="t", mode="deterministic"
    )
    assert matched[0].line_id is None and matched[0].match.method == "unmatched"


def test_family_rate_expands_to_every_line_of_that_ply(rfx: RFx):
    family = row("the 5-ply")
    family.scope, family.scope_text, family.unit_code = "category", "the 5-ply", "per_kg"
    matched = line_matcher.match_rows([family], rfx, run_id="t", mode="deterministic")
    expected = [line.line_id for line in rfx.line_items if line.spec.ply == 5]
    assert [m.line_id for m in matched] == expected and len(expected) == 12
    assert all(m.match.method == "scope" for m in matched)


def test_units_are_read_by_the_table_not_the_model():
    assert units.resolve_unit("INR per piece (each)", "per_1000") == ("per_piece", "table")
    assert units.resolve_unit("Rate ₹ / 100 pcs", "unknown") == ("per_100", "table")
    assert units.resolve_unit("USD per thousand sets", "per_set") == ("per_1000", "table")
    assert units.resolve_unit("per box", "per_piece") == ("per_box", "table")
    assert units.is_ambiguous("per_box") and not units.is_ambiguous("per_kg")
    assert units.resolve_unit("per pallet layer", "unknown") == ("unknown", "unknown")
