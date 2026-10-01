"""Analyst agent: a question in, a query, its rows and an answer out.

Two model calls with code in between. The model proposes a query; the sandbox runs it; the
model writes the answer from the rows. Code then checks that the figures in the answer are
in the rows and adds the statement of what was excluded, which is never left to the model.
"""

from __future__ import annotations

import re
import uuid
from typing import Literal

from pydantic import BaseModel

from app.llm import gateway, prompts
from app.llm.contracts import LLMRequest, ModelCallError
from app.schemas import ScenarioFilters
from app.services import quote_table, sandbox
from app.services.grid import GridResult

PLAN_PROMPT = "analyst_plan_v1"
ANSWER_PROMPT = "analyst_answer_v1"
MAX_ROWS_TO_MODEL = 80


class ScenarioHint(BaseModel):
    quality_pass_only: bool
    exclude_vendors: list[str]
    freight_inclusive: bool
    single_vendor: str | None


class Plan(BaseModel):
    answerable: bool
    plan: str
    sql: str | None
    cannot_answer_reason: str | None
    data_needed: str | None
    scenario: ScenarioHint | None


class Chart(BaseModel):
    type: Literal["bar", "line", "none"]
    x: str | None
    y: list[str]
    title: str | None


class Answer(BaseModel):
    answer: str
    chart: Chart
    follow_ups: list[str]


def exclusions_statement(result: GridResult) -> dict:
    """What is left out of every figure, stated by code from the grid."""
    vendors = {v.vendor_id: v.name for v in result.grid.vendors}
    review, missing, excluded = [], [], []
    for row in result.grid.lines:
        for vendor_id, cell in row.cells.items():
            label = f"{row.line_id} {vendors[vendor_id]}"
            if cell.excluded:
                excluded.append(label)
            elif cell.state == "needs_review":
                review.append(label)
            elif cell.state == "not_quoted":
                missing.append(label)
    parts = []
    if review:
        parts.append(f"{len(review)} cell(s) are still in review ({', '.join(review)})")
    if missing:
        parts.append(f"{len(missing)} are not quoted ({', '.join(missing)})")
    if excluded:
        parts.append(f"{len(excluded)} were excluded by the buyer ({', '.join(excluded)})")
    text = (
        "; ".join(parts) + ". They are excluded from every figure above; the totals will move "
        "when they are resolved."
        if parts
        else "Every cell in the grid is counted: nothing is in review, unquoted or excluded."
    )
    return {"in_review": review, "not_quoted": missing, "excluded": excluded, "text": text}


def _context(result: GridResult) -> str:
    grid = result.grid
    vendors = "\n".join(
        f"- {v.vendor_id}: {v.name}; quality {v.quality}; {v.totals.lines_counted} lines counted, "
        f"{v.totals.needs_review} in review, {v.totals.not_quoted} not quoted; freight {v.freight.kind}"
        for v in grid.vendors
    )
    a = grid.assumptions
    return (
        f"RFx {grid.rfx_id}: {grid.title}. {len(grid.lines)} lines, {len(grid.vendors)} vendors.\n"
        f"Assumptions in force: base unit {a.base_unit}; FX {a.fx}; freight: {a.freight} tax: {a.tax}\n"
        f"Vendors:\n{vendors}\n"
        f"Excluded cells: {exclusions_statement(result)['text']}\n\n"
        f"Schema:\n{quote_table.SCHEMA_DOC}"
    )


def _numbers(text: str) -> list[float]:
    return [float(n.replace(",", "")) for n in re.findall(r"(?<![A-Za-z])\d[\d,]*(?:\.\d+)?", text)]


def check_figures(answer: str, rows: list[list]) -> list[str]:
    """Figures quoted in the answer that are not in the result rows (small counts are ignored)."""
    available: list[float] = []
    for row in rows:
        for value in row:
            if isinstance(value, bool):
                continue
            if isinstance(value, int | float):
                available.append(float(value))
            elif isinstance(value, str):
                available += _numbers(value)
    missing = []
    # "per 1,000" is the unit, and dimensions such as 600×400×400 are names, not figures.
    answer = re.sub(r"per\s+1,?000", "per unit", answer)
    answer = re.sub(r"\d+(?:\s*[x×]\s*\d+)+", "", answer)
    for token in re.findall(r"(?<![A-Za-z\d])\d[\d,]*(?:\.\d+)?", answer):
        value = float(token.replace(",", ""))
        decimals = len(token.split(".")[1]) if "." in token else 0
        if value <= 100 and decimals == 0:
            continue  # line counts, vendor counts, ply, question numbers
        if not any(round(abs(a), decimals) == round(value, decimals) for a in available):
            missing.append(token)
    return missing


