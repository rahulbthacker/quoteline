"""`make eval`: the eval report.

Extraction accuracy per vendor, per model, per field, against the golden set; agreement;
flag precision and missed problems; quality verdict accuracy; free-text conditions graded by
the judge model; latency and cost. Written to backend/var/eval_report.json and shown in the
Run inspector. The numbers in docs/NOTE.md come from this file.
"""

from __future__ import annotations

import json
import re
import sys
import uuid
from datetime import UTC, datetime

from pydantic import BaseModel
from sqlalchemy import select

from app.api.admin import EVAL_REPORT
from app.db import session_scope
from app.eval import golden
from app.eval.harness import FIELDS, evaluate_vendor
from app.llm import gateway, prompts
from app.llm.contracts import LLMRequest, ModelCallError
from app.models import ExtractionCallRow, TraceRow
from app.services import grid, ingest

RFX_ID = "RFX-0147"


class Verdict(BaseModel):
    statement: str
    captured: bool
    faithful: bool
    kind_correct: bool
    reason: str


class JudgeOutput(BaseModel):
    verdicts: list[Verdict]


def truth_statements(vendor_id: str) -> list[dict]:
    """Free-text statements the generator put in each vendor's file."""
    truth = golden.load(vendor_id)
    out = [{"kind": "freight", "text": truth["freight"]["statement"]}]
    if "discount" in truth:
        # Drop the footnote's own number ("2. 4% discount...") so it cannot be read as "2.4%".
        out.append(
            {"kind": "discount", "text": re.sub(r"^\d+\.\s+", "", truth["discount"]["text"])}
        )
    if "unit_note" in truth:
        out.append({"kind": "unit_basis", "text": truth["unit_note"]["text"]})
    if "default_unit_statement" in truth:
        out.append({"kind": "unit_basis", "text": truth["default_unit_statement"]})
    if "unit_statement" in truth:
        out.append({"kind": "unit_basis", "text": truth["unit_statement"]})
    for statement in truth.get("statements", []):
        if statement["kind"] == "same_as_last_year":
            out.append({"kind": "same_as_last_year", "text": statement["text"]})
    return out


def judge(vendor_id: str, conditions: list, run_id: str) -> list[dict] | None:
    statements = truth_statements(vendor_id)
    prompt = prompts.load("judge_v1")
    listing = "\n".join(f"- [{c.kind}] {c.text}" + (f" (applies to: {c.applies_to})" if c.applies_to else "")
                        for c in conditions) or "(none reported)"  # fmt: skip
    text = (
        "Ground-truth statements:\n" + "\n".join(f"- [{s['kind']}] {s['text']}" for s in statements)
        + f"\n\nConditions the extractor reported:\n{listing}\n\n"
        "Return one verdict per ground-truth statement, in the same order."
    )  # fmt: skip
    try:
        result = gateway.call(
            LLMRequest(role="JUDGE", prompt_version=prompt.version, system=prompt.text, text=text,
                       output_schema=JudgeOutput, max_tokens=6000, effort="medium"),
            run_id=run_id, rfx_id=RFX_ID,
        )  # fmt: skip
    except ModelCallError:
        return None
    return [v.model_dump() for v in result.parsed.verdicts]


