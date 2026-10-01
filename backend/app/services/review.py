"""Review queue actions: resolve, override, exclude, ask the vendor, reopen. All audited.

A review item is computed by the grid (it is a function of the readings). What is stored is
only what a person decided about it.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete

from app.db import session_scope
from app.models import CellDecisionRow, ReviewItemRow
from app.schemas import ReviewItem
from app.services import audit, grid


class ReviewError(Exception):
    pass


def _find(rfx_id: str, item_id: str) -> ReviewItem:
    item = next((i for i in grid.build(rfx_id).items if i.id == item_id), None)
    if item is None:
        raise ReviewError(f"review item {item_id} does not exist for {rfx_id}")
    return item


def _upsert(session, rfx_id: str, item: ReviewItem, status: str, resolution: dict | None) -> None:
    row = session.get(ReviewItemRow, item.id)
    if row is None:
        row = ReviewItemRow(
            id=item.id, rfx_id=rfx_id, vendor_id=item.vendor_id, kind=item.kind,
            lines=[ref.line_id for ref in item.cells],
        )  # fmt: skip
        session.add(row)
    row.status, row.resolution, row.updated_at = status, resolution, datetime.now(UTC)


def _where(item: ReviewItem) -> str:
    lines = [ref.line_id for ref in item.cells]
    if not lines:
        return item.vendor_name
    shown = ", ".join(lines) if len(lines) <= 4 else f"{len(lines)} lines"
    return f"{item.vendor_name} {shown}"


def resolve(
    rfx_id: str,
    item_id: str,
    *,
    actor: str,
    option_id: str | None = None,
    value: float | None = None,
    amount: float | None = None,
    reason: str | None = None,
) -> ReviewItem:
    """Resolve by choosing one of the system's options, or by typing a value (an override)."""
    item = _find(rfx_id, item_id)
    lines = [ref.line_id for ref in item.cells]
    now = datetime.now(UTC)
    with session_scope() as session:
        if value is not None:
            if len(lines) != 1:
                raise ReviewError("a typed value can only override a single cell")
            if not reason:
                raise ReviewError("an override needs a reason")
            session.merge(
                CellDecisionRow(
                    rfx_id=rfx_id, vendor_id=item.vendor_id, line_id=lines[0], action="override",
                    value=value, reason=reason, actor=actor, at=now,
                )
            )  # fmt: skip
            resolution = {"option_id": "override", "value": value}
            summary = (
                f"Override {_where(item)}: set to {grid.money(value)} per 1,000. Reason: {reason}"
            )
        elif option_id in ("exclude", "exclude_vendor"):
            for line_id in lines:
                session.merge(
                    CellDecisionRow(
                        rfx_id=rfx_id, vendor_id=item.vendor_id, line_id=line_id, action="exclude",
                        value=None, reason=reason or item.title, actor=actor, at=now,
                    )
                )  # fmt: skip
            resolution = {"option_id": option_id}
            summary = f"Excluded {_where(item)} ({item.title.lower()})"
        else:
            option = next((o for o in item.options if o.option_id == option_id), None)
            if option is None:
                raise ReviewError(f"'{option_id}' is not an option for this item")
            resolution = {"option_id": option_id, "label": option.label}
            if amount is not None:
                resolution["amount"] = amount
            summary = f"Resolved {_where(item)} ({item.title.lower()}): {option.label}"
        resolution |= {"actor": actor, "reason": reason, "at": now.isoformat()}
        _upsert(session, rfx_id, item, "resolved", resolution)
        audit.record(
            session, rfx_id, "review.resolve", summary, actor=actor,
            before={"status": item.status}, after={"status": "resolved", **resolution},
        )  # fmt: skip
    return _find(rfx_id, item_id)


