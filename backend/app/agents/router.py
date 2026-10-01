"""Ingestion router (Haiku): one file in, a routing decision out. It never extracts prices."""

from __future__ import annotations

import io
from typing import Literal

from PIL import Image
from pydantic import BaseModel, Field

from app.llm import gateway, prompts
from app.llm.contracts import ImagePart, LLMRequest
from app.schemas.reply import DocumentKind
from app.services.parsers import ParsedDocument

PROMPT = "router_v1"
ROUTER_IMAGE_EDGE = 1280  # routing needs the gist, not the digits


class Section(BaseModel):
    locator: str = Field(description="Sheet name, page number or part, as shown in the preview")
    contains: Literal["commercial", "questionnaire", "terms", "company_info", "other"]


class RoutingDecision(BaseModel):
    kind: DocumentKind
    needs_vision: bool
    sections: list[Section]
    language: str
    line_mentions: list[str]
    summary: str


def _thumbnail(part: ImagePart) -> ImagePart:
    image = Image.open(io.BytesIO(part.data))
    image.thumbnail((ROUTER_IMAGE_EDGE, ROUTER_IMAGE_EDGE))
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, "JPEG", quality=80)
    return ImagePart(media_type="image/jpeg", data=buffer.getvalue())


def route(document: ParsedDocument, *, run_id: str, rfx_id: str) -> RoutingDecision:
    prompt = prompts.load(PROMPT)
    text_chars = len(document.text.strip())
    lines = [
        f"File name: {document.name}",
        f"Detected type: {document.format}",
        f"Sections: {', '.join(document.sections) or 'none'}",
        f"Characters of extractable text: {text_chars}",
        "",
        "Preview of the extracted text:" if text_chars else "There is no extractable text.",
        document.preview,
    ]
    # Show the image only when there is no text to judge from.
    images = tuple(_thumbnail(part) for part in document.images[:1]) if not text_chars else ()
    result = gateway.call(
        LLMRequest(
            role="ROUTER",
            prompt_version=prompt.version,
            system=prompt.text,
            text="\n".join(lines),
            images=images,
            output_schema=RoutingDecision,
            max_tokens=2000,
        ),
        run_id=run_id,
        rfx_id=rfx_id,
    )
    decision: RoutingDecision = result.parsed
    if document.format == "image" or text_chars == 0:
        decision.needs_vision = True  # no text layer exists; this is not the model's call
    return decision
