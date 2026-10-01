"""The grid: 5 vendors x 30 lines, one unit, one currency, every cell with its state.

Computed on demand from what is stored: the two models' readings, the conditions they
reported, and the decisions people have made. Nothing here calls a model, and nothing here
is cached, so the grid can never drift from its sources.

Cell states:
  confident     both models agree and nothing is open; the value counts
  needs_review  an open item touches this cell; a provisional value may be shown, never counted
  not_quoted    the vendor did not price the line; shown as "not quoted", never 0 or blank
  overridden    a person set or excluded the value; their reason travels with it
"""

from __future__ import annotations

import hashlib
import re
import statistics
from dataclasses import dataclass, field

from sqlalchemy import select

from app.db import session_scope
from app.models import (
    CellDecisionRow,
    ExtractionCallRow,
    ReviewItemRow,
    RfxRow,
    TraceRow,
    VendorQualityRow,
    VendorRow,
)
from app.schemas import (
    Assumptions,
    CellRef,
    Condition,
    Extraction,
    Freight,
    Grid,
    GridLine,
    GridVendor,
    LineItem,
    ModelReading,
    NormalizationStep,
    Override,
    QuoteCell,
    ReviewItem,
    ReviewOption,
    RFx,
    RunStats,
    VendorTotals,
)
from app.services import ingest, units
from app.services.normalization import normalise, parse_inr_amount
from app.services.validation import CELL_BLOCKING, Flag, LineReading, assess_vendor

FORMAT_LABEL = {"xlsx": "XLSX", "pdf": "PDF", "docx": "DOCX", "image": "Photo", "eml": "Email"}
UNIT_LABEL = {
    "per_piece": "per piece", "per_100": "per 100", "per_1000": "per 1,000", "per_kg": "per kg",
    "per_box": "per box", "per_bundle": "per bundle", "per_set": "per set", "unknown": "",
}  # fmt: skip
SYMBOL = {"INR": "₹", "USD": "USD "}
TITLES = {
    "unit_ambiguity": "Unit ambiguity",
    "ocr_disagreement": "Reading uncertain",
    "footnote_condition": "Conditional discount not applied",
    "not_quoted": "Lines not quoted",
    "model_error": "Extraction failed",
    "outlier": "Price out of line with other vendors",
    "missing_freight": "Freight not priced",
    "unmatched": "Row not matched to an RFx line",
    "currency_mismatch": "Quoted in a foreign currency",
    "carry_forward_unresolved": "'Same as last year' cannot be resolved",
}


@dataclass
class VendorWork:
    row: VendorRow
    reads: dict
    readings: dict[str, LineReading] = field(default_factory=dict)
    flags: list[Flag] = field(default_factory=list)
    items: list[ReviewItem] = field(default_factory=list)
    cells: dict[str, QuoteCell] = field(default_factory=dict)
    conditions: list[Condition] = field(default_factory=list)


def item_id(rfx_id: str, vendor_id: str, kind: str, lines: list[str], extra: str = "") -> str:
    key = f"{rfx_id}|{vendor_id}|{kind}|{','.join(sorted(lines))}|{extra}"
    return hashlib.sha1(key.encode()).hexdigest()[:12]


def money(value: float) -> str:
    """Indian grouping, no decimals: 1,08,320."""
    whole = f"{abs(value):.0f}"
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups + [tail])
    return ("-" if value < 0 else "") + "₹" + whole


def _raw_display(row: Extraction | None) -> str | None:
    if row is None:
        return None
    if row.not_quoted:
        return "declined"
    if row.raw_value is None:
        return "illegible"
    symbol = SYMBOL.get(row.raw_currency or "", f"{row.raw_currency or ''} ")
    value = f"{row.raw_value:,.2f}".rstrip("0").rstrip(".")
    return f"{symbol}{value} {UNIT_LABEL.get(row.unit_code, row.raw_unit or '')}".strip()


def _model_reading(role: str, row: Extraction) -> ModelReading:
    return ModelReading(
        role=role, model=row.model, raw_value=row.raw_value, raw_unit=row.raw_unit,
        unit_code=row.unit_code, raw_currency=row.raw_currency, confidence=row.confidence,
        alternatives=row.alternatives, not_quoted=row.not_quoted, notes=row.notes,
        match_reason=row.match.reason if row.match else None, source_ref=row.source_ref,
    )  # fmt: skip


