"""Award engine: a scenario's rules -> allocations, exclusions and what each rule costs.

Deterministic. The analyst can explore; the award is always computed here, from the grid.
"""

from __future__ import annotations

from app.schemas import ScenarioFilters
from app.services.grid import GridResult, money


def _allocate(result: GridResult, eligible: set[str]) -> dict[str, tuple[str, float, float]]:
    """line_id -> (vendor_id, inr_per_1000, extended_inr) for the lowest counted eligible price."""
    out = {}
    for row in result.grid.lines:
        priced = [
            (cell.inr_per_base, vendor_id, cell.extended_inr)
            for vendor_id, cell in row.cells.items()
            if vendor_id in eligible and cell.inr_per_base is not None
        ]
        if priced:
            price, vendor_id, extended = min(priced)
            out[row.line_id] = (vendor_id, price, extended)
    return out


def _lakh(value: float) -> str:
    return f"₹{value / 1e5:,.1f} L"


def compute(result: GridResult, filters: ScenarioFilters, single_vendor: str | None = None) -> dict:
    grid = result.grid
    vendors = {v.vendor_id: v for v in grid.vendors}
    replied = {v.vendor_id for v in grid.vendors if v.has_reply}
    rules = [
        f"Lowest normalised price per line, {grid.assumptions.base_unit}; FX at {grid.assumptions.fx}",
        "Lines in review or not quoted are excluded, never estimated",
    ]
    exclusions = []
    eligible = set(replied)
    for vendor_id in filters.exclude_vendors:
        if vendor_id in eligible:
            eligible.discard(vendor_id)
            exclusions.append({"vendor_id": vendor_id, "vendor": vendors[vendor_id].name,
                               "rule": "excluded_by_buyer", "reason": "excluded by the buyer for this scenario"})  # fmt: skip
    if filters.quality_pass_only:
        rules.append("Only vendors with questionnaire result Pass are eligible")
        for vendor_id in sorted(eligible):
            quality = vendors[vendor_id].quality
            if quality != "Pass":
                eligible.discard(vendor_id)
                failed = _failed_questions(result, vendor_id)
                exclusions.append({"vendor_id": vendor_id, "vendor": vendors[vendor_id].name,
                                   "rule": "quality_pass_only",
                                   "reason": f"questionnaire {quality or 'not evaluated'}" + (f" ({failed})" if failed else "")})  # fmt: skip
    if single_vendor:
        rules.append(f"Single source: all lines to {vendors[single_vendor].name}")
        eligible = {single_vendor} if single_vendor in eligible else set()

    allocation = _allocate(result, eligible)
    unconstrained = _allocate(result, replied)
    lines = {row.line_id: row for row in grid.lines}
    total = sum(extended for _, _, extended in allocation.values())

    by_vendor: dict[str, dict] = {}
    for line_id, (vendor_id, _price, extended) in allocation.items():
        entry = by_vendor.setdefault(vendor_id, {"lines": [], "extended_inr": 0.0})
        entry["lines"].append(line_id)
        entry["extended_inr"] += extended
    allocations = []
    freight_total, freight_open = 0.0, []
    for vendor_id, entry in sorted(by_vendor.items(), key=lambda kv: -kv[1]["extended_inr"]):
        vendor = vendors[vendor_id]
        if vendor.freight.kind == "lump_sum":
            freight_total += vendor.freight.amount_inr or 0
        elif vendor.freight.kind in ("extra_unpriced", "not_stated"):
            freight_open.append(vendor.name)
        allocations.append(
            {
                "vendor_id": vendor_id, "vendor": vendor.name, "quality": vendor.quality,
                "lines": entry["lines"], "line_count": len(entry["lines"]),
                "extended_inr": round(entry["extended_inr"], 2),
                "share_pct": round(entry["extended_inr"] / total * 100, 1) if total else 0.0,
                "freight": vendor.freight.model_dump(),
            }
        )  # fmt: skip
    if filters.freight_inclusive:
        rules.append(
            "Stated freight added for each awarded vendor; unpriced freight is a pre-award condition"
        )
    else:
        rules.append(
            "Freight shown separately; unpriced freight is flagged as a pre-award condition"
        )
    overridden = [
        f"{vendors[vid].name} {row.line_id}"
        for row in grid.lines for vid, cell in row.cells.items() if cell.state == "overridden"
    ]  # fmt: skip
    if overridden:
        rules.append(
            f"Buyer overrides and exclusions ({len(overridden)}) are carried with their reasons: {', '.join(overridden)}"
        )

    allocated = set(allocation)
    unallocated = [
        {"line_id": row.line_id, "description": row.description,
         "reason": "no eligible vendor has a counted price for this line"}
        for row in grid.lines if row.line_id not in allocated
    ]  # fmt: skip

    # Best single vendor among the eligible, on the lines this scenario allocates.
    singles = []
    for vendor_id in sorted(eligible if not single_vendor else replied):
        cells = {row.line_id: row.cells[vendor_id] for row in grid.lines}
        covered = [l for l in allocated if cells[l].inr_per_base is not None]  # noqa: E741
        singles.append(
            {
                "vendor_id": vendor_id, "vendor": vendors[vendor_id].name,
                "covers_all": len(covered) == len(allocated), "lines_covered": len(covered),
                "extended_inr": round(sum(cells[l].extended_inr for l in covered), 2),  # noqa: E741
            }
        )  # fmt: skip
    full = [s for s in singles if s["covers_all"]]
    best_single = min(full, key=lambda s: s["extended_inr"]) if full else None

    # Like for like against last year's contract.
    comparable = [l for l in allocated if lines[l].last_year_inr is not None]  # noqa: E741
    last_year = sum(lines[l].last_year_inr * lines[l].qty / 1000 for l in comparable)  # noqa: E741
    this_year = sum(allocation[l][2] for l in comparable)  # noqa: E741

    # What each rule costs: the same lines, awarded with no eligibility rule at all.
    common = [l for l in allocated if l in unconstrained]  # noqa: E741
    free_total = sum(unconstrained[l][2] for l in common)  # noqa: E741
    constrained_total = sum(allocation[l][2] for l in common)  # noqa: E741
    rule_cost = round(constrained_total - free_total, 2)
    for exclusion in exclusions:
        vendor_id = exclusion["vendor_id"]
        would_win = [l for l in common if unconstrained[l][0] == vendor_id]  # noqa: E741
        exclusion["would_have_won"] = sorted(would_win)
        if would_win:
            exclusion["reason"] += (
                f"; would have been lowest on {len(would_win)} line(s): {', '.join(sorted(would_win))}"
            )

    open_items = [
        {"id": item.id, "vendor": item.vendor_name, "title": item.title, "status": item.status,
         "lines": [ref.line_id for ref in item.cells]}
        for item in result.items if item.status != "resolved"
    ]  # fmt: skip
    in_review = [
        f"{row.line_id} {vendors[vid].name}"
        for row in grid.lines for vid, cell in row.cells.items() if cell.state == "needs_review"
    ]  # fmt: skip
    headline_total = total + (freight_total if filters.freight_inclusive else 0.0)
    return {
        "filters": filters.model_dump(),
        "single_vendor": single_vendor,
        "rules_applied": rules,
        "allocations": allocations,
        "line_allocations": [
            {"line_id": line_id, "vendor_id": v, "vendor": vendors[v].name, "inr_per_1000": price,
             "extended_inr": extended}
            for line_id, (v, price, extended) in sorted(allocation.items())
        ],  # fmt: skip
        "total_inr": round(headline_total, 2),
        "goods_total_inr": round(total, 2),
        "freight_inr": round(freight_total, 2),
        "freight_unpriced_vendors": freight_open,
        "lines_allocated": len(allocation),
        "vendors_awarded": len(allocations),
        "unallocated": unallocated,
        "single_vendor_options": sorted(singles, key=lambda s: (not s["covers_all"], s["extended_inr"])),
        "best_single_vendor": best_single,
        "vs_best_single_inr": round(total - best_single["extended_inr"], 2) if best_single else None,
        "vs_best_single_pct": round((total - best_single["extended_inr"]) / best_single["extended_inr"] * 100, 2)
        if best_single else None,
        "last_year": {
            "lines_compared": len(comparable),
            "last_year_inr": round(last_year, 2),
            "this_year_inr": round(this_year, 2),
            "delta_inr": round(this_year - last_year, 2),
            "delta_pct": round((this_year - last_year) / last_year * 100, 2) if last_year else None,
        },
        "unconstrained_total_inr": round(free_total, 2),
        "rule_cost_inr": rule_cost,
        "rule_cost_pct": round(rule_cost / free_total * 100, 2) if free_total else None,
        "rule_cost_text": (
            f"Cost of the eligibility rules: {_lakh(rule_cost)} ({rule_cost / free_total * 100:.1f}%) "
            f"versus awarding the same {len(common)} lines across every vendor that replied."
            if free_total and exclusions else None
        ),
        "exclusions": exclusions,
        "open_items": open_items,
        "cells_in_review": in_review,
        "approval_blocked": bool(open_items),
        "summary": f"{money(headline_total)} across {len(allocation)} lines and {len(allocations)} vendors",
    }  # fmt: skip


def _failed_questions(result: GridResult, vendor_id: str) -> str:
    row = result.quality.get(vendor_id)
    if row is None:
        return ""
    parts = []
    for answer in row.answers or []:
        if not answer.get("mandatory"):
            continue
        override = (row.overrides or {}).get(answer["question_id"])
        status = override["status"] if override else answer["status"]
        if status != "pass":
            parts.append(f"{answer['question_id']} {status}")
    return ", ".join(parts)
