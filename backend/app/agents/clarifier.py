"""Clarification agent: open review items -> one email draft to the vendor. Never sent."""

from __future__ import annotations

from pydantic import BaseModel

from app.llm import gateway, prompts
from app.llm.contracts import LLMRequest, LLMResult
from app.schemas import ReviewItem, RFx

PROMPT = "clarifier_v1"


class EmailDraft(BaseModel):
    subject: str
    body: str


def draft(
    rfx: RFx,
    vendor_name: str,
    contact: str | None,
    quote_file: str | None,
    items: list[ReviewItem],
    buyer: str,
    *,
    run_id: str,
) -> tuple[EmailDraft, LLMResult]:
    prompt = prompts.load(PROMPT)
    points = []
    for number, item in enumerate(items, start=1):
        lines = ", ".join(ref.line_id for ref in item.cells) or "whole quote"
        options = "\n".join(
            f"    - {option.label}" + (f" ({option.note})" if option.note else "")
            for option in item.options
        )
        points.append(
            f"Point {number} ({item.title}; RFx lines: {lines})\n"
            f"  Vendor wrote: {item.evidence or (item.source.snippet if item.source else 'not available')}\n"
            f"  Why unclear: {item.reason}\n"
            f"  Interpretations computed:\n{options or '    - none computed'}"
        )
    text = (
        f"RFx: {rfx.id}, {rfx.title}\nVendor: {vendor_name}\nVendor contact: {contact or 'not known'}\n"
        f"Vendor's document: {quote_file or 'their reply'}\nBuyer signing the email: {buyer}\n\n"
        + "\n\n".join(points)
    )
    result = gateway.call(
        LLMRequest(
            role="CLARIFIER", prompt_version=prompt.version, system=prompt.text, text=text,
            output_schema=EmailDraft, max_tokens=4000, effort="low",
        ),
        run_id=run_id,
        rfx_id=rfx.id,
    )  # fmt: skip
    return result.parsed, result
