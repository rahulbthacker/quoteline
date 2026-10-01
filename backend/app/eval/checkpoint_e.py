"""Checkpoint E gate: `make check-e`.

Asks the analyst the VP's split-award question and five further questions, live, and checks
each answer's figures against truth computed deterministically from the same grid by the
award engine and plain Python. Nothing here knows an expected number in advance: truth is
recomputed from the grid at run time. One question is unanswerable on purpose.
"""

from __future__ import annotations

import sys

from app.agents import analyst
from app.schemas import ScenarioFilters
from app.services import award, grid

RFX_ID = "RFX-0147"


def has_value(payload: dict, truth: float) -> bool:
    """Is this figure in the result rows, as rupees, lakh or crore?"""
    for row in payload.get("rows", []):
        for value in row:
            if isinstance(value, bool) or not isinstance(value, int | float):
                continue
            if abs(value - truth) <= max(1.0, abs(truth) * 0.0005):
                return True
            if abs(value - truth / 1e7) <= 0.006 or abs(value - truth / 1e5) <= 0.06:
                return True
    return False


def has_text(payload: dict, text: str) -> bool:
    haystack = (
        (payload.get("answer") or "")
        + " "
        + " ".join(str(v) for row in payload.get("rows", []) for v in row)
    )
    return text.lower() in haystack.lower()


def main() -> int:
    result = grid.build(RFX_ID)
    g = result.grid
    vendors = {v.vendor_id: v for v in g.vendors}
    split_pass = award.compute(result, ScenarioFilters(quality_pass_only=True))
    split_all = award.compute(result, ScenarioFilters())
    without_northbox = award.compute(result, ScenarioFilters(exclude_vendors=["northbox"]))

    lines = {line.line_id: line for line in result.rfx.line_items}
    wins_5ply: dict[str, int] = {}
    dearer = []
    for row in g.lines:
        counted = {
            vid: c.inr_per_base for vid, c in row.cells.items() if c.inr_per_base is not None
        }
        best_vendor = min(counted, key=counted.get)
        if lines[row.line_id].spec.ply == 5:
            wins_5ply[best_vendor] = wins_5ply.get(best_vendor, 0) + 1
        if row.last_year_inr is not None and min(counted.values()) > row.last_year_inr:
            dearer.append(row.line_id)
    top_5ply = max(wins_5ply, key=wins_5ply.get)
    kaveri = vendors["kaveri"]
    kaveri_out = sorted(row.line_id for row in g.lines if row.cells["kaveri"].inr_per_base is None)

    cases = [
        (
            "VP split-award question",
            "What if we split it, cheapest per line, but only among vendors who cleared the quality "
            "questionnaire? Compare with giving it all to the single cheapest vendor.",
            lambda p: [
                ("split total among quality-cleared vendors", has_value(p, split_pass["total_inr"])),
                ("a single-vendor total that is a real counted total",
                 any(has_value(p, v.totals.extended_inr) for v in g.vendors)),
                ("status answered", p["status"] == "answered"),
            ],
        ),
        (
            "Unrehearsed 1",
            "Which vendor is cheapest on the most 5-ply lines, and on how many of them?",
            lambda p: [
                (f"names {vendors[top_5ply].name}", has_text(p, vendors[top_5ply].name)),
                (f"count {wins_5ply[top_5ply]}", any(wins_5ply[top_5ply] in row for row in p["rows"])),
            ],
        ),
        (
            "Unrehearsed 2",
            "What do we lose by leaving NorthBox out of a cheapest-per-line split across all vendors?",
            lambda p: [
                ("split across all vendors", has_value(p, split_all["total_inr"])),
                ("split without NorthBox", has_value(p, without_northbox["total_inr"])),
            ],
        ),
        (
            "Unrehearsed 3",
            "On which lines is the best price we have this year higher than last year's contract price?",
            lambda p: [
                (f"lists exactly the {len(dearer)} dearer lines",
                 sorted({v for row in p["rows"] for v in row if isinstance(v, str) and v in lines}) == sorted(dearer)),
            ],
        ),
        (
            "Unrehearsed 4",
            "What is Kaveri's total, and which of their lines are not counted in it and why?",
            lambda p: [
                ("Kaveri counted total", has_value(p, kaveri.totals.extended_inr)),
                *[(f"mentions {line_id}", has_text(p, line_id)) for line_id in kaveri_out],
            ],
        ),
        (
            "Unrehearsed 5 (unanswerable)",
            "Which vendor has the best on-time delivery record over the last two years?",
            lambda p: [("declines and says what data is needed", p["status"] == "cannot_answer" and bool(p.get("data_needed")))],
        ),
    ]  # fmt: skip

    failures = []
    for name, question, checks in cases:
        payload = analyst.ask(result, question)
        print(f"\n=== {name}\nQ: {question}\nstatus: {payload['status']} · rows: {len(payload.get('rows', []))} "
              f"· unverified figures: {payload.get('unverified_figures')}")  # fmt: skip
        print(f"A: {payload.get('answer')}")
        if payload.get("sql"):
            print("SQL: " + " ".join(payload["sql"].split())[:600])
        for label, ok in checks(payload):
            print(f"   {'ok  ' if ok else 'FAIL'} {label}")
            if not ok:
                failures.append(f"{name}: {label}")
        if payload["status"] == "answered" and payload.get("unverified_figures"):
            failures.append(
                f"{name}: answer quotes figures not in the rows: {payload['unverified_figures']}"
            )
    print()
    if failures:
        print("Checkpoint E NOT passed:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("Checkpoint E passed: the VP question and five further questions answered correctly "
          "against truth recomputed from the grid.")  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
