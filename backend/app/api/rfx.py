"""RFx lifecycle: draft with the co-pilot, edit, send, receive, ingest."""

from __future__ import annotations

import email
import email.policy
import mimetypes
import threading
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from sqlalchemy import select

from app.agents import intake
from app.api.deps import persona, require
from app.config import REPO_ROOT
from app.db import session_scope
from app.llm.contracts import ModelCallError
from app.models import ExtractionCallRow, ReplyFileRow, RfxRow, VendorRow
from app.schemas import RFx
from app.services import audit, board, ingest, mail_stub, outbound

router = APIRouter()
Who = Annotated[str, Depends(persona)]
_jobs: dict[str, dict] = {}


class ChatRequest(BaseModel):
    messages: list[dict]
    draft: dict | None = None


class CreateRequest(BaseModel):
    draft: dict


class AssumptionsUpdate(BaseModel):
    fx_rate: float | None = None
    fx_source: str | None = None
    fx_as_of: str | None = None
    freight_policy: str | None = None
    tax_policy: str | None = None


def _get(rfx_id: str) -> RFx:
    try:
        return ingest.get_rfx(rfx_id)
    except KeyError:
        raise HTTPException(404, f"RFx {rfx_id} not found") from None


@router.get("/rfx")
def list_rfx() -> list[dict]:
    with session_scope() as session:
        rows = session.scalars(select(RfxRow).order_by(RfxRow.created_at)).all()
        return [
            {"id": row.id, "title": row.payload["title"], "status": row.status,
             "lines": len(row.payload["line_items"]), "created_at": row.created_at.isoformat()}
            for row in rows
        ]  # fmt: skip


@router.post("/intake/chat")
def intake_chat(body: ChatRequest, who: Who) -> dict:
    require(who, "buyer")
    try:
        return intake.chat(body.messages, body.draft)
    except ModelCallError as exc:
        raise HTTPException(502, f"The co-pilot model could not be reached: {exc}") from exc


@router.post("/rfx")
def create_rfx(body: CreateRequest, who: Who) -> dict:
    """Create an RFx from a co-pilot draft. Lines without a quantity are refused, not guessed."""
    actor = require(who, "buyer")
    draft = body.draft
    missing_qty = [
        i + 1 for i, line in enumerate(draft.get("line_items", [])) if not line.get("qty")
    ]
    if not draft.get("line_items"):
        raise HTTPException(422, "The draft has no line items.")
    if missing_qty:
        raise HTTPException(
            422, f"Lines {missing_qty} have no quantity. Fill them in before creating the RFx."
        )
    with session_scope() as session:
        existing = [row.id for row in session.scalars(select(RfxRow))]
        number = (
            max([int(i.split("-")[1]) for i in existing if i.split("-")[1].isdigit()] or [147]) + 1
        )
        rfx_id = f"RFX-{number:04d}"
        assumptions = list(draft.get("assumptions") or [])
        lines = []
        for index, line in enumerate(draft["line_items"], start=1):
            weight = board.estimate_weight_kg(
                line["description"], line.get("ply"), line.get("gsm"), line.get("dims_mm") or []
            )
            lines.append({
                "line_id": f"L{index:02d}", "description": line["description"],
                "spec": {"ply": line.get("ply"), "gsm": line.get("gsm"), "dims_mm": line.get("dims_mm") or None,
                         "print": line.get("print"), "board_weight_kg_per_pc": weight},
                "qty": line["qty"], "uom": line.get("uom") or "pcs",
                "last_year_price_inr": line.get("last_year_price_inr"),
            })  # fmt: skip
        if any(line["spec"]["board_weight_kg_per_pc"] for line in lines):
            assumptions.append(
                "Board weights are estimated from dimensions, ply and GSM; confirm against the spec."
            )
        terms = draft.get("terms") or {}
        payload = {
            "id": rfx_id, "title": draft.get("title") or "Untitled RFx",
            "category": draft.get("category") or "Corrugated packaging",
            "fx_policy": {"source": "RBI reference rate", "rate": 83.42, "foreign_currency": "USD",
                          "as_of": datetime.now(UTC).date().isoformat()},
            "freight_policy": "Freight is excluded from line prices and shown per vendor as stated.",
            "tax_policy": "GST is excluded from all prices.",
            "terms": {"payment": terms.get("payment"), "delivery": terms.get("delivery"),
                      "validity_days": terms.get("validity_days"), "assumptions": assumptions},
            "questionnaire": [
                {"question_id": f"Q{i}", "text": q["text"], "mandatory": bool(q.get("mandatory"))}
                for i, q in enumerate(draft.get("questionnaire") or [], start=1)
            ],
            "line_items": lines,
        }  # fmt: skip
        rfx = RFx.model_validate(payload)
        session.add(RfxRow(id=rfx_id, payload=rfx.model_dump(mode="json"), status="draft"))
        # The vendor master for this category: the vendors of the most recent RFx.
        seen = set()
        for vendor in session.scalars(select(VendorRow).order_by(VendorRow.position)).all():
            if vendor.vendor_id in seen:
                continue
            seen.add(vendor.vendor_id)
            session.add(VendorRow(rfx_id=rfx_id, vendor_id=vendor.vendor_id, name=vendor.name,
                                  contact=vendor.contact, email=vendor.email, city=vendor.city,
                                  position=vendor.position))  # fmt: skip
        audit.record(session, rfx_id, "rfx.create", f"RFx drafted with the co-pilot: {len(lines)} lines",
                     actor=actor)  # fmt: skip
    return {"id": rfx_id}


