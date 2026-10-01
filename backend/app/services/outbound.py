"""Outbound mail: the RFx to each vendor, and clarification drafts. Transport is stubbed."""

from __future__ import annotations

import io
import uuid
from datetime import UTC, datetime

from openpyxl import Workbook
from openpyxl.styles import Font
from sqlalchemy import select

from app.agents import clarifier
from app.config import REPO_ROOT
from app.db import session_scope
from app.llm.contracts import ModelCallError
from app.models import OutboxRow, RfxRow, VendorRow
from app.schemas import RFx
from app.services import audit, grid, mail_stub, review

BUYER = {
    "name": "Rahul Thacker",
    "title": "Category Buyer, Packaging",
    "company": "Sahyadri Foods Pvt Ltd",
    "email": "rahul.thacker@sahyadrifoods.example",
}
SENDER = f"{BUYER['name']} <{BUYER['email']}>"


def _stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S")


def quote_template(rfx: RFx) -> bytes:
    """The template vendors are asked to fill in. Most of them will ignore it."""
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Quote"
    sheet.append([f"{rfx.id}: {rfx.title}"])
    sheet.append(["Please quote in INR per 1,000 pcs, ex-GST, and state freight separately."])
    sheet.append([])
    sheet.append(["Line", "Description", "Annual qty", "UOM", "Rate (INR per 1,000)", "Remarks"])
    for line in rfx.line_items:
        sheet.append([line.line_id, line.description, line.qty, line.uom, None, None])
    for cell in sheet[4]:
        cell.font = Font(bold=True)
    sheet.column_dimensions["B"].width = 70
    questions = workbook.create_sheet("Questionnaire")
    questions.append(["No.", "Mandatory", "Question", "Your answer"])
    for question in rfx.questionnaire:
        questions.append(
            [question.question_id, "Yes" if question.mandatory else "No", question.text, None]
        )
    questions.column_dimensions["C"].width = 110
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def rfx_email_body(rfx: RFx, contact: str | None) -> str:
    lines = "\n".join(
        f"  {line.line_id}  {line.description}  |  {line.qty:,} {line.uom}"
        for line in rfx.line_items
    )
    questions = "\n".join(
        f"  {q.question_id}{' (mandatory)' if q.mandatory else ''}: {q.text}"
        for q in rfx.questionnaire
    )
    return (
        f"Dear {contact or 'Sir/Madam'},\n\n"
        f"{BUYER['company']} invites your quotation for {rfx.title} (reference {rfx.id}).\n\n"
        f"Please quote in {rfx.currency} per 1,000 pcs for the {len(rfx.line_items)} items below, "
        "using the attached template if you can.\n\n"
        f"Items and annual quantities:\n{lines}\n\n"
        f"Supplier questionnaire:\n{questions}\n\n"
        f"Terms: payment {rfx.terms.payment}; delivery {rfx.terms.delivery}; "
        f"offer validity {rfx.terms.validity_days} days. {rfx.freight_policy} {rfx.tax_policy}\n\n"
        f"Regards,\n{BUYER['name']}\n{BUYER['title']}, {BUYER['company']}\n"
    )


def send_rfx(rfx_id: str, *, actor: str) -> list[dict]:
    """Write one RFx email per vendor to the outbox and log it."""
    with session_scope() as session:
        row = session.get(RfxRow, rfx_id)
        if row is None:
            raise KeyError(rfx_id)
        rfx = RFx.model_validate(row.payload)
        vendors = session.scalars(
            select(VendorRow).where(VendorRow.rfx_id == rfx_id).order_by(VendorRow.position)
        ).all()
        template = quote_template(rfx)
        subject = f"{rfx.id} {rfx.title}: request for quotation"
        sent = []
        for vendor in vendors:
            body = rfx_email_body(rfx, vendor.contact)
            path = mail_stub.write_outbox(
                f"{_stamp()}_rfx_{vendor.vendor_id}.eml", sender=SENDER,
                to=f"{vendor.contact} <{vendor.email}>", subject=subject, body=body,
                message_id=f"<{rfx.id.lower()}-{vendor.vendor_id}@quoteline.local>",
                attachments=[(f"{rfx.id}_quote_template.xlsx", template, "application",
                              "vnd.openxmlformats-officedocument.spreadsheetml.sheet")],
            )  # fmt: skip
            relative = str(path.relative_to(REPO_ROOT))
            session.add(
                OutboxRow(
                    rfx_id=rfx_id, vendor_id=vendor.vendor_id, kind="rfx", to_address=vendor.email,
                    subject=subject, body=body, path=relative, status="sent",
                )
            )  # fmt: skip
            sent.append({"vendor_id": vendor.vendor_id, "to": vendor.email, "path": relative})
        row.status = "sent"
        audit.record(
            session, rfx_id, "rfx.send",
            f"RFx sent to {len(sent)} vendors by email (stubbed transport: written to mail/outbox)",
            actor=actor, after={"vendors": [item["vendor_id"] for item in sent]},
        )  # fmt: skip
    return sent


def ask_vendor(rfx_id: str, item_ids: list[str], *, actor: str) -> dict:
    """Draft one clarification email covering the given items for one vendor. Not sent."""
    result = grid.build(rfx_id)
    items = [item for item in result.items if item.id in item_ids]
    if not items:
        raise review.ReviewError("no such review items")
    vendor_ids = {item.vendor_id for item in items}
    if len(vendor_ids) != 1:
        raise review.ReviewError("one clarification email goes to one vendor")
    vendor_id = vendor_ids.pop()
    vendor = next(v for v in result.grid.vendors if v.vendor_id == vendor_id)
    with session_scope() as session:
        row = session.get(VendorRow, (rfx_id, vendor_id))
        contact, address = row.contact, row.email
    run_id = f"clarify-{uuid.uuid4().hex[:8]}"
    try:
        email, call = clarifier.draft(
            result.rfx, vendor.name, contact, vendor.file, items,
            f"{BUYER['name']}, {BUYER['title']}, {BUYER['company']}", run_id=run_id,
        )  # fmt: skip
    except ModelCallError as exc:
        raise review.ReviewError(f"the clarification could not be drafted: {exc}") from exc
    path = mail_stub.write_outbox(
        f"{_stamp()}_clarification_{vendor_id}.eml", sender=SENDER,
        to=f"{contact} <{address}>", subject=email.subject, body=email.body,
    )  # fmt: skip
    relative = str(path.relative_to(REPO_ROOT))
    with session_scope() as session:
        session.add(
            OutboxRow(
                rfx_id=rfx_id, vendor_id=vendor_id, kind="clarification", to_address=address,
                subject=email.subject, body=email.body, path=relative, status="draft",
                review_item_id=",".join(item.id for item in items),
            )
        )  # fmt: skip
    for item in items:
        review.mark_asked(rfx_id, item.id, actor=actor, outbox_path=relative)
    return {
        "vendor_id": vendor_id, "to": address, "subject": email.subject, "body": email.body,
        "path": relative, "status": "draft", "model": call.served_model, "call_id": call.call_id,
    }  # fmt: skip


def outbox(rfx_id: str) -> list[dict]:
    with session_scope() as session:
        rows = session.scalars(
            select(OutboxRow).where(OutboxRow.rfx_id == rfx_id).order_by(OutboxRow.id.desc())
        ).all()
        return [
            {
                "id": row.id, "vendor_id": row.vendor_id, "kind": row.kind, "to": row.to_address,
                "subject": row.subject, "body": row.body, "path": row.path, "status": row.status,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ]  # fmt: skip
