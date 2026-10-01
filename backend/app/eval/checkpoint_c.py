"""Checkpoint C gate: `make check-c`.

Reads the extractions stored by the last `make ingest` and compares them with the golden
set. Pass means: all five replies extracted with both models; Meridian and Sri Balaji are
100% on every field for both models; every vendor raises exactly its expected flags.
"""

from __future__ import annotations

import sys

from app.eval import golden
from app.eval.harness import FIELDS, evaluate_vendor
from app.services import ingest

RFX_ID = "RFX-0147"
MUST_BE_PERFECT = ("meridian", "sribalaji")


def main() -> int:
    rfx = ingest.get_rfx(RFX_ID)
    failures: list[str] = []
    print(
        f"\n{'vendor':<11}{'model':<30}{'rows':>5}"
        + "".join(f"{f:>10}" for f in FIELDS)
        + f"{'agree':>8}"
    )
    print("-" * 94)
    reports = [evaluate_vendor(rfx, vendor_id) for vendor_id in golden.VENDORS]
    for report in reports:
        for role, score in report.scores.items():
            cells = "".join(
                f"{score.accuracy(name) * 100:>9.1f}%" if score.total else f"{'-':>10}"
                for name in FIELDS
            )
            agree = (
                f"{report.agreement * 100:>7.1f}%" if report.agreement is not None else f"{'-':>8}"
            )
            name = score.model or f"{role} FAILED"
            print(f"{report.vendor_id:<11}{name:<30}{score.total:>5}{cells}{agree}")
            if score.model is None:
                failures.append(f"{report.vendor_id}: {role} extraction did not complete")
            if report.vendor_id in MUST_BE_PERFECT and not score.perfect:
                failures.append(f"{report.vendor_id}: {role} is not 100% on golden")
    print()
    for report in reports:
        print(f"{report.vendor_id}:")
        for role, score in report.scores.items():
            for error in score.errors + score.spurious:
                print(f"    {role:<10} WRONG  {error}")
        for key in report.expected_met:
            print(f"    flag ok      {key}")
        for key in report.expected_missed:
            print(f"    flag MISSED  {key}")
            failures.append(f"{report.vendor_id}: expected flag not raised as specified: {key}")
        for key in report.unexpected:
            print(f"    flag EXTRA   {key}")
            failures.append(f"{report.vendor_id}: unexpected flag {key}")
        for wrong in report.states_wrong:
            print(f"    state WRONG  {wrong}")
            failures.append(f"{report.vendor_id}: cell state {wrong}")
        for flag in report.flags:
            lines = ",".join(flag.lines) if len(flag.lines) <= 6 else f"{len(flag.lines)} lines"
            print(f"      · {flag.kind} [{lines}] {flag.reason[:150]}")
    print()
    if failures:
        print("Checkpoint C NOT passed:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("Checkpoint C passed: five replies extracted by both models; Meridian and Sri Balaji")
    print("at 100% on golden; every vendor raised exactly its expected flags.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