@router.get("/rfx/{rfx_id}")
def get_rfx(rfx_id: str) -> dict:
    rfx = _get(rfx_id)
    with session_scope() as session:
        row = session.get(RfxRow, rfx_id)
        vendors = session.scalars(
            select(VendorRow).where(VendorRow.rfx_id == rfx_id).order_by(VendorRow.position)
        ).all()
        return {
            "rfx": rfx.model_dump(mode="json"), "status": row.status,
            "vendors": [{"vendor_id": v.vendor_id, "name": v.name, "contact": v.contact,
                         "email": v.email, "city": v.city} for v in vendors],
        }  # fmt: skip


@router.put("/rfx/{rfx_id}")
def update_rfx(rfx_id: str, body: dict, who: Who) -> dict:
    actor = require(who, "buyer", "admin")
    _get(rfx_id)
    body["id"] = rfx_id
    try:
        rfx = RFx.model_validate(body)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(422, str(exc)) from exc
    with session_scope() as session:
        row = session.get(RfxRow, rfx_id)
        before = {"lines": len(row.payload["line_items"]), "title": row.payload["title"]}
        row.payload = rfx.model_dump(mode="json")
        audit.record(session, rfx_id, "rfx.edit", "RFx edited", actor=actor, before=before,
                     after={"lines": len(rfx.line_items), "title": rfx.title})  # fmt: skip
    return {"ok": True}


@router.put("/rfx/{rfx_id}/assumptions")
def update_assumptions(rfx_id: str, body: AssumptionsUpdate, who: Who) -> dict:
    """Change the FX, freight or tax assumption. The grid is recomputed from it on next read."""
    actor = require(who, "buyer", "admin")
    _get(rfx_id)
    with session_scope() as session:
        row = session.get(RfxRow, rfx_id)
        payload = dict(row.payload)
        before = {"fx_policy": payload["fx_policy"], "freight_policy": payload["freight_policy"],
                  "tax_policy": payload["tax_policy"]}  # fmt: skip
        fx = dict(payload["fx_policy"])
        if body.fx_rate is not None:
            if body.fx_rate <= 0:
                raise HTTPException(422, "FX rate must be positive")
            fx["rate"] = body.fx_rate
        if body.fx_source:
            fx["source"] = body.fx_source
        if body.fx_as_of:
            fx["as_of"] = body.fx_as_of
        payload["fx_policy"] = fx
        if body.freight_policy:
            payload["freight_policy"] = body.freight_policy
        if body.tax_policy:
            payload["tax_policy"] = body.tax_policy
        row.payload = RFx.model_validate(payload).model_dump(mode="json")
        audit.record(session, rfx_id, "assumptions.edit",
                     f"Assumptions changed: FX {fx['foreign_currency']} 1 = ₹{fx['rate']} ({fx['source']})",
                     actor=actor, before=before, after={"fx_policy": fx})  # fmt: skip
    return {"ok": True}


@router.post("/rfx/{rfx_id}/send")
def send(rfx_id: str, who: Who) -> dict:
    actor = require(who, "buyer")
    _get(rfx_id)
    return {"sent": outbound.send_rfx(rfx_id, actor=actor)}


@router.get("/rfx/{rfx_id}/outbox")
def get_outbox(rfx_id: str) -> list[dict]:
    return outbound.outbox(rfx_id)


@router.post("/rfx/{rfx_id}/inbox/deliver-seed")
def deliver_seed(rfx_id: str, who: Who) -> dict:
    """The receive half of the email stub: drop the fabricated vendor replies into the inbox."""
    require(who, "buyer")
    return {"delivered": mail_stub.deliver_seed_replies()}


@router.get("/rfx/{rfx_id}/inbox")
def inbox(rfx_id: str) -> dict:
    return {vendor: [p.name for p in files] for vendor, files in mail_stub.scan_inbox().items()}


