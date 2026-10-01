"""Intake co-pilot: chat turns -> RFx draft. The draft always lands in an editable form."""

from __future__ import annotations

import json
import uuid

from pydantic import BaseModel

from app.llm import gateway, prompts
from app.llm.contracts import LLMRequest

PROMPT = "intake_v1"


class DraftLine(BaseModel):
    description: str
    ply: int | None
    gsm: int | None
    dims_mm: list[int]
    print: str | None
    qty: int | None
    uom: str
    last_year_price_inr: float | None


class DraftQuestion(BaseModel):
    text: str
    mandatory: bool


class DraftTerms(BaseModel):
    payment: str | None
    delivery: str | None
    validity_days: int | None


class RfxDraft(BaseModel):
    title: str
    category: str
    line_items: list[DraftLine]
    questionnaire: list[DraftQuestion]
    terms: DraftTerms
    assumptions: list[str]
    missing: list[str]


class IntakeTurn(BaseModel):
    reply: str
    draft: RfxDraft


def chat(messages: list[dict], draft: dict | None) -> dict:
    """One co-pilot turn. `messages` is the whole conversation, oldest first."""
    prompt = prompts.load(PROMPT)
    run_id = f"intake-{uuid.uuid4().hex[:8]}"
    conversation = "\n\n".join(f"{m['role'].upper()}: {m['content']}" for m in messages)
    text = (
        f"Current draft:\n{json.dumps(draft, ensure_ascii=False) if draft else 'empty'}\n\n"
        f"Conversation so far:\n{conversation}\n\nReturn the full updated draft and your reply."
    )
    result = gateway.call(
        LLMRequest(
            role="INTAKE", prompt_version=prompt.version, system=prompt.text, text=text,
            output_schema=IntakeTurn, max_tokens=32000, effort="medium",
        ),
        run_id=run_id,
    )  # fmt: skip
    turn: IntakeTurn = result.parsed
    return {
        "reply": turn.reply, "draft": turn.draft.model_dump(), "run_id": run_id,
        "model": result.served_model, "call_id": result.call_id,
    }  # fmt: skip