def freight_summary(conditions: list[Condition], entered: float | None = None) -> Freight:
    statements = [c for c in conditions if c.kind == "freight"]
    text = " ".join(c.text for c in statements)
    if entered is not None:
        return Freight(kind="lump_sum", amount_inr=entered, statement=text or "entered by buyer")
    if not statements:
        return Freight(kind="not_stated")
    amount = next((parse_inr_amount(c.text) for c in statements if parse_inr_amount(c.text)), None)
    lowered = text.lower()
    extra = re.search(
        r"\b(not included|excluded|extra|buyer'?s account|to your account)\b", lowered
    )
    if amount:
        return Freight(kind="lump_sum", amount_inr=amount, statement=text)
    if not extra and re.search(r"\b(included|inclusive|delivered)\b", lowered):
        return Freight(kind="included", statement=text)
    return Freight(kind="extra_unpriced", statement=text)


def quality_result(row: VendorQualityRow | None) -> str | None:
    """Pass if all mandatory pass, Fail if any mandatory fails, else Partial (brief section 5)."""
    if row is None or row.error or not row.answers:
        return None
    statuses = []
    for answer in row.answers:
        if answer.get("mandatory"):
            override = (row.overrides or {}).get(answer["question_id"])
            statuses.append(override["status"] if override else answer["status"])
    if "fail" in statuses:
        return "Fail"
    return "Partial" if "unanswered" in statuses else "Pass"


def _options(
    flag: Flag, work: VendorWork, rfx: RFx, lines: dict[str, LineItem]
) -> list[ReviewOption]:
    kind = flag.kind
    if kind == "unit_ambiguity" and flag.lines:
        reading = work.readings[flag.lines[0]]
        if reading.normalised is None:
            return []
        return [
            ReviewOption(
                option_id=c.interpretation, label=f"{c.label.capitalize()}: {money(c.inr_per_base)}",
                inr_per_base=c.inr_per_base, normalization_trace=c.steps, lines=flag.lines,
            )
            for c in reading.normalised.candidates
        ]  # fmt: skip
    if kind == "ocr_disagreement" and flag.lines:
        reading = work.readings[flag.lines[0]]
        line = lines[flag.lines[0]]
        values: dict[float, list[str]] = {}
        for row in (reading.primary, reading.secondary):
            if row is None:
                continue
            if row.raw_value is not None:
                values.setdefault(row.raw_value, []).append(f"read by {row.model}")
            for alternative in row.alternatives[:6]:
                values.setdefault(alternative, []).append(f"possible, per {row.model}")
        template = reading.lead or reading.primary or reading.secondary
        options = []
        for value, who in sorted(values.items()):
            candidate = normalise(template.model_copy(update={"raw_value": value}), line, rfx)
            if candidate.value is None:
                continue
            raw = f"{value:,.2f}".rstrip("0").rstrip(".")
            options.append(
                ReviewOption(
                    option_id=f"value:{value}", label=f"Use {raw}: {money(candidate.value)}",
                    inr_per_base=candidate.value, note="; ".join(sorted(set(who))),
                    normalization_trace=candidate.candidates[0].steps, lines=flag.lines,
                )
            )  # fmt: skip
        return options
    if kind == "footnote_condition":
        percent = flag.detail.get("percent")
        by_rate = flag.detail.get("lines_by_rate", flag.lines)
        by_value = flag.detail.get("lines_by_line_value", [])
        threshold = flag.detail.get("threshold_inr")
        options = []
        if percent and threshold:
            options.append(
                ReviewOption(
                    option_id="by_rate", lines=by_rate,
                    label=f"Apply {percent:g}% to lines with a rate above {money(threshold)} "
                    f"per 1,000 ({len(by_rate)} line{'s' if len(by_rate) != 1 else ''})",
                )
            )  # fmt: skip
            if set(by_value) != set(by_rate):
                options.append(
                    ReviewOption(
                        option_id="by_line_value", lines=by_value,
                        label=f"Apply {percent:g}% to lines whose value exceeds {money(threshold)} "
                        f"({len(by_value)} lines)",
                    )
                )  # fmt: skip
        elif percent:
            options.append(
                ReviewOption(option_id="by_rate", lines=flag.lines, label=f"Apply {percent:g}% to these lines")
            )  # fmt: skip
        options.append(ReviewOption(option_id="none", label="Do not apply; keep the quoted rates"))
        return options
    simple = {
        "not_quoted": [("keep_excluded", "Keep excluded")],
        "carry_forward_unresolved": [("exclude", "Treat these lines as not quoted")],
        "currency_mismatch": [
            ("accept_policy_rate", f"Accept conversion at {rfx.fx_policy.foreign_currency} 1 = "
             f"₹{rfx.fx_policy.rate} ({rfx.fx_policy.source})")
        ],
        "missing_freight": [("accept_open", "Carry as a pre-award condition")],
        "outlier": [("accept", "Accept as quoted")],
        "unmatched": [("ignore", "Ignore this row")],
        "model_error": [("exclude_vendor", "Exclude this vendor from the comparison")],
    }  # fmt: skip
    return [
        ReviewOption(option_id=option_id, label=label, lines=flag.lines)
        for option_id, label in simple.get(kind, [])
    ]