def ask(result: GridResult, question: str, history: list[dict] | None = None) -> dict:
    """Answer one question. Always returns a payload; failures are stated, never papered over."""
    run_id = f"analyse-{uuid.uuid4().hex[:8]}"
    rfx_id = result.grid.rfx_id
    snapshot, digest = quote_table.build_snapshot(result)
    exclusions = exclusions_statement(result)
    context = _context(result)
    previous = "\n".join(f"- {turn['question']}" for turn in (history or [])[-4:])
    plan_prompt = prompts.load(PLAN_PROMPT)
    payload: dict = {
        "run_id": run_id, "question": question, "snapshot": digest, "exclusions": exclusions,
        "status": "answered", "plan": None, "sql": None, "columns": [], "rows": [], "answer": None,
        "chart": None, "follow_ups": [], "scenario": None, "unverified_figures": [], "attempts": [],
    }  # fmt: skip

    def plan_call(extra: str = "") -> Plan:
        text = f"{context}\n\n" + (
            f"Earlier questions in this session:\n{previous}\n\n" if previous else ""
        )
        text += f"Question: {question}{extra}"
        call = gateway.call(
            LLMRequest(
                role="ANALYST", prompt_version=plan_prompt.version, system=plan_prompt.text,
                text=text, output_schema=Plan, max_tokens=12000, effort="high",
            ),
            run_id=run_id, rfx_id=rfx_id,
        )  # fmt: skip
        return call.parsed

    try:
        plan = plan_call()
    except ModelCallError as exc:
        return payload | {
            "status": "model_error",
            "answer": f"The analyst model could not be reached: {exc}",
        }

    payload["plan"] = plan.plan
    if not plan.answerable or not plan.sql:
        return payload | {
            "status": "cannot_answer",
            "answer": plan.cannot_answer_reason or "This cannot be answered from the quote data.",
            "data_needed": plan.data_needed,
        }

    query_result = None
    sql = plan.sql
    for attempt in (1, 2):  # one repair attempt, with the error shown to the model
        try:
            query_result = sandbox.run(snapshot, sql)
            payload["attempts"].append({"sql": sql, "ok": True})
            break
        except (sandbox.QueryRejected, sandbox.QueryFailed) as exc:
            payload["attempts"].append({"sql": sql, "ok": False, "error": str(exc)})
            if attempt == 2:
                return payload | {
                    "status": "query_failed", "sql": sql,
                    "answer": f"The query for this question failed twice and no answer is shown. Last error: {exc}",
                }  # fmt: skip
            try:
                plan = plan_call(
                    f"\n\nYour previous query failed.\nQuery:\n{sql}\nError: {exc}\nWrite a corrected query."
                )
            except ModelCallError as model_exc:
                return payload | {
                    "status": "model_error",
                    "answer": f"The analyst model could not be reached: {model_exc}",
                }
            if not plan.sql:
                return payload | {
                    "status": "cannot_answer",
                    "answer": plan.cannot_answer_reason or "No query could be written.",
                }
            sql = plan.sql

    payload |= {
        "sql": sandbox.check(sql), "columns": query_result.columns, "rows": query_result.rows,
        "truncated": query_result.truncated, "elapsed_ms": query_result.elapsed_ms,
        "rows_out": len(query_result.rows),
    }  # fmt: skip
    if plan.scenario is not None:
        vendor_ids = {v.vendor_id for v in result.grid.vendors}
        hint = plan.scenario
        payload["scenario"] = {
            "filters": ScenarioFilters(
                quality_pass_only=hint.quality_pass_only,
                exclude_vendors=[v for v in hint.exclude_vendors if v in vendor_ids],
                freight_inclusive=hint.freight_inclusive,
            ).model_dump(),
            "single_vendor": hint.single_vendor if hint.single_vendor in vendor_ids else None,
        }

    answer_prompt = prompts.load(ANSWER_PROMPT)
    shown = query_result.rows[:MAX_ROWS_TO_MODEL]
    table = "\n".join(
        [" | ".join(query_result.columns)] + [" | ".join(str(v) for v in row) for row in shown]
    )
    text = (
        f"Question: {question}\n\nQuery:\n{payload['sql']}\n\n"
        f"Result ({len(query_result.rows)} rows{', truncated' if query_result.truncated else ''}):\n{table}\n\n"
        f"Excluded from the data: {exclusions['text']}\n"
        f"Assumptions in force: {result.grid.assumptions.model_dump()}"
    )
    try:
        call = gateway.call(
            LLMRequest(
                role="ANALYST", prompt_version=answer_prompt.version, system=answer_prompt.text,
                text=text, output_schema=Answer, max_tokens=8000, effort="medium",
            ),
            run_id=run_id, rfx_id=rfx_id,
        )  # fmt: skip
    except ModelCallError as exc:
        return payload | {
            "status": "model_error",
            "answer": f"The query ran, but the answer could not be written: {exc}. The rows are shown below.",
        }
    answer: Answer = call.parsed
    chart = answer.chart
    valid = chart.type != "none" and chart.x in query_result.columns and chart.y
    valid = valid and all(col in query_result.columns for col in chart.y)
    payload |= {
        "answer": answer.answer,
        "chart": chart.model_dump() if valid else None,
        "follow_ups": answer.follow_ups[:3],
        "unverified_figures": check_figures(answer.answer, query_result.rows),
    }
    return payload
