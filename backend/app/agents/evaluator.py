"""Evaluation agent: questionnaire answers plus attachments -> per-question verdict with evidence.

The vendor result (Pass / Partial / Fail) is computed by rule from these verdicts, in code.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel

from app.llm import gateway, prompts
from app.llm.contracts import ImagePart, LLMRequest, LLMResult
from app.schemas import RFx

PROMPT = "evaluator_v1"


class AnswerOut(BaseModel):
    question_id: str
    status: Literal["pass", "fail", "unanswered", "answered"]
    answer: str | None
    evidence: str | None
    file: str | None
    locator: str | None
    reasoning: str


class EvaluatorOutput(BaseModel):
    answers: list[AnswerOut]


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def evaluate(
    rfx: RFx,
    vendor_name: str,
    documents: list[tuple[str, str]],
    images: list[tuple[str, ImagePart]],
    *,
    run_id: str,
) -> tuple[list[dict], LLMResult]:
    """`documents` are (file name, text with locators); `images` are files with no text layer."""
    prompt = prompts.load(PROMPT)
    questions = "\n".join(
        f"- {q.question_id} ({'MANDATORY' if q.mandatory else 'optional'}): {q.text}"
        for q in rfx.questionnaire
    )
    parts = [
        f"Vendor: {vendor_name}",
        f"RFx {rfx.id}: {rfx.title}",
        "",
        "Questionnaire:",
        questions,
    ]
    for name, text in documents:
        parts += ["", f"=== File: {name} ===", text]
    if images:
        parts += ["", "Attached images, in order: " + ", ".join(name for name, _ in images)]
    result = gateway.call(
        LLMRequest(
            # Anything that must be read from an image goes to the vision evaluator (Gemini).
            role="EVALUATOR_VISION" if images else "EVALUATOR",
            prompt_version=prompt.version,
            system=prompt.text,
            text="\n".join(parts),
            images=tuple(part for _, part in images),
            output_schema=EvaluatorOutput,
            max_tokens=16000,
            effort="medium",
        ),
        run_id=run_id,
        rfx_id=rfx.id,
    )
    output: EvaluatorOutput = result.parsed
    by_id = {answer.question_id: answer for answer in output.answers}
    haystack = _squash(" ".join(text for _, text in documents))
    answers = []
    for question in rfx.questionnaire:
        got = by_id.get(question.question_id)
        status = got.status if got else "unanswered"
        # Keep the vocabulary strict: mandatory questions are pass/fail/unanswered.
        if question.mandatory and status == "answered":
            status = "unanswered"
        if not question.mandatory and status in ("pass", "fail"):
            status = "answered"
        verified = None
        if got and got.evidence and documents:
            verified = _squash(got.evidence) in haystack
        answers.append(
            {
                "question_id": question.question_id,
                "mandatory": question.mandatory,
                "question": question.text,
                "status": status,
                "answer": got.answer if got else None,
                "evidence": got.evidence if got else None,
                "file": got.file if got else None,
                "locator": got.locator if got else None,
                "reasoning": got.reasoning
                if got
                else "the model returned no verdict for this question",
                "evidence_verified": verified,
            }
        )
    return answers, result
