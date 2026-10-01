"""Compare and Review: the grid, cell provenance, overrides, the review queue, quality."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import persona, require
from app.db import session_scope
from app.models import AuditEventRow, AwardRow, OutboxRow, RfxRow, ScenarioRow, VendorQualityRow
from app.schemas import Grid, ReviewItem
from app.services import audit, export, grid, outbound, review

router = APIRouter()
Who = Annotated[str, Depends(persona)]


class OverrideRequest(BaseModel):
    value: float | None = None
    exclude: bool = False
    reason: str


class ResolveRequest(BaseModel):
    option_id: str | None = None
    value: float | None = None
    amount: float | None = None
    reason: str | None = None


class AskRequest(BaseModel):
    item_ids: list[str]


class QualityOverride(BaseModel):
    status: str
    reason: str


def _build(rfx_id: str) -> grid.GridResult:
    try:
        return grid.build(rfx_id)
    except KeyError:
        raise HTTPException(404, f"RFx {rfx_id} not found") from None


@router.get("/rfx/{rfx_id}/overview")
def overview(rfx_id: str) -> dict:
    """What the shell needs to draw the stage stepper: where this RFx stands."""
    result = _build(rfx_id)
    g = result.grid
    with session_scope() as session:
        rfx_row = session.get(RfxRow, rfx_id)
        sent = session.scalars(
            select(OutboxRow.id).where(OutboxRow.rfx_id == rfx_id, OutboxRow.kind == "rfx")
        ).all()
        scenarios = session.scalars(
            select(ScenarioRow.id).where(ScenarioRow.rfx_id == rfx_id)
        ).all()
        award = session.scalars(
            select(AwardRow).where(AwardRow.rfx_id == rfx_id).order_by(AwardRow.updated_at.desc())
        ).first()
        award_status = award.status if award else None
        status = rfx_row.status
    return {
        "rfx_id": rfx_id, "title": g.title, "status": status, "lines": len(g.lines),
        "vendors": len(g.vendors), "sent": len(sent),
        "replies": sum(1 for v in g.vendors if v.has_reply),
        "review_open": g.review_open, "review_total": len(result.items),
        "cells_in_review": g.review_blocking_cells, "overrides": g.counts["overridden"],
        "scenarios": len(scenarios), "award_status": award_status, "run": g.run.model_dump(),
    }  # fmt: skip


@router.get("/rfx/{rfx_id}/grid", response_model=Grid)
def get_grid(rfx_id: str) -> Grid:
    """150 cells with their states. `view=normalised|raw` is a display choice: every cell
    carries both `inr_per_base` and `raw_display`."""
    return _build(rfx_id).grid


@router.get("/rfx/{rfx_id}/cells/{vendor_id}/{line_id}")
def get_cell(rfx_id: str, vendor_id: str, line_id: str) -> dict:
    """Full provenance for one number: source, both readings, arithmetic, flags, history."""
    result = _build(rfx_id)
    row = next((r for r in result.grid.lines if r.line_id == line_id), None)
    if row is None or vendor_id not in row.cells:
        raise HTTPException(404, "no such cell")
    cell = row.cells[vendor_id]
    vendor = next(v for v in result.grid.vendors if v.vendor_id == vendor_id)
    items = [item for item in result.items if item.id in cell.review_item_ids]
    with session_scope() as session:
        history = [
            event for event in audit.events(session, rfx_id, limit=500)
            if f"{vendor.name} {line_id}" in event["summary"] or f"{vendor_id} {line_id}" in event["summary"]
            or any(item.id == (event.get("after") or {}).get("item_id") for item in items)
        ]  # fmt: skip
    return {
        "cell": cell.model_dump(mode="json"),
        "line": {"line_id": row.line_id, "description": row.description, "qty": row.qty, "uom": row.uom,
                 "last_year_inr": row.last_year_inr},
        "vendor": {"vendor_id": vendor_id, "name": vendor.name, "file": vendor.file, "format": vendor.format,
                   "file_url": f"/rfx/{rfx_id}/files/{vendor_id}/{vendor.file}" if vendor.file else None},
        "review_items": [item.model_dump(mode="json") for item in items],
        "others": {
            v.name: row.cells[v.vendor_id].inr_per_base
            for v in result.grid.vendors if v.vendor_id != vendor_id
        },
        "history": history,
    }  # fmt: skip


@router.post("/rfx/{rfx_id}/cells/{vendor_id}/{line_id}/override")
def override(rfx_id: str, vendor_id: str, line_id: str, body: OverrideRequest, who: Who) -> dict:
    actor = require(who, "buyer")
    try:
        review.override_cell(rfx_id, vendor_id, line_id, actor=actor, reason=body.reason,
                             value=body.value, exclude=body.exclude)  # fmt: skip
    except review.ReviewError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"ok": True}


@router.delete("/rfx/{rfx_id}/cells/{vendor_id}/{line_id}/override")
def revert(rfx_id: str, vendor_id: str, line_id: str, who: Who) -> dict:
    actor = require(who, "buyer")
    try:
        review.revert_cell(rfx_id, vendor_id, line_id, actor=actor)
    except review.ReviewError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"ok": True}


@router.get("/rfx/{rfx_id}/review", response_model=list[ReviewItem])
def review_queue(rfx_id: str) -> list[ReviewItem]:
    return _build(rfx_id).items


@router.post("/rfx/{rfx_id}/review/{item_id}/resolve", response_model=ReviewItem)
def resolve(rfx_id: str, item_id: str, body: ResolveRequest, who: Who) -> ReviewItem:
    actor = require(who, "buyer")
    try:
        return review.resolve(rfx_id, item_id, actor=actor, option_id=body.option_id, value=body.value,
                              amount=body.amount, reason=body.reason)  # fmt: skip
    except review.ReviewError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/rfx/{rfx_id}/review/{item_id}/reopen", response_model=ReviewItem)
def reopen(rfx_id: str, item_id: str, who: Who) -> ReviewItem:
    actor = require(who, "buyer")
    try:
        return review.reopen(rfx_id, item_id, actor=actor)
    except review.ReviewError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/rfx/{rfx_id}/review/ask-vendor")
def ask_vendor(rfx_id: str, body: AskRequest, who: Who) -> dict:
    """Draft one clarification email (live model call) for one vendor's open items. Not sent."""
    actor = require(who, "buyer")
    try:
        return outbound.ask_vendor(rfx_id, body.item_ids, actor=actor)
    except review.ReviewError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/rfx/{rfx_id}/quality")
