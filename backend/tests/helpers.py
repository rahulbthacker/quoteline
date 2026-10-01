"""Test fixtures that stand in for a finished ingest, built from the golden set.

`seed_exact_reads` stores what two exact readers would have extracted from each vendor's
file. It lets the grid, review, award and analyst-executor logic be tested without model
calls. It exists only under tests/.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from app.db import session_scope
from app.eval import golden
from app.models import (
    ConditionRow,
    ExtractionCallRow,
    ExtractionRow,
    ReplyFileRow,
    RfxRow,
    VendorQualityRow,
    VendorRow,
)
from app.schemas import Condition, Extraction, LineMatch, RFx, SourceRef

DATA = Path(__file__).resolve().parents[2] / "data"
RFX_ID = "RFX-0147"
MODELS = {"primary": "claude-opus-5-5", "secondary": "gemini-3.1-pro-preview"}


def load_rfx() -> RFx:
    return RFx.model_validate_json((DATA / "rfx" / f"{RFX_ID}.json").read_text(encoding="utf-8"))


def _rows(vendor: str, model: str) -> list[Extraction]:
    truth = golden.load(vendor)
    rows = []
    for item in truth["lines"]:
        common = {
            "vendor_id": vendor, "line_id": item["line_id"], "model": model, "prompt_version": "t",
            "confidence": 0.95, "raw_description": item["vendor_description"],
            "source_ref": SourceRef(file=truth["files"][0], locator=item["locator"] or "-",
                                    snippet=item["raw_text"] or "-", snippet_verified=True),
            "match": LineMatch(line_id=item["line_id"], score=1.0, method="spec", reason="t"),
        }  # fmt: skip
        if item["raw_value"] is not None:
            unit = golden.UNIT_CODE[item["raw_unit"]]
            rows.append(
                Extraction(
                    raw_value=item["raw_value"], raw_unit=unit.replace("_", " "), unit_code=unit,
                    raw_currency=item["raw_currency"],
                    pack_note="packed 100 per bundle" if unit == "per_box" else None, **common,
                )
            )  # fmt: skip
        elif vendor == "kaveri" and not item["quoted"]:
            rows.append(Extraction(raw_currency="USD", not_quoted=True, **common))
    if (
        vendor == "northbox"
    ):  # the blotted digit: one reader declines, the other offers alternatives
        for row in rows:
            if row.line_id == "L05":
                if model == MODELS["primary"]:
                    row.raw_value, row.confidence, row.alternatives = None, 0.3, [3935.0, 3985.0]
                else:
                    row.confidence, row.alternatives = 0.5, [3985.0]
    return rows


def _conditions(vendor: str, model: str) -> list[Condition]:
    truth = golden.load(vendor)

    def make(kind, text, **extra):
        return Condition(
            kind=kind, text=text, model=model, prompt_version="t",
            source_ref=SourceRef(file=truth["files"][0], locator="-", snippet=text), **extra,
        )  # fmt: skip

    out = [make("freight", truth["freight"]["statement"])]
    if vendor == "sribalaji":
        out.append(
            make("discount", truth["discount"]["text"], percent=4.0, applies_to="lines above ₹1 L")
        )
    if vendor == "anand":
        out.append(make("same_as_last_year", "rest same as last year", applies_to="rest"))
    return out


def seed_exact_reads(with_quality: bool = True) -> RFx:
    rfx = load_rfx()
    vendors = json.loads((DATA / "rfx" / "vendors.json").read_text(encoding="utf-8"))
    with session_scope() as session:
        session.add(RfxRow(id=rfx.id, payload=rfx.model_dump(mode="json"), status="sent"))
        for position, vendor in enumerate(vendors):
            vendor_id = vendor["vendor_id"]
            truth = golden.load(vendor_id)
            session.add(VendorRow(rfx_id=rfx.id, position=position, **vendor))
            session.add(
                ReplyFileRow(
                    rfx_id=rfx.id, vendor_id=vendor_id, name=truth["files"][0], format=truth["format"],
                    kind="quote", needs_vision=truth["format"] == "image", sha256="t", run_id="t",
                    pages=3 if truth["format"] == "pdf" else None,
                    received_at=datetime.fromisoformat(truth["received_at"]).astimezone(UTC),
                )
            )  # fmt: skip
            for role, model in MODELS.items():
                session.add(
                    ExtractionCallRow(
                        rfx_id=rfx.id, vendor_id=vendor_id, file=truth["files"][0], role=role,
                        status="ok", model=model, agreement=1.0, run_id="t",
                    )
                )  # fmt: skip
                for row in _rows(vendor_id, model):
                    session.add(
                        ExtractionRow(
                            rfx_id=rfx.id, vendor_id=vendor_id, file=truth["files"][0], role=role,
                            line_id=row.line_id, payload=row.model_dump(mode="json"), run_id="t",
                        )
                    )  # fmt: skip
                for condition in _conditions(vendor_id, model):
                    session.add(
                        ConditionRow(
                            rfx_id=rfx.id, vendor_id=vendor_id, file=truth["files"][0], role=role,
                            payload=condition.model_dump(mode="json"), run_id="t",
                        )
                    )  # fmt: skip
            if with_quality:
                session.add(
                    VendorQualityRow(
                        rfx_id=rfx.id, vendor_id=vendor_id, overrides={}, model="t",
                        answers=[
                            {"question_id": q["question_id"], "mandatory": q["mandatory"],
                             "status": q["expected"], "answer": q["evidence"], "evidence": q["evidence"]}
                            for q in truth["questionnaire"]
                        ],
                    )
                )  # fmt: skip
    return rfx
