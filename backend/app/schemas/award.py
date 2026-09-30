from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from app.schemas.common import Actor, LineId, Schema, VendorId


class ScenarioFilters(Schema):
    quality_pass_only: bool = False
    exclude_vendors: list[VendorId] = Field(default_factory=list)
    freight_inclusive: bool = False


class Scenario(Schema):
    id: str
    name: str
    filters: ScenarioFilters
    result: list[dict[str, Any]] = Field(default_factory=list)
    query_text: str | None = None
    totals: dict[str, float] = Field(default_factory=dict)


class Allocation(Schema):
    line_id: LineId
    vendor_id: VendorId
    inr_per_base: float
    extended_inr: float


class Exclusion(Schema):
    vendor_id: VendorId
    reason: str
    cost_of_rule_inr: float | None = None


class Approval(Schema):
    actor: Actor
    decision: Literal["approved", "changes_requested"]
    note: str | None = None
    at: datetime


class Award(Schema):
    id: str
    scenario_id: str
    allocations: list[Allocation]
    rules_applied: list[str]
    exclusions: list[Exclusion]
    open_items: list[str] = Field(description="Review item ids; any open item blocks approval")
    status: Literal["draft", "sent_for_approval", "approved", "changes_requested"] = "draft"
    approvals: list[Approval] = Field(default_factory=list)


class AuditEvent(Schema):
    """Immutable."""

    id: str
    actor: Actor
    action: str
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    at: datetime