def quality(rfx_id: str) -> list[dict]:
    result = _build(rfx_id)
    out = []
    for vendor in result.grid.vendors:
        row = result.quality.get(vendor.vendor_id)
        answers = []
        for answer in (row.answers if row else None) or []:
            override_ = (row.overrides or {}).get(answer["question_id"])
            answers.append(answer | {"override": override_,
                                     "effective_status": override_["status"] if override_ else answer["status"]})  # fmt: skip
        out.append({
            "vendor_id": vendor.vendor_id, "name": vendor.name, "result": vendor.quality,
            "model": row.model if row else None, "error": row.error if row else None, "answers": answers,
        })  # fmt: skip
    return out


@router.post("/rfx/{rfx_id}/quality/{vendor_id}/{question_id}/override")
def quality_override(
    rfx_id: str, vendor_id: str, question_id: str, body: QualityOverride, who: Who
) -> dict:
    actor = require(who, "evaluator")
    if body.status not in ("pass", "fail", "unanswered", "answered") or not body.reason.strip():
        raise HTTPException(422, "give a valid status and a reason")
    with session_scope() as session:
        row = session.get(VendorQualityRow, (rfx_id, vendor_id))
        if row is None:
            raise HTTPException(404, "no evaluation for this vendor")
        answer = next((a for a in row.answers if a["question_id"] == question_id), None)
        if answer is None:
            raise HTTPException(404, "no such question")
        overrides = dict(row.overrides or {})
        before = overrides.get(question_id, {"status": answer["status"]})
        overrides[question_id] = {"status": body.status, "reason": body.reason, "actor": actor}
        row.overrides = overrides
        audit.record(session, rfx_id, "quality.override",
                     f"Evaluator set {vendor_id} {question_id} to {body.status}. Reason: {body.reason}",
                     actor=actor, before=before, after=overrides[question_id])  # fmt: skip
    return {"ok": True}


@router.get("/rfx/{rfx_id}/audit")
def audit_log(rfx_id: str) -> list[dict]:
    with session_scope() as session:
        return audit.events(session, rfx_id)


@router.get("/rfx/{rfx_id}/audit/count")
def audit_count(rfx_id: str) -> dict:
    with session_scope() as session:
        rows = session.scalars(select(AuditEventRow.id).where(AuditEventRow.rfx_id == rfx_id)).all()
        return {"count": len(rows)}


@router.get("/rfx/{rfx_id}/export.xlsx")
def export_xlsx(rfx_id: str) -> Response:
    data = export.grid_xlsx(_build(rfx_id))
    return Response(
        data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{rfx_id}_comparison.xlsx"'},
    )  # fmt: skip


@router.get("/rfx/{rfx_id}/export.csv")
def export_csv(rfx_id: str) -> Response:
    return Response(
        export.grid_csv(_build(rfx_id)), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{rfx_id}_comparison.csv"'},
    )  # fmt: skip
