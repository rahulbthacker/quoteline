"""Checkpoint D: 150 cells with correct states; totals exclude flagged and not-quoted lines."""

from __future__ import annotations

import pytest

from app.eval import golden
from app.services import grid, review
from tests.helpers import RFX_ID, seed_exact_reads


@pytest.fixture
def built():
    seed_exact_reads()
    return grid.build(RFX_ID)


def cell(result, vendor, line):
    return next(row for row in result.grid.lines if row.line_id == line).cells[vendor]


def vendor(result, vendor_id):
    return next(v for v in result.grid.vendors if v.vendor_id == vendor_id)


def test_grid_has_150_cells_with_the_golden_states(built):
    cells = [(row.line_id, vid, c) for row in built.grid.lines for vid, c in row.cells.items()]
    assert len(cells) == 150
    for vendor_id in golden.VENDORS:
        for item in golden.load(vendor_id)["lines"]:
            got = cell(built, vendor_id, item["line_id"])
            assert got.state == item["expected_state"], (vendor_id, item["line_id"])
            if got.state == "confident":
                assert got.inr_per_base == pytest.approx(item["normalised_inr_per_1000"], abs=0.01)
                assert got.normalization_trace, "every counted number carries its arithmetic"
            else:
                assert got.inr_per_base is None  # never a number, never zero
    assert built.grid.counts == {
        "confident": 141,
        "needs_review": 5,
        "not_quoted": 4,
        "overridden": 0,
    }


def test_totals_exclude_flagged_and_not_quoted_lines(built):
    qty = {row.line_id: row.qty for row in built.grid.lines}
    for vendor_id in golden.VENDORS:
        expected = sum(
            item["normalised_inr_per_1000"] * qty[item["line_id"]] / 1000
            for item in golden.load(vendor_id)["lines"]
            if item["expected_state"] == "confident"
        )
        totals = vendor(built, vendor_id).totals
        assert totals.extended_inr == pytest.approx(expected, abs=1.0)
        states = [i["expected_state"] for i in golden.load(vendor_id)["lines"]]
        assert totals.lines_counted == states.count("confident")
        assert totals.needs_review == states.count("needs_review")
        assert totals.not_quoted == states.count("not_quoted")
    # Kaveri's L01 is worth about ₹35 lakh and must not be in the total while it is in review.
    assert vendor(built, "kaveri").totals.lines_counted == 28


def test_review_cell_shows_a_provisional_value_but_never_counts_it(built):
    kaveri_l01 = cell(built, "kaveri", "L01")
    assert kaveri_l01.state == "needs_review" and kaveri_l01.inr_per_base is None
    assert kaveri_l01.display_inr == pytest.approx(0.65 * 1000 * 83.42, abs=0.01)
    assert kaveri_l01.annotation == "per box?" and not kaveri_l01.is_lowest
    assert kaveri_l01.extended_inr is None


def test_every_cell_with_a_reading_has_provenance(built):
    for row in built.grid.lines:
        for vendor_id, got in row.cells.items():
            if got.how in ("explicit", "per_kg"):
                assert len(got.readings) == 2, (vendor_id, row.line_id)
                for reading in got.readings:
                    assert reading.source_ref.file and reading.source_ref.locator
                    assert reading.source_ref.snippet and reading.model


def test_lowest_on_line_ignores_cells_in_review(built):
    for row in built.grid.lines:
        counted = [c.inr_per_base for c in row.cells.values() if c.inr_per_base is not None]
        lowest = [c for c in row.cells.values() if c.is_lowest]
        assert lowest and all(c.inr_per_base == min(counted) for c in lowest)


