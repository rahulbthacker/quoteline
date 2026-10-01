"""Audit log. Append-only: every decision a person or the system makes is recorded here."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditEventRow

PERSONAS = {
    "buyer": "R. Thacker (category buyer)",
    "vp": "VP Supply Chain",
    "evaluator": "Technical evaluator",
    "admin": "Admin",
}


def actor_name(persona: str | None) -> str:
    return PERSONAS.get(persona or "buyer", persona or "buyer")


def record(
    session: Session,
    rfx_id: str,
    action: str,
    summary: str,
    *,
    actor: str = "system",
    before: dict | None = None,
    after: dict | None = None,
) -> None:
    session.add(
        AuditEventRow(
            rfx_id=rfx_id,
            actor_kind="system" if actor == "system" else "user",
            actor_id=actor,
            action=action,
            summary=summary,
            before=before,
            after=after,
        )
    )


def events(session: Session, rfx_id: str, limit: int = 200) -> list[dict]:
    rows = session.scalars(
        select(AuditEventRow)
        .where(AuditEventRow.rfx_id == rfx_id)
        .order_by(AuditEventRow.at.desc(), AuditEventRow.id.desc())
        .limit(limit)
    ).all()
    return [
        {
            "id": row.id,
            "actor_kind": row.actor_kind,
            "actor": row.actor_id,
            "action": row.action,
            "summary": row.summary,
            "before": row.before,
            "after": row.after,
            "at": row.at.isoformat(),
        }
        for row in rows
    ]
