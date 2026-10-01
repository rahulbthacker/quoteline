"""Award engine and the analyst's query sandbox, on the golden-derived grid (no model)."""

from __future__ import annotations

import pytest

from app.eval import golden
from app.schemas import ScenarioFilters
from app.services import award, grid, quote_table, review, sandbox
from tests.helpers import RFX_ID, seed_exact_reads


@pytest.fixture
def result():
    seed_exact_reads()
    return grid.build(RFX_ID)


def golden_prices(pass_only: bool) -> dict[str, dict[str, float]]:
    """line -> vendor -> counted price, straight from the golden set."""
    out: dict[str, dict[str, float]] = {}
    for vendor_id in golden.VENDORS:
        truth = golden.load(vendor_id)
        if pass_only and truth["quality_result"] != "Pass":
            continue
        for item in truth["lines"]:
            if item["expected_state"] == "confident":
                out.setdefault(item["line_id"], {})[vendor_id] = item["normalised_inr_per_1000"]
    return out


def test_split_award_among_quality_cleared_vendors_matches_golden(result):
    qty = {row.line_id: row.qty for row in result.grid.lines}
    prices = golden_prices(pass_only=True)
    expected = sum(min(by_vendor.values()) * qty[line] / 1000 for line, by_vendor in prices.items())
    scenario = award.compute(result, ScenarioFilters(quality_pass_only=True))
    assert scenario["total_inr"] == pytest.approx(expected, abs=1.0)
    assert {a["vendor_id"] for a in scenario["allocations"]} <= {"meridian", "sribalaji", "anand"}
    assert {e["vendor_id"] for e in scenario["exclusions"]} == {"kaveri", "northbox"}
    assert sum(a["line_count"] for a in scenario["allocations"]) == scenario["lines_allocated"]
    assert abs(sum(a["share_pct"] for a in scenario["allocations"]) - 100) < 0.2


def test_rule_cost_is_the_difference_from_the_unconstrained_split(result):
    qty = {row.line_id: row.qty for row in result.grid.lines}
    free = golden_prices(pass_only=False)
    constrained = golden_prices(pass_only=True)
    common = set(free) & set(constrained)
    expected = sum(
        (min(constrained[l].values()) - min(free[l].values())) * qty[l] / 1000
        for l in common  # noqa: E741
    )
    scenario = award.compute(result, ScenarioFilters(quality_pass_only=True))
    assert scenario["rule_cost_inr"] == pytest.approx(expected, abs=1.0)
    assert scenario["rule_cost_inr"] > 0
    northbox = next(e for e in scenario["exclusions"] if e["vendor_id"] == "northbox")
    assert northbox["would_have_won"] and "Q3 fail" in northbox["reason"]


def test_best_single_vendor_only_counts_vendors_covering_every_allocated_line(result):
    scenario = award.compute(result, ScenarioFilters(quality_pass_only=True))
    # Sri Balaji's L04 is in review and Anand cannot price two lines, so only Meridian covers all.
    assert scenario["best_single_vendor"]["vendor_id"] == "meridian"
    assert scenario["vs_best_single_inr"] < 0
    item = next(i for i in result.items if i.kind == "footnote_condition")
    review.resolve(RFX_ID, item.id, actor="buyer", option_id="by_rate")
    after = award.compute(grid.build(RFX_ID), ScenarioFilters(quality_pass_only=True))
    assert after["best_single_vendor"]["vendor_id"] == "sribalaji"


def test_open_items_block_approval_and_freight_is_never_assumed(result):
    scenario = award.compute(
        result, ScenarioFilters(quality_pass_only=True, freight_inclusive=True)
    )
    assert scenario["approval_blocked"] and len(scenario["open_items"]) == result.grid.review_open
    assert "Anand Papers" in scenario["freight_unpriced_vendors"]
    assert scenario["total_inr"] == pytest.approx(
        scenario["goods_total_inr"] + scenario["freight_inr"]
    )
    assert scenario["last_year"]["delta_pct"] < 0


def test_single_vendor_scenario(result):
    scenario = award.compute(result, ScenarioFilters(), single_vendor="meridian")
    assert scenario["vendors_awarded"] == 1 and scenario["lines_allocated"] == 30
    truth = sum(
        i["normalised_inr_per_1000"]
        * next(r.qty for r in result.grid.lines if r.line_id == i["line_id"])
        / 1000
        for i in golden.load("meridian")["lines"]
    )
    assert scenario["total_inr"] == pytest.approx(truth, abs=1.0)


def test_quote_table_holds_only_counted_cells_and_explains_the_rest(result):
    path, digest = quote_table.build_snapshot(result)
    counted = sandbox.run(
        path, "SELECT count(*) AS n, sum(extended_inr) AS total FROM quotes"
    ).records()[0]
    assert counted["n"] == 141
    assert counted["total"] == pytest.approx(
        sum(v.totals.extended_inr for v in result.grid.vendors), abs=1
    )
    excluded = sandbox.run(
        path, "SELECT state, count(*) AS n FROM excluded_cells GROUP BY state"
    ).records()
    assert {r["state"]: r["n"] for r in excluded} == {"needs_review": 5, "not_quoted": 4}
    assert quote_table.build_snapshot(result)[1] == digest  # same grid, same snapshot


def test_sandbox_sql_reproduces_the_award_engine(result):
    path, _ = quote_table.build_snapshot(result)
    sql = """
        WITH best AS (
          SELECT line_id, min(extended_inr) AS extended FROM quotes WHERE quality = 'Pass' GROUP BY line_id
        ) SELECT sum(extended) AS total, count(*) AS lines FROM best
    """
    row = sandbox.run(path, sql).records()[0]
    scenario = award.compute(result, ScenarioFilters(quality_pass_only=True))
    assert row["total"] == pytest.approx(scenario["total_inr"], abs=1.0)
    assert row["lines"] == scenario["lines_allocated"]


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE quotes",
        "SELECT 1; SELECT 2",
        "COPY quotes TO '/tmp/x.csv'",
        "SELECT * FROM read_csv('/etc/passwd')",
        "ATTACH '/tmp/other.db' AS o",
        "INSTALL httpfs",
        "",
    ],
)
def test_sandbox_rejects_anything_but_one_select(sql, result):
    path, _ = quote_table.build_snapshot(result)
    with pytest.raises(sandbox.QueryRejected):
        sandbox.run(path, sql)


def test_sandbox_reports_sql_errors_and_cannot_write(result):
    path, _ = quote_table.build_snapshot(result)
    with pytest.raises(sandbox.QueryFailed, match="(?i)no_such_column|not found|does not have"):
        sandbox.run(path, "SELECT no_such_column FROM quotes")
    assert sandbox.run(path, "SELECT 'drop table' AS harmless_string").rows == [["drop table"]]