def _run_ingest(rfx_id: str) -> None:
    try:
        summary = ingest.ingest(rfx_id)
        _jobs[rfx_id] |= {"status": "done", "summary": summary}
    except Exception as exc:  # noqa: BLE001  surfaced to the UI, never swallowed
        _jobs[rfx_id] |= {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}
    _jobs[rfx_id]["finished_at"] = datetime.now(UTC).isoformat()


@router.post("/rfx/{rfx_id}/ingest")
def start_ingest(rfx_id: str, who: Who) -> dict:
    """Read the inbox with both models. Runs in the background; poll GET for status."""
    require(who, "buyer")
    _get(rfx_id)
    if _jobs.get(rfx_id, {}).get("status") == "running":
        return _jobs[rfx_id]
    _jobs[rfx_id] = {"status": "running", "started_at": datetime.now(UTC).isoformat()}
    threading.Thread(target=_run_ingest, args=(rfx_id,), daemon=True).start()
    return _jobs[rfx_id]


@router.get("/rfx/{rfx_id}/ingest")
def ingest_status(rfx_id: str) -> dict:
    return _jobs.get(rfx_id, {"status": "idle"})


@router.get("/rfx/{rfx_id}/replies")
def replies(rfx_id: str) -> list[dict]:
    """Per vendor: the files they sent, how each was routed, and what each model made of it."""
    _get(rfx_id)
    with session_scope() as session:
        vendors = session.scalars(
            select(VendorRow).where(VendorRow.rfx_id == rfx_id).order_by(VendorRow.position)
        ).all()
        files = session.scalars(select(ReplyFileRow).where(ReplyFileRow.rfx_id == rfx_id)).all()
        calls = session.scalars(
            select(ExtractionCallRow).where(ExtractionCallRow.rfx_id == rfx_id)
        ).all()
        out = []
        for vendor in vendors:
            mine = [f for f in files if f.vendor_id == vendor.vendor_id]
            reads = ingest.load_vendor_reads(rfx_id, vendor.vendor_id) if mine else None
            out.append({
                "vendor_id": vendor.vendor_id, "name": vendor.name, "email": vendor.email,
                "received_at": mine[0].received_at.isoformat() if mine and mine[0].received_at else None,
                "files": [
                    {"name": f.name, "format": f.format, "kind": f.kind, "pages": f.pages,
                     "parent": f.parent, "needs_vision": f.needs_vision, "summary": f.summary,
                     "sections": (f.routing or {}).get("sections", []), "parsed_text": f.parsed_text,
                     "url": f"/rfx/{rfx_id}/files/{vendor.vendor_id}/{f.name}"}
                    for f in mine
                ],
                "extraction": [
                    {"file": c.file, "role": c.role, "model": c.model, "status": c.status,
                     "error": c.error, "agreement": c.agreement,
                     "rows": len(reads[c.role] or []) if reads else 0,
                     "conditions": [cond.model_dump(mode="json") for cond in reads[f"{c.role}_conditions"]] if reads else []}
                    for c in calls if c.vendor_id == vendor.vendor_id
                ],
                "lead_role": reads["lead_role"] if reads else None,
            })  # fmt: skip
        return out


@router.get("/rfx/{rfx_id}/files/{vendor_id}/{name}")
def get_file(rfx_id: str, vendor_id: str, name: str):
    """Serve a reply file exactly as received, including files carried inside an email."""
    with session_scope() as session:
        row = session.scalars(
            select(ReplyFileRow).where(ReplyFileRow.rfx_id == rfx_id, ReplyFileRow.vendor_id == vendor_id,
                                       ReplyFileRow.name == name)
        ).first()  # fmt: skip
        if row is None:
            raise HTTPException(404, "no such file")
        path, parent = row.path, row.parent
        if parent:
            parent_row = session.scalars(
                select(ReplyFileRow).where(ReplyFileRow.rfx_id == rfx_id, ReplyFileRow.vendor_id == vendor_id,
                                           ReplyFileRow.name == parent)
            ).first()  # fmt: skip
            path = parent_row.path if parent_row else None
    if not path or not (REPO_ROOT / path).is_file():
        raise HTTPException(404, "the file is no longer in the inbox")
    media = mimetypes.guess_type(name)[0] or "application/octet-stream"
    if parent:
        message = email.message_from_bytes(
            (REPO_ROOT / path).read_bytes(), policy=email.policy.default
        )
        for part in message.iter_attachments():
            if part.get_filename() == name:
                return Response(part.get_content(), media_type=media)
        raise HTTPException(404, "attachment not found in the email")
    return FileResponse(REPO_ROOT / path, media_type=media, filename=name,
                        content_disposition_type="inline")  # fmt: skip
