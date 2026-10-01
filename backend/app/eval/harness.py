"""Score stored extractions against the golden set.

Per vendor, per model, per field: was the row matched to the right RFx line, and are the raw
value, unit and currency exactly what the file says. Then: did validation raise the flags the
dataset was built to provoke, and did it raise any that are not real problems.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.eval import golden
from app.schemas import Extraction, RFx
from app.services import ingest
from app.services.validation import Flag, assess_vendor

FIELDS = ("line", "value", "unit", "currency")
VALUE_TOLERANCE = 0.005


@dataclass
class ModelScore:
    model: str | None
    correct: dict[str, int] = field(default_factory=lambda: dict.fromkeys(FIELDS, 0))
    total: int = 0
    errors: list[str] = field(default_factory=list)
    spurious: list[str] = field(default_factory=list)  # prices reported for lines not quoted

    def accuracy(self, name: str) -> float | None:
        return self.correct[name] / self.total if self.total else None

    @property
    def perfect(self) -> bool:
        return self.total > 0 and not self.errors and not self.spurious


@dataclass
class VendorReport:
    vendor_id: str
    scores: dict[str, ModelScore]
    agreement: float | None
    flags: list[Flag]
    expected_met: list[str]
    expected_missed: list[str]
    unexpected: list[str]
    states_wrong: list[str]


def score_model(vendor_id: str, rows: list[Extraction] | None, model: str | None) -> ModelScore:
    truth = golden.load(vendor_id)
    score = ModelScore(model=model)
    if rows is None:
        score.errors.append("extraction failed")
        return score
    by_line: dict[str, Extraction] = {}
    for row in rows:
        if row.line_id:
            by_line.setdefault(row.line_id, row)
    for item in truth["lines"]:
        line_id = item["line_id"]
        got = by_line.get(line_id)
        if item["raw_value"] is None:  # not quoted, or covered only by a carry-forward statement
            if got is not None and got.raw_value is not None and not got.not_quoted:
                score.spurious.append(
                    f"{line_id}: read {got.raw_value} but the vendor quotes nothing"
                )
            continue
        score.total += 1
        if got is None:
            score.errors.append(f"{line_id}: no row matched (expected {item['raw_text']})")
            continue
        score.correct["line"] += 1
        checks = {
            "value": got.raw_value is not None
            and abs(got.raw_value - item["raw_value"]) <= VALUE_TOLERANCE,
            "unit": got.unit_code == golden.UNIT_CODE[item["raw_unit"]],
            "currency": got.raw_currency == item["raw_currency"],
        }
        for name, ok in checks.items():
            if ok:
                score.correct[name] += 1
        if not all(checks.values()):
            score.errors.append(
                f"{line_id}: read {got.raw_value} {got.unit_code} {got.raw_currency}; golden "
                f"{item['raw_value']} {golden.UNIT_CODE[item['raw_unit']]} {item['raw_currency']}"
            )
    return score


def _key(kind: str, lines: list[str]) -> str:
    return f"{kind}[{','.join(sorted(lines))}]" if lines else kind


def evaluate_vendor(rfx: RFx, vendor_id: str) -> VendorReport:
    truth = golden.load(vendor_id)
    reads = ingest.load_vendor_reads(rfx.id, vendor_id)
    scores = {
        role: score_model(vendor_id, reads[role], reads["models"].get(role))
        for role in ("primary", "secondary")
    }
    readings, flags = assess_vendor(
        rfx, reads["primary"], reads["secondary"],
        reads["primary_conditions"], reads["secondary_conditions"],
        lead_role=reads["lead_role"], errors=reads["errors"],
    )  # fmt: skip

    # Merge flags of the same kind so line sets compare with the golden expectation.
    raised: dict[str, set[str]] = {}
    for flag in flags:
        raised.setdefault(flag.kind, set()).update(flag.lines)
    met, missed = [], []
    for expected in truth["expected_review_items"]:
        key = _key(expected["kind"], expected["lines"])
        if expected["kind"] in raised and raised[expected["kind"]] == set(expected["lines"]):
            met.append(key)
        else:
            got = raised.get(expected["kind"])
            missed.append(f"{key} (raised: {sorted(got) if got is not None else 'nothing'})")
    expected_kinds = {item["kind"] for item in truth["expected_review_items"]}
    unexpected = [
        _key(kind, sorted(lines)) for kind, lines in raised.items() if kind not in expected_kinds
    ]

    blocking = {line for flag in flags if flag.kind in _blocking_kinds() for line in flag.lines}
    states_wrong = []
    for item in truth["lines"]:
        reading = readings[item["line_id"]]
        if reading.how == "not_quoted":
            state = "not_quoted"
        elif item["line_id"] in blocking:
            state = "needs_review"
        else:
            state = "confident"
        if state != item["expected_state"]:
            states_wrong.append(f"{item['line_id']}: {state}, golden {item['expected_state']}")
    return VendorReport(
        vendor_id, scores, reads["agreement"], flags, met, missed, unexpected, states_wrong
    )


def _blocking_kinds() -> set[str]:
    from app.services.validation import CELL_BLOCKING

    return CELL_BLOCKING
