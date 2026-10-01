"""Analyse and Award: questions over the grid, scenarios, the award and its sign-off."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select

from app.agents import analyst
from app.api.deps import persona, require
from app.db import session_scope
from app.models import AnalysisRow, AwardRow, ScenarioRow
from app.schemas import ScenarioFilters
from app.services import audit, award, export, grid

router = APIRouter()
Who = Annotated[str, Depends(persona)]


class Question(BaseModel):
    question: str


class ScenarioRequest(BaseModel):
    name: str
    filters: ScenarioFilters = ScenarioFilters()
    single_vendor: str | None = None
    analysis_id: str | None = None


class AwardRequest(BaseModel):
    scenario_id: str


class Decision(BaseModel):
    note: str | None = None


def _build(rfx_id: str) -> grid.GridResult:
    try:
        return grid.build(rfx_id)
    except KeyError:
        raise HTTPException(404, f"RFx {rfx_id} not found") from None


@router.post("/rfx/{rfx_id}/analyse")
def analyse(rfx_id: str, body: Question, who: Who) -> dict:
    """Question -> query -> rows -> answer. Two live model calls and one sandboxed query."""
    actor = require(who, "buyer", "vp")
    question = body.question.strip()
    if not question:
        raise HTTPException(422, "ask a question")
    result = _build(rfx_id)
    with session_scope() as session:
        history = [
            {"question": row.question}
            for row in session.scalars(
                select(AnalysisRow)
                .where(AnalysisRow.rfx_id == rfx_id)
                .order_by(AnalysisRow.created_at)
            )
        ]
    payload = analyst.ask(result, question, history)
    analysis_id = uuid.uuid4().hex[:12]
    payload["id"] = analysis_id
    payload["asked_by"] = actor
    payload["created_at"] = datetime.now(UTC).isoformat()
    with session_scope() as session:
        session.add(
            AnalysisRow(
                id=analysis_id, rfx_id=rfx_id, question=question, payload=payload, asked_by=actor
            )
        )
        audit.record(session, rfx_id, "analyse.ask", f"Asked the analyst: {question[:140]}",
                     actor=actor, after={"analysis_id": analysis_id, "status": payload["status"]})  # fmt: skip
    return payload


@router.get("/rfx/{rfx_id}/analyses")
def analyses(rfx_id: str) -> list[dict]:
    with session_scope() as session:
        rows = session.scalars(
            select(AnalysisRow).where(AnalysisRow.rfx_id == rfx_id).order_by(AnalysisRow.created_at)
        ).all()
        return [row.payload for row in rows]


def _analysis(analysis_id: str) -> dict:
    with session_scope() as session:
        row = session.get(AnalysisRow, analysis_id)
        if row is None:
            raise HTTPException(404, "no such analysis")
        return row.payload


@router.get("/analyses/{analysis_id}/export.xlsx")
def analysis_xlsx(analysis_id: str) -> Response:
    payload = _analysis(analysis_id)
    data = export.rows_xlsx("Quoteline analysis", payload["question"], payload.get("sql"),
                            payload.get("columns", []), payload.get("rows", []), payload["exclusions"]["text"])  # fmt: skip
    return Response(
        data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="analysis_{analysis_id}.xlsx"'},
    )  # fmt: skip


@router.get("/analyses/{analysis_id}/export.csv")
def analysis_csv(analysis_id: str) -> Response:
    payload = _analysis(analysis_id)
    return Response(
        export.rows_csv(payload.get("columns", []), payload.get("rows", [])), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="analysis_{analysis_id}.csv"'},
    )  # fmt: skip


def _scenario_view(row: ScenarioRow, result: grid.GridResult) -> dict:
    filters = ScenarioFilters.model_validate(row.payload["filters"])
    computed = award.compute(result, filters, row.payload.get("single_vendor"))
    return {
        "id": row.id, "name": row.name, "created_by": row.created_by,
        "created_at": row.created_at.isoformat(), "filters": filters.model_dump(),
        "single_vendor": row.payload.get("single_vendor"), "question": row.payload.get("question"),
        "query_text": row.payload.get("query_text"), "saved_total_inr": row.payload.get("saved_total_inr"),
        "computed": computed,
    }  # fmt: skip


@router.get("/rfx/{rfx_id}/scenarios")
def scenarios(rfx_id: str) -> dict:
    """Saved scenarios, recomputed from the current grid, plus the engine's standard options."""
    result = _build(rfx_id)
    with session_scope() as session:
        rows = session.scalars(
            select(ScenarioRow).where(ScenarioRow.rfx_id == rfx_id).order_by(ScenarioRow.created_at)
        ).all()
        saved = [_scenario_view(row, result) for row in rows]
    presets = [
        {"key": "split_all", "name": "Split, all vendors", "filters": ScenarioFilters().model_dump(),
         "single_vendor": None},
        {"key": "split_pass", "name": "Split, quality-cleared",
         "filters": ScenarioFilters(quality_pass_only=True).model_dump(), "single_vendor": None},
    ]  # fmt: skip
    for preset in presets:
        preset["computed"] = award.compute(
            result, ScenarioFilters.model_validate(preset["filters"])
        )
    return {"saved": saved, "presets": presets}