def build() -> dict:
    rfx = ingest.get_rfx(RFX_ID)
    run_id = f"eval-{uuid.uuid4().hex[:8]}"
    result = grid.build(RFX_ID)
    with session_scope() as session:
        latest = session.scalars(
            select(ExtractionCallRow.run_id).order_by(ExtractionCallRow.id.desc()).limit(1)
        ).first()
        traces = session.scalars(select(TraceRow).where(TraceRow.parent_run_id == latest)).all()
        by_call = {t.call_id: t for t in traces}
        calls = session.scalars(
            select(ExtractionCallRow).where(ExtractionCallRow.run_id == latest)
        ).all()
        call_stats = {
            (c.vendor_id, c.role): {
                "latency_s": round(by_call[c.call_id].latency_ms / 1000, 1)
                if c.call_id in by_call
                else None,
                "cost_inr": by_call[c.call_id].cost_inr if c.call_id in by_call else None,
                "input_tokens": by_call[c.call_id].input_tokens if c.call_id in by_call else None,
                "output_tokens": by_call[c.call_id].output_tokens if c.call_id in by_call else None,
            }
            for c in calls
        }
        run_cost = round(sum(t.cost_inr or 0 for t in traces), 2)
        run_calls, run_failed = len(traces), sum(1 for t in traces if t.status != "ok")

    vendors = []
    totals = {role: {f: [0, 0] for f in FIELDS} for role in ("primary", "secondary")}
    flags_raised = flags_real = missed = 0
    wrong_counted = []
    for vendor_id in golden.VENDORS:
        report = evaluate_vendor(rfx, vendor_id)
        truth = golden.load(vendor_id)
        reads = ingest.load_vendor_reads(RFX_ID, vendor_id)
        models = {}
        for role, score in report.scores.items():
            for name in FIELDS:
                totals[role][name][0] += score.correct[name]
                totals[role][name][1] += score.total
            verdicts = judge(vendor_id, reads[f"{role}_conditions"], run_id)
            models[role] = {
                "model": score.model,
                "rows": score.total,
                "accuracy": {name: score.accuracy(name) for name in FIELDS},
                "errors": score.errors + score.spurious,
                "free_text": verdicts,
                "free_text_score": (
                    round(sum(v["captured"] and v["faithful"] for v in verdicts) / len(verdicts), 3)
                    if verdicts else None
                ),
                **(call_stats.get((vendor_id, role)) or {}),
            }  # fmt: skip
        expected_kinds = {item["kind"] for item in truth["expected_review_items"]}
        raised_kinds = {flag.kind for flag in report.flags}
        flags_raised += len(raised_kinds)
        flags_real += len(raised_kinds & expected_kinds)
        missed += len(report.expected_missed)
        # A missed problem that matters most: a wrong number sitting in a counted cell.
        for item in truth["lines"]:
            cell = next(r for r in result.grid.lines if r.line_id == item["line_id"]).cells[
                vendor_id
            ]
            if cell.state == "confident" and item["normalised_inr_per_1000"] is not None:
                if abs(cell.inr_per_base - item["normalised_inr_per_1000"]) > 0.01:
                    wrong_counted.append(
                        f"{vendor_id} {item['line_id']}: grid {cell.inr_per_base}, golden {item['normalised_inr_per_1000']}"
                    )
        quality = result.quality.get(vendor_id)
        verdict_truth = {q["question_id"]: q["expected"] for q in truth["questionnaire"]}
        answers = quality.answers if quality else []
        vendors.append({
            "vendor_id": vendor_id, "vendor": truth["vendor_name"], "format": truth["format"],
            "agreement": report.agreement, "models": models,
            "flags_expected_met": report.expected_met, "flags_missed": report.expected_missed,
            "flags_unexpected": report.unexpected, "cell_states_wrong": report.states_wrong,
            "quality": {
                "result": next(v.quality for v in result.grid.vendors if v.vendor_id == vendor_id),
                "expected_result": truth["quality_result"],
                "verdicts_correct": sum(1 for a in answers if a["status"] == verdict_truth[a["question_id"]]),
                "verdicts_total": len(verdict_truth),
                "wrong": [f"{a['question_id']}: {a['status']} (golden {verdict_truth[a['question_id']]})"
                          for a in answers if a["status"] != verdict_truth[a["question_id"]]],
            },
        })  # fmt: skip

    def overall(role: str) -> dict:
        return {name: round(c / t, 4) if t else None for name, (c, t) in totals[role].items()}

    agreements = [v["agreement"] for v in vendors if v["agreement"] is not None]
    free = [
        m["free_text_score"]
        for v in vendors
        for m in v["models"].values()
        if m["free_text_score"] is not None
    ]
    quality_correct = sum(v["quality"]["verdicts_correct"] for v in vendors)
    quality_total = sum(v["quality"]["verdicts_total"] for v in vendors)
    headline = {
        "primary_accuracy": overall("primary"),
        "secondary_accuracy": overall("secondary"),
        "rows_scored_per_model": totals["primary"]["value"][1],
        "agreement_rate": round(sum(agreements) / len(agreements), 4) if agreements else None,
        "flag_precision": round(flags_real / flags_raised, 4) if flags_raised else None,
        "flags_raised": flags_raised,
        "missed_problems": missed + len(wrong_counted),
        "wrong_values_in_counted_cells": wrong_counted,
        "free_text_score": round(sum(free) / len(free), 3) if free else None,
        "quality_verdict_accuracy": round(quality_correct / quality_total, 4) if quality_total else None,
        "quality_results_correct": sum(1 for v in vendors if v["quality"]["result"] == v["quality"]["expected_result"]),
        "ingest_calls": run_calls, "ingest_failed_calls": run_failed, "ingest_cost_inr": run_cost,
        "mean_extraction_latency_s": round(
            sum(m["latency_s"] or 0 for v in vendors for m in v["models"].values()) / (2 * len(vendors)), 1
        ),
    }  # fmt: skip
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "rfx_id": RFX_ID,
        "ingest_run": latest,
        "judge_run": run_id,
        "headline": headline,
        "vendors": vendors,
        "method": (
            "Truth is exact because the generator that wrote the five reply files also wrote the "
            "golden set. Field accuracy counts a row as correct only if it is matched to the right "
            "RFx line and the raw value, unit and currency equal the golden values. A flagged cell "
            "with a wrong value is not a missed problem; a counted cell with a wrong value is."
        ),
    }


def main() -> int:
    report = build()
    EVAL_REPORT.parent.mkdir(parents=True, exist_ok=True)
    EVAL_REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    h = report["headline"]
    print(f"\nEval report for {report['rfx_id']} (ingest run {report['ingest_run']})\n")
    print(
        f"{'vendor':<11}{'model':<26}{'rows':>5}"
        + "".join(f"{f:>10}" for f in FIELDS)
        + f"{'free-text':>11}{'s':>7}{'₹':>8}"
    )
    for vendor in report["vendors"]:
        for model in vendor["models"].values():
            acc = "".join(f"{(model['accuracy'][f] or 0) * 100:>9.1f}%" for f in FIELDS)
            free = (
                f"{model['free_text_score'] * 100:>10.0f}%"
                if model["free_text_score"] is not None
                else f"{'-':>11}"
            )
            print(f"{vendor['vendor_id']:<11}{model['model'] or 'FAILED':<26}{model['rows']:>5}{acc}{free}"
                  f"{model.get('latency_s') or 0:>7.0f}{model.get('cost_inr') or 0:>8.2f}")  # fmt: skip
    print(f"\nPrimary accuracy   {h['primary_accuracy']}")
    print(f"Secondary accuracy {h['secondary_accuracy']}")
    print(f"Agreement {h['agreement_rate']} · flag precision {h['flag_precision']} ({h['flags_raised']} raised) · "
          f"missed problems {h['missed_problems']} · free-text {h['free_text_score']} · "
          f"quality verdicts {h['quality_verdict_accuracy']} · ingest ₹{h['ingest_cost_inr']} in {h['ingest_calls']} calls")  # fmt: skip
    print(f"\nWritten to {EVAL_REPORT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
