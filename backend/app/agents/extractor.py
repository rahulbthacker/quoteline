"""Extraction agent: one quote file, one model, raw readings with provenance.

The same request goes to the primary and the secondary model; the ingest service runs them
in parallel and computes agreement. Nothing here converts a unit or a currency.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field

from app.agents.router import RoutingDecision
from app.config import Role
from app.llm import gateway, prompts
from app.llm.contracts import LLMRequest, LLMResult
from app.schemas import Condition, Extraction, ReadSpec, RFx, SourceRef
from app.schemas.reply import ConditionKind, UnitCode
from app.services import units
from app.services.parsers import ParsedDocument

PROMPT = "extractor_v1"


class RowOut(BaseModel):
    raw_description: str
    raw_value: float | None
    raw_unit: str | None
    unit_code: UnitCode
    raw_currency: str | None
    ply: int | None
    gsm: int | None
    dims_mm: list[int]
    print_colours: int | None
    rfx_reference: str | None
    locator: str
    snippet: str
    pack_note: str | None
    confidence: float
    alternatives: list[float]
    not_quoted: bool
    scope: Literal["item", "category"]
    scope_text: str | None
    notes: str | None


class ConditionOut(BaseModel):
    kind: ConditionKind
    text: str
    applies_to: str | None
    percent: float | None
    amount: float | None
    locator: str


class ExtractorOutput(BaseModel):
    rows: list[RowOut] = Field(description="One per priced or explicitly declined item")
    conditions: list[ConditionOut]
    currency_detected: str | None
    document_notes: str | None = Field(description="Anything a buyer should know about legibility")


def _squash(text: str) -> str:
    text = text.replace("\u2019", "'").replace("\u201c", '"').replace("\u201d", '"')
    return re.sub(r"\s+", " ", text).strip().lower()


def _numbers(text: str) -> list[float]:
    return [float(n.replace(",", "")) for n in re.findall(r"\d[\d,]*(?:\.\d+)?", text)]


def clean_locator(locator: str) -> str:
    return locator.strip().strip("[]").strip()


_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
CONTEXT_WINDOW = (600, 400)  # characters before and after the value
CONTEXT_COVERAGE = 0.8


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+(?:\.[0-9]+)?", _squash(text).replace(",", ""))


def _context_found(snippet: str, text: str, raw_value: float | None) -> bool:
    """Is the snippet's wording in the file, next to the number it was read from?

    Models quote table rows in different shapes (with pipes, with or without the number), so
    a literal substring test is too brittle. Instead: find every place the number occurs in
    the file and check that most of the snippet's words are within reach of one of them.
    """
    wanted = [t for t in _tokens(snippet) if len(t) > 1 or t.isdigit()]
    if not wanted:
        return False
    if raw_value is None:
        # No number to anchor on (a decline, a condition): the words must occur in sequence.
        source = _tokens(text)
        pairs = set(zip(source, source[1:], strict=False))
        sequence = _tokens(snippet)
        wanted_pairs = list(zip(sequence, sequence[1:], strict=False))
        if not wanted_pairs:
            return sequence[0] in source
        return sum(pair in pairs for pair in wanted_pairs) / len(wanted_pairs) >= 0.9
    for match in _NUMBER.finditer(text):
        if abs(float(match.group().replace(",", "")) - raw_value) > 1e-6:
            continue
        start = max(0, match.start() - CONTEXT_WINDOW[0])
        window = set(_tokens(text[start : match.end() + CONTEXT_WINDOW[1]]))
        if sum(t in window for t in wanted) / len(wanted) >= CONTEXT_COVERAGE:
            return True
    return False


def verify_source(
    document: ParsedDocument, locator: str, snippet: str, raw_value: float | None
) -> bool | None:
    """Does the file really say this, where the model says it does? Checked without a model.

    Workbook: the cited cell must hold exactly the value. Text: the number must occur in the
    file with the snippet's wording around it. Image: None, there is no text layer to check.
    """
    if document.format == "image" or (not document.text.strip() and not document.cells):
        return None
    if document.cells and raw_value is not None:
        refs = re.findall(r"([^!|,;]+?)!\$?([A-Z]{1,3})\$?(\d+)", locator)
        for sheet, column, row in refs:
            value = document.cells.get(f"{sheet.strip()}!{column}{row}")
            if isinstance(value, int | float) and abs(float(value) - raw_value) < 1e-6:
                return True
        return False
    if _squash(snippet) in _squash(document.text) and raw_value is None:
        return True
    return _context_found(snippet, document.text, raw_value)


def build_request(
    role: Role, rfx: RFx, document: ParsedDocument, routing: RoutingDecision
) -> LLMRequest:
    prompt = prompts.load(PROMPT)
    rfx_lines = "\n".join(
        f"- {line.line_id}: {line.description} (qty {line.qty:,} {line.uom})"
        for line in rfx.line_items
    )
    sections = "\n".join(f"- {s.locator}: {s.contains}" for s in routing.sections)
    use_text = bool(document.text.strip()) and not (routing.needs_vision and document.images)
    parts = [
        f"RFx {rfx.id}: {rfx.title}. The buyer asked for prices in {rfx.currency} per 1,000 pcs.",
        "For context only, the buyer's line list:",
        rfx_lines,
        "",
        f"Vendor file: {document.name} ({document.format})",
        f"Router's map of the file:\n{sections}" if sections else "",
    ]
    if document.images:
        labels = ", ".join(document.image_locators)
        parts.append(f"Attached images, in order: {labels}.")
    if use_text:
        parts += ["", "Extracted text with locators:", document.text]
    else:
        parts += [
            "",
            "There is no reliable text layer. Read the image. Cite rows of the image as locators.",
        ]
    return LLMRequest(
        role=role,
        prompt_version=prompt.version,
        system=prompt.text,
        text="\n".join(part for part in parts if part is not None),
        images=tuple(document.images),
        output_schema=ExtractorOutput,
        max_tokens=32000,
        effort="medium",
    )


def extract(
    role: Role,
    rfx: RFx,
    vendor_id: str,
    document: ParsedDocument,
    routing: RoutingDecision,
    *,
    run_id: str,
) -> tuple[list[Extraction], list[Condition], LLMResult]:
    """One live model call. Raises ModelCallError if the role's chain is exhausted."""
    request = build_request(role, rfx, document, routing)
    result = gateway.call(request, run_id=run_id, rfx_id=rfx.id)
    output: ExtractorOutput = result.parsed

    extractions = []
    for row in output.rows:
        unit_code, how = units.resolve_unit(row.raw_unit, row.unit_code)
        notes = [row.notes] if row.notes else []
        if how == "table" and row.unit_code != unit_code:
            notes.append(
                f"model labelled the unit {row.unit_code}; conversion table reads {unit_code}"
            )
        if how == "model":
            notes.append("unit wording not in the conversion table; model's label used")
        extractions.append(
            Extraction(
                vendor_id=vendor_id,
                raw_description=row.raw_description,
                raw_value=row.raw_value,
                raw_unit=row.raw_unit,
                unit_code=unit_code,
                raw_currency=units.currency_code(row.raw_currency or output.currency_detected),
                not_quoted=row.not_quoted,
                scope=row.scope,
                scope_text=row.scope_text,
                pack_note=row.pack_note,
                alternatives=[a for a in row.alternatives if a != row.raw_value],
                spec=ReadSpec(
                    ply=row.ply, gsm=row.gsm, dims_mm=row.dims_mm, print_colours=row.print_colours
                ),
                rfx_reference=row.rfx_reference,
                source_ref=SourceRef(
                    file=document.name,
                    locator=clean_locator(row.locator),
                    snippet=row.snippet,
                    snippet_verified=verify_source(
                        document, row.locator, row.snippet, row.raw_value
                    ),
                ),
                confidence=max(0.0, min(1.0, row.confidence)),
                model=result.served_model,
                prompt_version=request.prompt_version,
                notes="; ".join(notes) or None,
            )
        )
    conditions = [
        Condition(
            kind=item.kind,
            text=item.text,
            applies_to=item.applies_to,
            percent=item.percent,
            amount=item.amount,
            source_ref=SourceRef(
                file=document.name,
                locator=clean_locator(item.locator),
                snippet=item.text,
                snippet_verified=verify_source(document, item.locator, item.text, None),
            ),
            model=result.served_model,
            prompt_version=request.prompt_version,
        )
        for item in output.conditions
    ]
    return extractions, conditions, result
