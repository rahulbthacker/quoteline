"""Line matcher: map a vendor's rows to RFx lines.

Deterministic first. Each (row, line) pair gets a score from specification similarity:
dimensions, item type, ply, GSM and print. Rows are assigned one-to-one, best score first.
A row that clears the accept threshold with a clear lead is matched by code alone. A row in
the grey zone goes to the router model for a tie-break with a stated reason. A row below the
floor is flagged unmatched. Rows that price a family ("the 5-ply") expand to every line of
that family.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

import yaml
from pydantic import BaseModel

from app.config import BACKEND_ROOT
from app.llm import gateway, prompts
from app.llm.contracts import LLMRequest, ModelCallError
from app.schemas import Extraction, LineItem, LineMatch, RFx
from app.services.units import threshold

CATEGORY_TEMPLATE = BACKEND_ROOT / "config" / "category_corrugated.yaml"
WEIGHTS = {"dims": 0.40, "type": 0.25, "ply": 0.15, "gsm": 0.10, "print": 0.10}
TYPE_MISMATCH_CAP = 0.50
REFERENCE_BONUS = 0.05
SAME_NUMBERS_OTHER_ORDER = 0.7
PROMPT = "line_matcher_v1"


@lru_cache
def _template() -> dict:
    return yaml.safe_load(CATEGORY_TEMPLATE.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class Features:
    dims: tuple[int, ...]
    item_type: str | None
    ply: int | None
    gsm: int | None
    print_colours: int | None


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().replace("×", "x").replace("-", " ")).strip()


def _lookup(text: str, table: dict) -> str | int | None:
    """Longest phrase in the vocabulary that appears in the text."""
    cleaned = _clean(text)
    best: tuple[int, str | int] | None = None
    for key, phrases in table.items():
        for phrase in phrases:
            needle = _clean(phrase)
            if re.search(rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])", cleaned):
                if best is None or len(needle) > best[0]:
                    best = (len(needle), key)
    return best[1] if best else None


def dims_from_text(text: str) -> tuple[int, ...]:
    cleaned = _clean(text)
    found: list[int] = []
    for group in re.findall(r"\d+(?:\s*x\s*\d+)+", cleaned):
        found += [int(n) for n in re.findall(r"\d+", group)]
    for pattern in (
        r"(\d+)\s*mm long",
        r"(\d+)\s*mm lengths?",
        r"(?<![a-z0-9])l\s+(\d+)(?![0-9x])",
    ):
        found += [int(n) for n in re.findall(pattern, cleaned)]
    return tuple(found)


def line_features(line: LineItem) -> Features:
    template = _template()
    dims = tuple(line.spec.dims_mm) if line.spec.dims_mm else dims_from_text(line.description)
    printed = _lookup(line.spec.print or "", template["print_words"]) if line.spec.print else 0
    return Features(
        dims=dims,
        item_type=_lookup(line.description, template["item_types"]),
        ply=line.spec.ply,
        gsm=line.spec.gsm,
        print_colours=printed,
    )


def row_features(row: Extraction) -> Features:
    template = _template()
    text = row.raw_description or ""
    dims = tuple(row.spec.dims_mm) or dims_from_text(text)
    printed = row.spec.print_colours
    if printed is None:
        printed = _lookup(text, template["print_words"])
    ply = row.spec.ply if row.spec.ply is not None else _lookup(text, template["ply_words"])
    return Features(
        dims=dims,
        item_type=_lookup(text, template["item_types"]),
        ply=ply,
        gsm=row.spec.gsm,
        print_colours=printed,
    )


def _same(a, b) -> float:
    if a is None or b is None:
        return 0.5  # not stated: neither evidence for nor against
    return 1.0 if a == b else 0.0


def _dims_score(a: tuple[int, ...], b: tuple[int, ...]) -> float:
    if not a or not b:
        return 0.5
    if a == b:
        return 1.0
    if sorted(a) == sorted(b):
        # Same numbers in a different order is weaker evidence: 600x450x400 is not 600x400x450.
        return SAME_NUMBERS_OTHER_ORDER
    overlap = sum((Counter(a) & Counter(b)).values())
    return overlap / max(len(a), len(b))


def score(row: Features, line: Features) -> float:
    parts = {
        "dims": _dims_score(row.dims, line.dims),
        "type": _same(row.item_type, line.item_type),
        "ply": _same(row.ply, line.ply),
        "gsm": _same(row.gsm, line.gsm),
        "print": _same(row.print_colours, line.print_colours),
    }
    total = sum(WEIGHTS[name] * value for name, value in parts.items())
    if parts["type"] == 0.0:
        total = min(total, TYPE_MISMATCH_CAP)  # a tray is never a box, whatever the size
    return round(total, 4)


def _reference_line(row: Extraction, rfx: RFx) -> str | None:
    if not row.rfx_reference:
        return None
    digits = re.findall(r"\d+", row.rfx_reference)
    if not digits:
        return None
    shown = re.findall(r"\d+", row.source_ref.snippet.split("|")[0][:12])
    if not shown or int(shown[0]) != int(digits[0]):
        return None  # the model supplied a number the row itself does not lead with
    candidate = f"L{int(digits[0]):02d}"
    return candidate if any(line.line_id == candidate for line in rfx.line_items) else None


def expand_category(row: Extraction, rfx: RFx) -> list[Extraction]:
    """A rate quoted for a family ("the 5-ply") applies to every RFx line of that family."""
    text = f"{row.scope_text or ''} {row.raw_description or ''}"
    ply = row.spec.ply if row.spec.ply is not None else _lookup(text, _template()["ply_words"])
    if ply is None:
        unmatched = row.model_copy(deep=True)
        unmatched.match = LineMatch(
            line_id=None, score=0.0, method="unmatched",
            reason=f"could not tell which lines '{row.scope_text or row.raw_description}' covers",
        )  # fmt: skip
        return [unmatched]
    expanded = []
    for line in rfx.line_items:
        if line.spec.ply == ply:
            copy = row.model_copy(deep=True)
            copy.line_id = line.line_id
            copy.match = LineMatch(
                line_id=line.line_id, score=1.0, method="scope",
                reason=f"'{row.scope_text or row.raw_description}' covers every {ply}-ply line",
            )  # fmt: skip
            expanded.append(copy)
    return expanded


class TieBreak(BaseModel):
    choice: str  # an RFx line id, or "none"
    reason: str


def _tie_break(
    row: Extraction, candidates: list[tuple[LineItem, float]], *, run_id: str, rfx_id: str
) -> TieBreak | None:
    prompt = prompts.load(PROMPT)
    listing = "\n".join(
        f"- {line.line_id}: {line.description} (deterministic score {value:.2f})"
        for line, value in candidates
    )
    text = (
        f"Vendor row: {row.raw_description}\n"
        f"Read specification: ply={row.spec.ply}, gsm={row.spec.gsm}, dims_mm={row.spec.dims_mm}, "
        f"print_colours={row.spec.print_colours}\n"
        f"Source: {row.source_ref.locator}: {row.source_ref.snippet}\n\n"
        f"Candidate RFx lines:\n{listing}\n\n"
        "Answer with the chosen line id, or none."
    )
    try:
        result = gateway.call(
            LLMRequest(
                role="ROUTER", prompt_version=prompt.version, system=prompt.text, text=text,
                output_schema=TieBreak, max_tokens=1000,
            ),
            run_id=run_id,
            rfx_id=rfx_id,
        )  # fmt: skip
    except ModelCallError:
        return None
    return result.parsed


MatchMode = Literal["deterministic", "with_tiebreak"]


def match_rows(
    rows: list[Extraction], rfx: RFx, *, run_id: str, mode: MatchMode = "with_tiebreak"
) -> list[Extraction]:
    """Return rows with `line_id` and `match` filled. Category rows are expanded."""
    accept, margin, floor = (
        threshold("match_accept"),
        threshold("match_margin"),
        threshold("match_floor"),
    )
    lines = {line.line_id: line for line in rfx.line_items}
    features = {line_id: line_features(line) for line_id, line in lines.items()}

    out: list[Extraction] = []
    items = []
    for row in rows:
        if row.scope == "category":
            out += expand_category(row, rfx)
        else:
            items.append(row)

    scored = []
    for row in items:
        row_feat = row_features(row)
        reference = _reference_line(row, rfx)
        table = {}
        for line_id, feat in features.items():
            value = score(row_feat, feat)
            if reference == line_id and value >= floor:
                value = min(1.0, value + REFERENCE_BONUS)
            table[line_id] = value
        scored.append((row, table, reference))

    taken: set[str] = set()
    for row, table, reference in sorted(scored, key=lambda item: -max(item[1].values())):
        ranked = sorted(
            ((line_id, value) for line_id, value in table.items() if line_id not in taken),
            key=lambda pair: -pair[1],
        )
        matched = row.model_copy(deep=True)
        best_id, best = ranked[0]
        second_id, second = ranked[1] if len(ranked) > 1 else (None, 0.0)
        if best >= accept and best - second >= margin:
            method = "spec+reference" if reference == best_id else "spec"
            matched.match = LineMatch(
                line_id=best_id, score=best, method=method, runner_up=second_id,
                reason=f"specification match {best:.2f}; next best {second_id} at {second:.2f}",
            )  # fmt: skip
        elif best >= floor and mode == "with_tiebreak":
            candidates = [(lines[line_id], value) for line_id, value in ranked[:3]]
            verdict = _tie_break(row, candidates, run_id=run_id, rfx_id=rfx.id)
            valid = {line.line_id for line, _ in candidates}
            if verdict and verdict.choice in valid:
                matched.match = LineMatch(
                    line_id=verdict.choice, score=table[verdict.choice], method="model_tiebreak",
                    runner_up=second_id, reason=verdict.reason,
                )  # fmt: skip
            else:
                why = verdict.reason if verdict else "tie-break model unavailable"
                matched.match = LineMatch(
                    line_id=None, score=best, method="unmatched", runner_up=best_id, reason=why
                )
        else:
            matched.match = LineMatch(
                line_id=None, score=best, method="unmatched", runner_up=best_id,
                reason=f"best specification match {best_id} scores only {best:.2f}",
            )  # fmt: skip
        matched.line_id = matched.match.line_id
        if matched.line_id:
            taken.add(matched.line_id)
        out.append(matched)
    return out