def _make_item(flag: Flag, work: VendorWork, rfx: RFx, lines: dict[str, LineItem]) -> ReviewItem:
    extra = flag.reason if flag.kind == "unmatched" else ""
    first = work.readings.get(flag.lines[0]) if flag.lines else None
    readings: list[ModelReading] = []
    source = None
    agreement = None
    if first is not None and len(flag.lines) == 1:
        readings = [
            _model_reading(role, row)
            for role, row in (("primary", first.primary), ("secondary", first.secondary))
            if row is not None
        ]
        source = first.lead.source_ref if first.lead else None
        agreement = first.agreement
    return ReviewItem(
        id=item_id(rfx.id, work.row.vendor_id, flag.kind, flag.lines, extra),
        vendor_id=work.row.vendor_id,
        vendor_name=work.row.name,
        cells=[CellRef(vendor_id=work.row.vendor_id, line_id=line) for line in flag.lines],
        kind=flag.kind,
        title=TITLES.get(flag.kind, flag.kind),
        reason=flag.reason,
        evidence=flag.evidence,
        source=source,
        readings=readings,
        agreement=agreement,
        options=_options(flag, work, rfx, lines),
        blocks_cells=flag.kind in CELL_BLOCKING,
        detail=flag.detail,
    )


def _annotation(reading: LineReading, vision: bool) -> str | None:
    lead = reading.lead
    if reading.how == "carry_forward":
        return "same as last year"
    if reading.how == "carry_forward_unresolved":
        return "no last-year price"
    if lead is None:
        return None
    if lead.unit_code == "per_kg":
        return "from ₹/kg"
    if units.is_ambiguous(lead.unit_code):
        return f"{UNIT_LABEL[lead.unit_code]}?"
    # Currency and photo are vendor-wide and already in the column header.
    return None


def _base_cell(
    work: VendorWork, line: LineItem, rfx: RFx, resolved: dict[str, ReviewItem], vision: bool
) -> QuoteCell:
    """The cell before open items and decisions are applied."""
    vendor_id = work.row.vendor_id
    reading = work.readings[line.line_id]
    readings = [
        _model_reading(role, row)
        for role, row in (("primary", reading.primary), ("secondary", reading.secondary))
        if row is not None
    ]
    cell = QuoteCell(
        vendor_id=vendor_id, line_id=line.line_id, state="confident", how=reading.how,
        readings=readings, agreement=reading.agreement, raw_display=_raw_display(reading.lead),
        annotation=_annotation(reading, vision),
    )  # fmt: skip
    if reading.how == "not_quoted":
        cell.state = "not_quoted"
        return cell
    if reading.how == "carry_forward":
        value = reading.carry_forward_inr
        cell.inr_per_base = value
        cell.raw_display = "same as last year"
        cell.normalization_trace = [
            NormalizationStep(
                op="carry_forward", factor=1.0, value_in=value, value_out=value,
                source=f"RFx {line.line_id} last_year_price_inr",
            )
        ]  # fmt: skip
        return cell
    if reading.how == "carry_forward_unresolved":
        cell.raw_display = "same as last year"
        return cell

    result = reading.normalised
    lead = reading.lead
    # A resolved reading choice replaces the lead's raw value.
    for item in resolved.values():
        option = (item.resolution or {}).get("option_id", "")
        if (
            item.kind == "ocr_disagreement"
            and line.line_id in _lines(item)
            and option.startswith("value:")
        ):
            chosen = float(option.split(":", 1)[1])
            result = normalise(lead.model_copy(update={"raw_value": chosen}), line, rfx)
            cell.raw_display = _raw_display(lead.model_copy(update={"raw_value": chosen}))
            cell.resolution_note = f"reading set to {chosen:g} by {item.resolution.get('actor')}"
    if result is None or not result.candidates:
        return cell
    candidate = result.candidates[0]
    if result.ambiguous:
        chosen = None
        for item in resolved.values():
            if item.kind == "unit_ambiguity" and line.line_id in _lines(item):
                option = (item.resolution or {}).get("option_id")
                chosen = next((c for c in result.candidates if c.interpretation == option), None)
                if chosen:
                    cell.resolution_note = (
                        f"unit read as '{chosen.label}' by {item.resolution.get('actor')}"
                    )
        if chosen is None:
            cell.display_inr = candidate.inr_per_base  # provisional, first interpretation
            cell.normalization_trace = candidate.steps
            return cell
        candidate = chosen
        cell.annotation = f"{UNIT_LABEL[lead.unit_code]}: {chosen.label.lower()}"
    cell.inr_per_base = candidate.inr_per_base
    cell.normalization_trace = list(candidate.steps)
    return cell