def reopen(rfx_id: str, item_id: str, *, actor: str) -> ReviewItem:
    item = _find(rfx_id, item_id)
    with session_scope() as session:
        option = (item.resolution or {}).get("option_id")
        if option in ("override", "exclude", "exclude_vendor"):
            session.execute(
                delete(CellDecisionRow).where(
                    CellDecisionRow.rfx_id == rfx_id,
                    CellDecisionRow.vendor_id == item.vendor_id,
                    CellDecisionRow.line_id.in_([ref.line_id for ref in item.cells]),
                )
            )
        _upsert(session, rfx_id, item, "open", None)
        audit.record(
            session, rfx_id, "review.reopen", f"Reopened {_where(item)} ({item.title.lower()})",
            actor=actor, before={"status": item.status, "resolution": item.resolution},
            after={"status": "open"},
        )  # fmt: skip
    return _find(rfx_id, item_id)


def mark_asked(rfx_id: str, item_id: str, *, actor: str, outbox_path: str) -> ReviewItem:
    item = _find(rfx_id, item_id)
    with session_scope() as session:
        _upsert(session, rfx_id, item, "asked_vendor", {"actor": actor, "outbox": outbox_path})
        audit.record(
            session, rfx_id, "review.ask_vendor",
            f"Clarification drafted to {item.vendor_name} about {_where(item)}; saved to outbox, not sent",
            actor=actor, after={"outbox": outbox_path},
        )  # fmt: skip
    return _find(rfx_id, item_id)


def override_cell(
    rfx_id: str, vendor_id: str, line_id: str, *, actor: str, reason: str,
    value: float | None = None, exclude: bool = False,
) -> None:  # fmt: skip
    """Direct override from the provenance popover. Resolves any open item on that one cell."""
    if not reason.strip():
        raise ReviewError("an override needs a reason")
    if value is None and not exclude:
        raise ReviewError("give a value or exclude the cell")
    result = grid.build(rfx_id)
    cell = next(
        (line.cells[vendor_id] for line in result.grid.lines if line.line_id == line_id and vendor_id in line.cells),
        None,
    )  # fmt: skip
    if cell is None:
        raise ReviewError(f"no cell {vendor_id}/{line_id}")
    now = datetime.now(UTC)
    action = "exclude" if exclude else "override"
    vendor_name = next(v.name for v in result.grid.vendors if v.vendor_id == vendor_id)
    with session_scope() as session:
        session.merge(
            CellDecisionRow(
                rfx_id=rfx_id, vendor_id=vendor_id, line_id=line_id, action=action,
                value=None if exclude else value, reason=reason, actor=actor, at=now,
            )
        )  # fmt: skip
        for item in result.items:
            single = len(item.cells) == 1 and item.cells[0].line_id == line_id
            if (
                item.vendor_id == vendor_id
                and single
                and item.blocks_cells
                and item.status != "resolved"
            ):
                _upsert(
                    session, rfx_id, item, "resolved",
                    {"option_id": action, "value": value, "actor": actor, "reason": reason, "at": now.isoformat()},
                )  # fmt: skip
        was = cell.inr_per_base if cell.inr_per_base is not None else cell.display_inr
        what = "excluded" if exclude else f"set to {grid.money(value)} per 1,000"
        audit.record(
            session, rfx_id, f"cell.{action}",
            f"{action.capitalize()} {vendor_name} {line_id}: {what}. Reason: {reason}", actor=actor,
            before={"state": cell.state, "inr_per_base": was}, after={"action": action, "value": value},
        )  # fmt: skip


def revert_cell(rfx_id: str, vendor_id: str, line_id: str, *, actor: str) -> None:
    result = grid.build(rfx_id)
    with session_scope() as session:
        row = session.get(CellDecisionRow, (rfx_id, vendor_id, line_id))
        if row is None:
            raise ReviewError("this cell has no override to revert")
        before = {"action": row.action, "value": row.value, "reason": row.reason}
        session.delete(row)
        for item in result.items:
            option = (item.resolution or {}).get("option_id")
            touches = (
                any(ref.line_id == line_id for ref in item.cells) and item.vendor_id == vendor_id
            )
            if touches and option in ("override", "exclude") and len(item.cells) == 1:
                _upsert(session, rfx_id, item, "open", None)
        audit.record(
            session, rfx_id, "cell.revert", f"Reverted override on {vendor_id} {line_id}",
            actor=actor, before=before,
        )  # fmt: skip
