"""Settings, traces and the eval report."""

from __future__ import annotations

import json
from typing import Annotated

import yaml
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from app.api.deps import persona, require
from app.config import ROLES, VAR_DIR, get_settings
from app.db import session_scope
from app.llm import prompts
from app.models import TraceRow
from app.schemas import Trace
from app.services import audit, units

router = APIRouter()
Who = Annotated[str, Depends(persona)]
EVAL_REPORT = VAR_DIR / "eval_report.json"


@router.get("/health")
def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "roles": {role: [str(spec) for spec in settings.chain(role)] for role in ROLES},
        "keys": {
            provider: bool(settings.api_key(provider)) for provider in ("anthropic", "gemini")
        },
    }


@router.get("/traces", response_model=list[Trace])
def traces(
    rfx_id: str | None = None, run_id: str | None = None, limit: int = 500
) -> list[TraceRow]:
    with session_scope() as session:
        query = select(TraceRow)
        if rfx_id:
            query = query.where(TraceRow.rfx_id == rfx_id)
        if run_id:
            query = query.where(TraceRow.parent_run_id == run_id)
        rows = session.scalars(query.order_by(TraceRow.created_at.desc()).limit(limit)).all()
        session.expunge_all()
        return list(rows)


@router.get("/rfx/{rfx_id}/traces", response_model=list[Trace])
def rfx_traces(rfx_id: str) -> list[TraceRow]:
    return traces(rfx_id=rfx_id)


@router.get("/prompts")
def list_prompts() -> list[dict]:
    out = []
    for path in sorted(prompts.PROMPT_DIR.glob("*.md")):
        prompt = prompts.load(path.stem)
        out.append({"version": prompt.version, "purpose": prompt.purpose, "text": prompt.text})
    return out


@router.get("/settings/conversions")
def get_conversions() -> dict:
    return units.conversion_table()


@router.put("/settings/conversions")
def put_conversions(body: dict, who: Who) -> dict:
    """Replace the conversion table. Validated, written to the YAML file, effective at once."""
    actor = require(who, "admin")
    try:
        for code, spec in body["units"].items():
            assert isinstance(spec["aliases"], list) and spec["label"], code
            rules = spec.get("interpretations") or [{"to_base": spec["to_base"]}]
            for rule in rules:
                assert rule["to_base"]["op"] in ("multiply", "weight", "pack"), code
                assert float(rule["to_base"]["factor"]) > 0, code
        for name, value in body["thresholds"].items():
            assert float(value) >= 0, name
        assert body["currencies"] and body["base_unit"]
    except (KeyError, AssertionError, TypeError, ValueError) as exc:
        raise HTTPException(422, f"invalid conversion table: {exc!r}") from exc
    before = units.conversion_table()
    header = "# Conversion table. Admin-editable (Settings screen). All arithmetic that reaches the grid\n# uses these factors; no model output is ever used as a factor.\n"
    units.CONVERSION_TABLE.write_text(
        header + yaml.safe_dump(body, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    units.conversion_table.cache_clear()
    with session_scope() as session:
        audit.record(session, "settings", "settings.conversions", "Conversion table edited", actor=actor,
                     before={"thresholds": before["thresholds"]}, after={"thresholds": body["thresholds"]})  # fmt: skip
    return units.conversion_table()


@router.get("/eval/report")
def eval_report() -> dict:
    if not EVAL_REPORT.is_file():
        raise HTTPException(404, "No eval report yet. Run `make eval`.")
    return json.loads(EVAL_REPORT.read_text(encoding="utf-8"))