def _lines(item: ReviewItem) -> set[str]:
    return {ref.line_id for ref in item.cells}


def _apply_discount(work: VendorWork, resolved: dict[str, ReviewItem]) -> None:
    for item in resolved.values():
        if item.kind != "footnote_condition":
            continue
        option_id = (item.resolution or {}).get("option_id")
        option = next((o for o in item.options if o.option_id == option_id), None)
        percent = item.detail.get("percent")
        if option is None or option_id == "none" or not percent:
            continue
        for line_id in option.lines:
            cell = work.cells[line_id]
            if cell.inr_per_base is None:
                continue
            discounted = round(cell.inr_per_base * (1 - percent / 100), 2)
            cell.normalization_trace.append(
                NormalizationStep(
                    op="discount", factor=1 - percent / 100, value_in=cell.inr_per_base,
                    value_out=discounted, source=f"vendor footnote: '{item.detail.get('text')}'",
                )
            )  # fmt: skip
            cell.inr_per_base = discounted
            cell.annotation = f"{percent:g}% discount applied"


def _outlier_flags(works: list[VendorWork], rfx: RFx) -> dict[str, list[Flag]]:
    sigma, floor = units.threshold("outlier_sigma"), units.threshold("outlier_min_deviation_pct")
    out: dict[str, list[Flag]] = {}
    for line in rfx.line_items:
        priced = {
            w.row.vendor_id: w.cells[line.line_id].inr_per_base
            for w in works
            if line.line_id in w.cells and w.cells[line.line_id].inr_per_base is not None
        }
        if len(priced) < 4:
            continue
        median = statistics.median(priced.values())
        spread = statistics.pstdev(priced.values())
        for vendor_id, value in priced.items():
            deviation = (value - median) / median * 100
            # With five vendors a bare 2-sigma test fires on harmless differences, so the
            # deviation must also be material.
            if spread and abs(value - median) > sigma * spread and abs(deviation) > floor:
                out.setdefault(vendor_id, []).append(
                    Flag(
                        "outlier", [line.line_id],
                        f"{money(value)} is {abs(deviation):.0f}% {'above' if deviation > 0 else 'below'} "
                        f"the line median of {money(median)} across {len(priced)} vendors",
                        detail={"median": median, "deviation_pct": round(deviation, 1)},
                    )
                )  # fmt: skip
    return out


def _unit_notes(works: list[VendorWork], rfx: RFx) -> None:
    """Tell the reviewer how each interpretation compares with the other vendors."""
    for work in works:
        for item in work.items:
            if item.kind not in ("unit_ambiguity", "ocr_disagreement") or not item.cells:
                continue
            line_id = item.cells[0].line_id
            others = [
                w.cells[line_id].inr_per_base
                for w in works
                if w is not work
                and line_id in w.cells
                and w.cells[line_id].inr_per_base is not None
            ]
            if len(others) < 2:
                continue
            median = statistics.median(others)
            for option in item.options:
                if option.inr_per_base is None:
                    continue
                ratio = option.inr_per_base / median
                if ratio < 0.5:
                    comparison = (
                        f"{1 / ratio:.0f}x below the other vendors' median of {money(median)}"
                    )
                elif ratio > 2:
                    comparison = f"{ratio:.0f}x above the other vendors' median of {money(median)}"
                else:
                    comparison = f"{(ratio - 1) * 100:+.1f}% against the other vendors' median of {money(median)}"
                option.note = f"{option.note}; {comparison}" if option.note else comparison