def test_vendor_headers(built):
    assert [v.lines_quoted for v in built.grid.vendors] == [30, 30, 29, 27, 30]
    assert [v.quality for v in built.grid.vendors] == ["Pass", "Pass", "Partial", "Fail", "Pass"]
    freight = {v.vendor_id: (v.freight.kind, v.freight.amount_inr) for v in built.grid.vendors}
    assert freight == {
        "meridian": ("included", None), "sribalaji": ("lump_sum", 520000.0),
        "kaveri": ("extra_unpriced", None), "northbox": ("lump_sum", 410000.0),
        "anand": ("extra_unpriced", None),
    }  # fmt: skip
    assert vendor(built, "kaveri").format_label == "DOCX · USD"


def test_resolving_the_unit_ambiguity_puts_the_value_in_the_total(built):
    item = next(i for i in built.items if i.kind == "unit_ambiguity")
    notes = {o.option_id: o.note for o in item.options}
    assert "x below" in notes["per_pack"]  # the bundle reading is absurd against other vendors
    before = vendor(built, "kaveri").totals.extended_inr
    review.resolve(RFX_ID, item.id, actor="buyer", option_id="per_piece")
    after = grid.build(RFX_ID)
    got = cell(after, "kaveri", "L01")
    assert got.state == "confident" and got.inr_per_base == pytest.approx(54223.0)
    assert vendor(after, "kaveri").totals.extended_inr == pytest.approx(
        before + 54223.0 * 65, abs=1
    )
    assert after.grid.review_open == built.grid.review_open - 1


def test_discount_readings_change_different_cells(built):
    item = next(i for i in built.items if i.kind == "footnote_condition")
    list_price = cell(built, "sribalaji", "L04").display_inr
    review.resolve(RFX_ID, item.id, actor="buyer", option_id="by_rate")
    by_rate = grid.build(RFX_ID)
    assert cell(by_rate, "sribalaji", "L04").inr_per_base == pytest.approx(list_price * 0.96)
    assert cell(by_rate, "sribalaji", "L04").normalization_trace[-1].op == "discount"
    l01 = cell(by_rate, "sribalaji", "L01").inr_per_base
    review.reopen(RFX_ID, item.id, actor="buyer")
    review.resolve(RFX_ID, item.id, actor="buyer", option_id="by_line_value")
    by_value = grid.build(RFX_ID)
    assert cell(by_value, "sribalaji", "L01").inr_per_base == pytest.approx(l01 * 0.96)


def test_override_and_exclude_are_states_with_a_reason_and_can_be_reverted(built):
    review.override_cell(
        RFX_ID, "anand", "L01", actor="buyer", reason="verbal confirmation", value=54000
    )
    review.override_cell(
        RFX_ID, "meridian", "L02", actor="buyer", reason="spec mismatch", exclude=True
    )
    after = grid.build(RFX_ID)
    anand = cell(after, "anand", "L01")
    assert anand.state == "overridden" and anand.inr_per_base == 54000
    assert anand.override.reason == "verbal confirmation" and anand.display_inr == pytest.approx(
        53886.0
    )
    excluded = cell(after, "meridian", "L02")
    assert excluded.state == "overridden" and excluded.excluded and excluded.inr_per_base is None
    with pytest.raises(review.ReviewError):
        review.override_cell(RFX_ID, "anand", "L03", actor="buyer", reason=" ", value=1)
    review.revert_cell(RFX_ID, "anand", "L01", actor="buyer")
    assert cell(grid.build(RFX_ID), "anand", "L01").state == "confident"


def test_every_decision_is_audited(built):
    from app.db import session_scope
    from app.services import audit

    item = next(i for i in built.items if i.kind == "ocr_disagreement")
    review.resolve(RFX_ID, item.id, actor="buyer", option_id="value:3935.0")
    review.override_cell(
        RFX_ID, "anand", "L01", actor="buyer", reason="confirmed by phone", value=54000
    )
    with session_scope() as session:
        log = audit.events(session, RFX_ID)
    assert [event["action"] for event in log] == ["cell.override", "review.resolve"]
    assert "confirmed by phone" in log[0]["summary"] and log[0]["actor"] == "buyer"
    assert cell(grid.build(RFX_ID), "northbox", "L05").inr_per_base == 39350.0
