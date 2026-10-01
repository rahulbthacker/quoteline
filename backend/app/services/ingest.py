"""Ingestion: inbox files -> routed, read by two models, matched to RFx lines, stored.

Every value written here came from a live model call over the file in the inbox. A failed
read is stored as a failure (status model_error) so the grid can flag it; it is never
replaced with a default.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import delete, select

from app.agents import extractor, router
from app.agents.router import RoutingDecision
from app.config import REPO_ROOT
from app.db import init_db, session_scope
from app.llm.contracts import ModelCallError
from app.models import (
    ConditionRow,
    ExtractionCallRow,
    ExtractionRow,
    ReplyFileRow,
    RfxRow,
    TraceRow,
    VendorRow,
)
from app.schemas import Condition, Extraction, RFx
from app.services import line_matcher, mail_stub, parsers
from app.services.parsers import ParsedDocument
from app.services.validation import readings_agree

SEED_RFX = REPO_ROOT / "data" / "rfx"
ROLES = {"primary": "EXTRACT_PRIMARY", "secondary": "EXTRACT_SECONDARY"}
MAX_WORKERS = 6


@dataclass
class InboundFile:
    vendor_id: str
    document: ParsedDocument
    sha256: str
    path: Path | None
    parent: str | None
    received_at: object
    routing: RoutingDecision | None = None
    routing_error: str | None = None


@dataclass
class FileRead:
    """The outcome of one model reading one quote file."""

    role: str
    rows: list[Extraction] = field(default_factory=list)
    conditions: list[Condition] = field(default_factory=list)
    model: str | None = None
    call_id: str | None = None
    error: str | None = None


def load_seed_rfx() -> RFx:
    """Put the seeded RFx and its vendor list into the database (idempotent)."""
    init_db()
    files = sorted(SEED_RFX.glob("RFX-*.json"))
    payload = json.loads(files[0].read_text(encoding="utf-8"))
    rfx = RFx.model_validate(payload)
    vendors = json.loads((SEED_RFX / "vendors.json").read_text(encoding="utf-8"))
    with session_scope() as session:
        if session.get(RfxRow, rfx.id) is None:
            session.add(RfxRow(id=rfx.id, payload=payload, status="sent"))
        for vendor in vendors:
            if session.get(VendorRow, (rfx.id, vendor["vendor_id"])) is None:
                session.add(VendorRow(rfx_id=rfx.id, **vendor))
    return rfx


def get_rfx(rfx_id: str) -> RFx:
    with session_scope() as session:
        row = session.get(RfxRow, rfx_id)
        if row is None:
            raise KeyError(rfx_id)
        return RFx.model_validate(row.payload)


def _collect(vendor_id: str, path: Path) -> list[InboundFile]:
    data = path.read_bytes()
    document = parsers.parse(path.name, data)
    received = mail_stub.received_at(path)
    found = [
        InboundFile(vendor_id, document, hashlib.sha256(data).hexdigest(), path, None, received)
    ]
    for child_name, payload in document.children:  # files carried inside an email
        child = parsers.parse(child_name, payload)
        found.append(
            InboundFile(
                vendor_id, child, hashlib.sha256(payload).hexdigest(), None, path.name, received
            )
        )
    return found


def _route(item: InboundFile, run_id: str, rfx_id: str) -> None:
    try:
        item.routing = router.route(item.document, run_id=run_id, rfx_id=rfx_id)
    except ModelCallError as exc:
        item.routing_error = str(exc)


def _read(role: str, rfx: RFx, item: InboundFile, run_id: str) -> FileRead:
    try:
        rows, conditions, result = extractor.extract(
            ROLES[role], rfx, item.vendor_id, item.document, item.routing, run_id=run_id
        )
    except ModelCallError as exc:
        return FileRead(role=role, error=str(exc))
    matched = line_matcher.match_rows(rows, rfx, run_id=run_id)
    return FileRead(role, matched, conditions, result.served_model, result.call_id)


def agreement_score(primary: FileRead, secondary: FileRead) -> tuple[float | None, dict[str, bool]]:
    """Share of lines, read by at least one model, on which the two readings agree."""
    if primary.error or secondary.error:
        return None, {}
    p = {row.line_id: row for row in primary.rows if row.line_id}
    s = {row.line_id: row for row in secondary.rows if row.line_id}
    per_line = {
        line_id: line_id in p and line_id in s and readings_agree(p[line_id], s[line_id])
        for line_id in sorted(set(p) | set(s))
    }
    if not per_line:
        return None, {}
    return round(sum(per_line.values()) / len(per_line), 4), per_line


def ingest(rfx_id: str, only_vendors: list[str] | None = None) -> dict:
    """Read everything in the inbox for this RFx. Returns a summary for the caller to print."""
    init_db()
    rfx = get_rfx(rfx_id)
    run_id = f"ingest-{uuid.uuid4().hex[:8]}"
    inbox = mail_stub.scan_inbox()
    if only_vendors:
        inbox = {vendor: files for vendor, files in inbox.items() if vendor in only_vendors}

    items: list[InboundFile] = []
    for vendor_id, paths in inbox.items():
        for path in paths:
            items += _collect(vendor_id, path)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        list(pool.map(lambda item: _route(item, run_id, rfx_id), items))

    quotes = [item for item in items if item.routing and item.routing.kind == "quote"]
    jobs = [(role, item) for item in quotes for role in ROLES]
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        reads = list(pool.map(lambda job: _read(job[0], rfx, job[1], run_id), jobs))
    by_file: dict[tuple[str, str], dict[str, FileRead]] = {}
    for (role, item), read in zip(jobs, reads, strict=True):
        by_file.setdefault((item.vendor_id, item.document.name), {})[role] = read

    summary = {"run_id": run_id, "rfx_id": rfx_id, "vendors": {}}
    with session_scope() as session:
        vendors = list(inbox)
        for table in (ReplyFileRow, ExtractionCallRow, ExtractionRow, ConditionRow):
            session.execute(
                delete(table).where(table.rfx_id == rfx_id, table.vendor_id.in_(vendors))
            )

        for item in items:
            routing = item.routing
            session.add(
                ReplyFileRow(
                    rfx_id=rfx_id,
                    vendor_id=item.vendor_id,
                    name=item.document.name,
                    path=str(item.path.relative_to(REPO_ROOT)) if item.path else None,
                    parent=item.parent,
                    format=item.document.format,
                    kind=routing.kind if routing else "other",
                    needs_vision=bool(routing and routing.needs_vision),
                    pages=item.document.pages,
                    sha256=item.sha256,
                    summary=routing.summary if routing else f"routing failed: {item.routing_error}",
                    routing=routing.model_dump() if routing else None,
                    parsed_text=item.document.text,
                    received_at=item.received_at,
                    run_id=run_id,
                )
            )
            entry = summary["vendors"].setdefault(item.vendor_id, {"files": [], "quotes": {}})
            entry["files"].append(
                {"name": item.document.name, "kind": routing.kind if routing else "unrouted"}
            )

        for (vendor_id, file_name), pair in by_file.items():
            score, _ = agreement_score(pair["primary"], pair["secondary"])
            for role, read in pair.items():
                session.add(
                    ExtractionCallRow(
                        rfx_id=rfx_id, vendor_id=vendor_id, file=file_name, role=role,
                        status="model_error" if read.error else "ok", error=read.error,
                        model=read.model, call_id=read.call_id, agreement=score, run_id=run_id,
                    )
                )  # fmt: skip
                if read.call_id and score is not None:
                    trace = session.get(TraceRow, read.call_id)
                    if trace:
                        trace.agreement = score
                for row in read.rows:
                    session.add(
                        ExtractionRow(
                            rfx_id=rfx_id, vendor_id=vendor_id, file=file_name, role=role,
                            line_id=row.line_id, payload=row.model_dump(mode="json"), run_id=run_id,
                        )
                    )  # fmt: skip
                for condition in read.conditions:
                    session.add(
                        ConditionRow(
                            rfx_id=rfx_id, vendor_id=vendor_id, file=file_name, role=role,
                            payload=condition.model_dump(mode="json"), run_id=run_id,
                        )
                    )  # fmt: skip
            summary["vendors"][vendor_id]["quotes"][file_name] = {
                "agreement": score,
                **{
                    role: {
                        "model": read.model,
                        "rows": len(read.rows),
                        "matched": sum(1 for row in read.rows if row.line_id),
                        "conditions": len(read.conditions),
                        "error": read.error,
                    }
                    for role, read in pair.items()
                },
            }

        traces = session.scalars(select(TraceRow).where(TraceRow.parent_run_id == run_id)).all()
        summary["calls"] = len(traces)
        summary["failed_calls"] = sum(1 for t in traces if t.status != "ok")
        summary["cost_inr"] = round(sum(t.cost_inr or 0 for t in traces), 2)
        summary["latency_s"] = round(sum(t.latency_ms for t in traces) / 1000, 1)
    return summary


def load_vendor_reads(rfx_id: str, vendor_id: str) -> dict:
    """Everything stored for one vendor: per-role rows and conditions, call status, lead role."""
    with session_scope() as session:
        calls = session.scalars(
            select(ExtractionCallRow).where(
                ExtractionCallRow.rfx_id == rfx_id, ExtractionCallRow.vendor_id == vendor_id
            )
        ).all()
        rows = session.scalars(
            select(ExtractionRow).where(
                ExtractionRow.rfx_id == rfx_id, ExtractionRow.vendor_id == vendor_id
            )
        ).all()
        conditions = session.scalars(
            select(ConditionRow).where(
                ConditionRow.rfx_id == rfx_id, ConditionRow.vendor_id == vendor_id
            )
        ).all()
        files = session.scalars(
            select(ReplyFileRow).where(
                ReplyFileRow.rfx_id == rfx_id, ReplyFileRow.vendor_id == vendor_id
            )
        ).all()
        out: dict = {"errors": {}, "agreement": None, "files": files, "models": {}}
        for role in ROLES:
            call = next((c for c in calls if c.role == role), None)
            failed = call is None or call.status != "ok"
            if call and call.status != "ok":
                out["errors"][role] = call.error or "failed"
            if call:
                out["agreement"] = call.agreement
                out["models"][role] = call.model
            out[role] = None if failed else [
                Extraction.model_validate(r.payload) for r in rows if r.role == role
            ]  # fmt: skip
            out[f"{role}_conditions"] = [
                Condition.model_validate(c.payload) for c in conditions if c.role == role
            ]
        quote = next((f for f in files if f.kind == "quote"), None)
        # Image and photo reads lead with the secondary (Gemini); text reads with the primary.
        out["lead_role"] = "secondary" if quote is not None and quote.needs_vision else "primary"
        out["has_reply"] = bool(files)
        return out