@router.post("/rfx/{rfx_id}/scenarios")
def save_scenario(rfx_id: str, body: ScenarioRequest, who: Who) -> dict:
    actor = require(who, "buyer", "vp")
    result = _build(rfx_id)
    vendor_ids = {v.vendor_id for v in result.grid.vendors}
    if body.single_vendor and body.single_vendor not in vendor_ids:
        raise HTTPException(422, "unknown vendor")
    question = query = None
    if body.analysis_id:
        analysis = _analysis(body.analysis_id)
        question, query = analysis["question"], analysis.get("sql")
    computed = award.compute(result, body.filters, body.single_vendor)
    scenario_id = uuid.uuid4().hex[:12]
    with session_scope() as session:
        row = ScenarioRow(
            id=scenario_id, rfx_id=rfx_id, name=body.name.strip() or "Untitled scenario", created_by=actor,
            payload={"filters": body.filters.model_dump(), "single_vendor": body.single_vendor,
                     "question": question, "query_text": query, "saved_total_inr": computed["total_inr"]},
        )  # fmt: skip
        session.add(row)
        audit.record(session, rfx_id, "scenario.save", f"Scenario saved: {row.name} ({computed['summary']})",
                     actor=actor, after={"scenario_id": scenario_id, "total_inr": computed["total_inr"]})  # fmt: skip
        session.flush()
        return _scenario_view(row, result)


def _award_view(rfx_id: str) -> dict:
    result = _build(rfx_id)
    with session_scope() as session:
        row = session.scalars(
            select(AwardRow).where(AwardRow.rfx_id == rfx_id).order_by(AwardRow.updated_at.desc())
        ).first()
        log = audit.events(session, rfx_id, limit=60)
        if row is None:
            return {"award": None, "audit": log}
        scenario = session.get(ScenarioRow, row.scenario_id)
        view = _scenario_view(scenario, result)
        return {
            "award": {"id": row.id, "status": row.status, "approvals": row.approvals,
                      "scenario_id": row.scenario_id, "updated_at": row.updated_at.isoformat()},
            "scenario": view, "computed": view["computed"], "audit": log,
        }  # fmt: skip


@router.get("/rfx/{rfx_id}/award")
def get_award(rfx_id: str) -> dict:
    return _award_view(rfx_id)


@router.post("/rfx/{rfx_id}/award")
def set_award(rfx_id: str, body: AwardRequest, who: Who) -> dict:
    """Make a saved scenario the award recommendation (status: draft)."""
    actor = require(who, "buyer")
    with session_scope() as session:
        scenario = session.get(ScenarioRow, body.scenario_id)
        if scenario is None or scenario.rfx_id != rfx_id:
            raise HTTPException(404, "no such scenario")
        row = AwardRow(id=uuid.uuid4().hex[:12], rfx_id=rfx_id, scenario_id=scenario.id, status="draft",
                       approvals=[])  # fmt: skip
        session.add(row)
        audit.record(session, rfx_id, "award.draft", f"Award drafted from scenario: {scenario.name}",
                     actor=actor, after={"award_id": row.id, "scenario_id": scenario.id})  # fmt: skip
    return _award_view(rfx_id)


def _transition(
    award_id: str, who: str, allowed: tuple[str, ...], status: str, decision: str, note: str | None
) -> dict:
    actor = require(who, *allowed)
    with session_scope() as session:
        row = session.get(AwardRow, award_id)
        if row is None:
            raise HTTPException(404, "no such award")
        rfx_id = row.rfx_id
    view = _award_view(rfx_id)
    if status in ("sent_for_approval", "approved") and view["computed"]["approval_blocked"]:
        open_count = len(view["computed"]["open_items"])
        raise HTTPException(
            409,
            f"Blocked: {open_count} review item(s) are still open. Resolve them before this award can go further.",
        )
    with session_scope() as session:
        row = session.get(AwardRow, award_id)
        before = {"status": row.status}
        row.status, row.updated_at = status, datetime.now(UTC)
        row.approvals = [*row.approvals, {"actor": actor, "decision": decision, "note": note,
                                          "at": datetime.now(UTC).isoformat(),
                                          "total_inr": view["computed"]["total_inr"]}]  # fmt: skip
        audit.record(session, rfx_id, f"award.{decision}",
                     f"Award {decision.replace('_', ' ')} ({view['computed']['summary']})" + (f". Note: {note}" if note else ""),
                     actor=actor, before=before, after={"status": status})  # fmt: skip
    return _award_view(rfx_id)


@router.post("/award/{award_id}/send-for-approval")
def send_for_approval(award_id: str, body: Decision, who: Who) -> dict:
    return _transition(
        award_id, who, ("buyer",), "sent_for_approval", "sent_for_approval", body.note
    )


@router.post("/award/{award_id}/approve")
def approve(award_id: str, body: Decision, who: Who) -> dict:
    return _transition(award_id, who, ("vp",), "approved", "approved", body.note)


@router.post("/award/{award_id}/request-changes")
def request_changes(award_id: str, body: Decision, who: Who) -> dict:
    return _transition(award_id, who, ("vp",), "changes_requested", "changes_requested", body.note)


@router.get("/rfx/{rfx_id}/award/export.pdf")
def award_pdf(rfx_id: str) -> Response:
    view = _award_view(rfx_id)
    if view["award"] is None:
        raise HTTPException(404, "no award has been drafted")
    data = export.award_pdf(_build(rfx_id), view["scenario"]["name"], view["computed"], view["audit"],
                            view["award"]["status"])  # fmt: skip
    return Response(data, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{rfx_id}_award_pack.pdf"'})  # fmt: skip