@dataclass
class GridResult:
    grid: Grid
    items: list[ReviewItem]
    rfx: RFx
    quality: dict[str, VendorQualityRow]


def build(rfx_id: str) -> GridResult:
    with session_scope() as session:
        rfx_row = session.get(RfxRow, rfx_id)
        if rfx_row is None:
            raise KeyError(rfx_id)
        rfx = RFx.model_validate(rfx_row.payload)
        vendors = session.scalars(select(VendorRow).where(VendorRow.rfx_id == rfx_id)).all()
        stored_items = {
            row.id: row
            for row in session.scalars(select(ReviewItemRow).where(ReviewItemRow.rfx_id == rfx_id))
        }
        decisions = {
            (row.vendor_id, row.line_id): row
            for row in session.scalars(
                select(CellDecisionRow).where(CellDecisionRow.rfx_id == rfx_id)
            )
        }
        quality = {
            row.vendor_id: row
            for row in session.scalars(
                select(VendorQualityRow).where(VendorQualityRow.rfx_id == rfx_id)
            )
        }
        # "This run" is the latest ingest; the Run inspector lists every call ever made.
        latest = session.scalars(
            select(ExtractionCallRow.run_id)
            .where(ExtractionCallRow.rfx_id == rfx_id)
            .order_by(ExtractionCallRow.id.desc())
            .limit(1)
        ).first()
        traces = session.scalars(select(TraceRow).where(TraceRow.parent_run_id == latest)).all()
        run = RunStats(
            model_calls=len(traces),
            failed_calls=sum(1 for t in traces if t.status != "ok"),
            cost_inr=round(sum(t.cost_inr or 0 for t in traces), 2),
            latency_s=round(sum(t.latency_ms for t in traces) / 1000, 1),
            agreement=None,
        )
        session.expunge_all()

    lines = {line.line_id: line for line in rfx.line_items}

    def with_status(item: ReviewItem) -> ReviewItem:
        row = stored_items.get(item.id)
        if row is not None:
            item.status, item.resolution = row.status, row.resolution
        return item

    works: list[VendorWork] = []
    for vendor in sorted(vendors, key=lambda v: v.position):
        reads = ingest.load_vendor_reads(rfx_id, vendor.vendor_id)
        work = VendorWork(row=vendor, reads=reads)
        works.append(work)
        if not reads["has_reply"]:
            for line in rfx.line_items:
                work.cells[line.line_id] = QuoteCell(
                    vendor_id=vendor.vendor_id, line_id=line.line_id, state="not_quoted",
                    how="not_quoted", flag_reason="no reply received from this vendor",
                )  # fmt: skip
            continue
        work.readings, work.flags = assess_vendor(
            rfx, reads["primary"], reads["secondary"],
            reads["primary_conditions"], reads["secondary_conditions"],
            lead_role=reads["lead_role"], errors=reads["errors"],
        )  # fmt: skip
        lead_conditions = reads[f"{reads['lead_role']}_conditions"]
        work.conditions = (
            lead_conditions or reads["primary_conditions"] or reads["secondary_conditions"]
        )
        work.items = [with_status(_make_item(flag, work, rfx, lines)) for flag in work.flags]
        resolved = {item.id: item for item in work.items if item.status == "resolved"}
        vision = reads["lead_role"] == "secondary"
        for line in rfx.line_items:
            work.cells[line.line_id] = _base_cell(work, line, rfx, resolved, vision)
        _apply_discount(work, resolved)

    # Outliers need every vendor's value, so they are found after the first pass.
    for vendor_id, flags in _outlier_flags([w for w in works if w.readings], rfx).items():
        work = next(w for w in works if w.row.vendor_id == vendor_id)
        work.flags += flags
        work.items += [with_status(_make_item(flag, work, rfx, lines)) for flag in flags]
    _unit_notes(works, rfx)

    # Open items hold their cells out of the totals; decisions override everything.
    for work in works:
        vendor_id = work.row.vendor_id
        for item in work.items:
            for line_id in _lines(item):
                cell = work.cells[line_id]
                cell.review_item_ids.append(item.id)
                if item.blocks_cells and item.status != "resolved" and cell.state != "not_quoted":
                    cell.state = "needs_review"
                    cell.flag_reason = item.reason
                    if cell.display_inr is None:
                        cell.display_inr = cell.inr_per_base
                    cell.inr_per_base = None
                    if item.kind == "footnote_condition":
                        cell.annotation = "discount in footnote"
                    elif item.kind == "outlier":
                        cell.annotation = "outlier"
        for line_id, cell in work.cells.items():
            decision = decisions.get((vendor_id, line_id))
            if decision is None:
                continue
            cell.state = "overridden"
            cell.override = Override(
                action=decision.action, value=decision.value, actor=decision.actor,
                reason=decision.reason, at=decision.at,
            )  # fmt: skip
            cell.flag_reason = None
            if decision.action == "exclude":
                cell.excluded, cell.inr_per_base = True, None
            else:
                cell.display_inr = cell.display_inr or cell.inr_per_base  # what the system computed
                cell.inr_per_base = decision.value
        for line_id, cell in work.cells.items():
            if cell.inr_per_base is not None:
                cell.extended_inr = round(cell.inr_per_base * lines[line_id].qty / 1000, 2)

    for line in rfx.line_items:
        counted = [
            w.cells[line.line_id] for w in works if w.cells[line.line_id].inr_per_base is not None
        ]
        if counted:
            lowest = min(cell.inr_per_base for cell in counted)
            for cell in counted:
                cell.is_lowest = cell.inr_per_base == lowest

    grid_vendors = []
    for work in works:
        cells = list(work.cells.values())
        reads = work.reads
        quote = next((f for f in reads.get("files", []) if f.kind == "quote"), None)
        lead_rows = (
            (reads.get(reads.get("lead_role", "primary")) or []) if reads["has_reply"] else []
        )
        currency = next((r.raw_currency for r in lead_rows if r.raw_currency), None)
        entered = next(
            ((i.resolution or {}).get("amount") for i in work.items
             if i.kind == "missing_freight" and i.status == "resolved"), None,
        )  # fmt: skip
        label = FORMAT_LABEL.get(quote.format, quote.format) if quote else None
        if quote and quote.pages and quote.format == "pdf":
            label += f" · {quote.pages} pages"
        if currency and currency != rfx.currency:
            label = f"{label} · {currency}"
        grid_vendors.append(
            GridVendor(
                vendor_id=work.row.vendor_id,
                name=work.row.name,
                has_reply=reads["has_reply"],
                format=quote.format if quote else None,
                format_label=label,
                file=quote.name if quote else None,
                lines_quoted=sum(1 for c in cells if c.how != "not_quoted"),
                currency=currency,
                quality=quality_result(quality.get(work.row.vendor_id)),
                freight=freight_summary(work.conditions, entered),
                totals=VendorTotals(
                    extended_inr=round(sum(c.extended_inr or 0 for c in cells), 2),
                    lines_counted=sum(1 for c in cells if c.inr_per_base is not None),
                    needs_review=sum(1 for c in cells if c.state == "needs_review"),
                    not_quoted=sum(1 for c in cells if c.state == "not_quoted"),
                    excluded=sum(1 for c in cells if c.excluded),
                ),
                agreement=reads.get("agreement"),
                models=reads.get("models", {}),
                extraction_error="; ".join(reads.get("errors", {}).values()) or None,
            )
        )

    agreements = [v.agreement for v in grid_vendors if v.agreement is not None]
    run.agreement = round(sum(agreements) / len(agreements), 4) if agreements else None
    items = [item for work in works for item in work.items]
    all_cells = [cell for work in works for cell in work.cells.values()]
    fx = rfx.fx_policy
    grid = Grid(
        rfx_id=rfx.id,
        title=rfx.title,
        assumptions=Assumptions(
            base_unit="₹ per 1,000 pcs",
            fx=f"{fx.foreign_currency} 1 = ₹{fx.rate}, {fx.source}, {fx.as_of.strftime('%d %b %Y')}",
            freight=rfx.freight_policy,
            tax=rfx.tax_policy,
        ),
        vendors=grid_vendors,
        lines=[
            GridLine(
                line_id=line.line_id,
                description=line.description,
                qty=line.qty,
                uom=line.uom,
                last_year_inr=line.last_year_price_inr,
                cells={w.row.vendor_id: w.cells[line.line_id] for w in works},
            )
            for line in rfx.line_items
        ],  # fmt: skip
        review_open=sum(1 for item in items if item.status != "resolved"),
        review_blocking_cells=sum(1 for c in all_cells if c.state == "needs_review"),
        counts={
            state: sum(1 for c in all_cells if c.state == state)
            for state in ("confident", "needs_review", "not_quoted", "overridden")
        },
        run=run,
    )
    return GridResult(grid=grid, items=items, rfx=rfx, quality=quality)
