"""`make seed`: write the RFx, the five vendor replies, the attachments and the golden set.

Run from the backend environment:  cd backend && uv run python ../data/gen/seed.py
Outputs are committed. Re-running reproduces them byte for byte.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

import catalog as c  # noqa: E402
import make_anand  # noqa: E402
import make_attachments  # noqa: E402
import make_kaveri  # noqa: E402
import make_meridian  # noqa: E402
import make_northbox  # noqa: E402
import make_sribalaji  # noqa: E402
from common import ATTACHMENTS, GOLDEN, REPLIES, REPO, RFX_DIR  # noqa: E402

from app.schemas import RFx  # noqa: E402


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def build_rfx() -> dict:
    last_year = c.last_year_prices()
    rfx = {
        "id": c.RFX_ID,
        "title": c.RFX_TITLE,
        "category": "Corrugated packaging",
        "base_unit": "per_1000_pcs",
        "currency": "INR",
        "fx_policy": {
            "source": "RBI reference rate",
            "rate": c.FX_USD_INR,
            "foreign_currency": "USD",
            "as_of": c.FX_AS_OF.isoformat(),
        },
        "freight_policy": "Freight is excluded from line prices and shown per vendor as stated.",
        "tax_policy": "GST is excluded from all prices.",
        "terms": {
            "payment": "60 days from receipt of material",
            "delivery": "Delivered to Chakan, Pune, against weekly schedules",
            "validity_days": 60,
            "assumptions": [],
        },
        "questionnaire": [
            {"question_id": qid, "text": text, "mandatory": mandatory}
            for qid, mandatory, text in c.QUESTIONNAIRE
        ],
        "line_items": [
            {
                "line_id": line.line_id,
                "description": line.description,
                "spec": {
                    "ply": line.ply,
                    "gsm": line.gsm,
                    "dims_mm": list(line.dims) if line.dims else None,
                    "print": line.print_,
                    "board_weight_kg_per_pc": line.weight_kg,
                },
                "qty": line.qty,
                "uom": line.uom,
                "last_year_price_inr": last_year[line.line_id],
            }
            for line in c.LINES
        ],
    }
    RFx.model_validate(rfx)  # the seed must satisfy the app's own contract
    return rfx


def intake_notes() -> str:
    """A buyer's rough notes: what they would paste to the co-pilot to draft this RFx."""
    last_year = c.last_year_prices()
    rows = []
    for line in c.LINES:
        text = line.description.replace("×", "x").replace("-ply", " ply").replace(" GSM", "gsm")
        text = text.replace("printed 1 colour", "1 col print").replace("printed 2 colour", "2 col print")
        price = last_year[line.line_id]
        ly = f"LY {price:,.0f}/1000" if price is not None else "new item, no LY price"
        rows.append(f"- {text} - {line.qty:,} {'sets' if line.uom == 'sets' else 'nos'} ({ly})")
    return (
        "Need to float the Q4 2026 corrugated packaging RFx for the Chakan plant. Annual "
        "quantities below, with last year's contract rates where we have them. Prices to come "
        "back in INR per 1,000, GST and freight separate. Payment 60 days from GRN, delivered "
        "Chakan on weekly schedules, offers valid 60 days.\n\n"
        "BRC or an equivalent food-safety certification is a must, so is food-contact compliance "
        "for the inks, and I want at least two production sites per vendor for continuity. Also "
        "ask about lead time, capacity, 60-day terms, recycled content and safety stock.\n\n"
        "Items:\n" + "\n".join(rows) + "\n"
    )


EXPECTED_REVIEW = {
    "meridian": [],
    "sribalaji": [
        {"kind": "footnote_condition", "lines": "by_rate", "why": "4% discount in footnote 2 is conditional on 'lines above ₹1 L' and is not applied in the quoted rates"},
    ],
    "kaveri": [
        {"kind": "unit_ambiguity", "lines": ["L01"], "why": "'per box' with 'packed 100 per bundle' in the same sentence"},
        {"kind": "not_quoted", "lines": ["L27"], "why": "declined in the letter"},
        {"kind": "currency_mismatch", "lines": "all_quoted", "why": "quoted in USD; RFx currency is INR"},
        {"kind": "missing_freight", "lines": [], "why": "FOB Chennai; onward freight not priced"},
    ],
    "northbox": [
        {"kind": "ocr_disagreement", "lines": ["L05"], "why": "tens digit is blotted: 3,935 or 3,985"},
        {"kind": "not_quoted", "lines": ["L08", "L26", "L27"], "why": "rows absent from the rate card"},
    ],
    "anand": [
        {"kind": "carry_forward_unresolved", "lines": ["L25", "L27"], "why": "'rest same as last year' but these lines are new and have no last-year price"},
        {"kind": "missing_freight", "lines": [], "why": "'freight extra' with no amount"},
    ],
}  # fmt: skip


def build_golden(vendor_id: str, artefact: dict) -> dict:
    quotes = c.build_quotes()[vendor_id]
    vendor = c.VENDOR_BY_ID[vendor_id]
    review = json.loads(json.dumps(EXPECTED_REVIEW[vendor_id]))
    for item in review:
        if item["lines"] == "by_rate":
            item["lines"] = artefact["discount"]["qualifying_lines_by_rate"]
        elif item["lines"] == "all_quoted":
            item["lines"] = [line.line_id for line in c.LINES if quotes[line.line_id].quoted]
    flagged = {
        line_id
        for item in review
        if item["kind"] in ("footnote_condition", "unit_ambiguity", "ocr_disagreement", "carry_forward_unresolved")
        for line_id in item["lines"]
    }  # fmt: skip

    lines = []
    for line in c.LINES:
        quote = quotes[line.line_id]
        source = artefact["lines"].get(line.line_id, {})
        extracted = quote.true_inr_per_1000
        true_value = extracted
        if vendor_id == "sribalaji" and line.line_id in artefact["discount"]["qualifying_lines_by_rate"]:
            true_value = round(extracted * (1 - c.SRIBALAJI_DISCOUNT["pct"] / 100), 2)
        if not quote.quoted:
            state = "not_quoted"
        elif line.line_id in flagged:
            state = "needs_review"
        else:
            state = "confident"
        lines.append(
            {
                "line_id": line.line_id,
                "quoted": quote.quoted,
                "how": quote.how,
                "raw_value": quote.raw_value,
                "raw_unit": quote.raw_unit,
                "raw_currency": quote.raw_currency,
                "raw_text": source.get("raw_text"),
                "locator": source.get("locator"),
                "bbox_px": source.get("bbox_px"),
                "vendor_description": source.get("vendor_description"),
                # What deterministic normalisation of the quoted figure gives (list price).
                "normalised_inr_per_1000": extracted,
                # What the vendor actually means once every condition is resolved.
                "true_inr_per_1000": true_value,
                "expected_state": state,
                "notes": quote.notes,
            }
        )

    quality = c.QUALITY[vendor_id]
    locators = artefact.get("questionnaire_locators", {})
    golden = {
        "vendor_id": vendor_id,
        "vendor_name": vendor.name,
        "format": vendor.reply_format,
        "received_at": vendor.received_at,
        "files": artefact["files"],
        "currency": next(q.raw_currency for q in quotes.values() if q.raw_currency),
        "lines_quoted_count": sum(1 for q in quotes.values() if q.quoted),
        "freight": {**c.FREIGHT[vendor_id], "locator": artefact.get("freight_locator")},
        "expected_review_items": review,
        "quality_result": quality["result"],
        "questionnaire": [
            {
                "question_id": qid,
                "mandatory": mandatory,
                "expected": quality["answers"][qid][0],
                "evidence": quality["answers"][qid][1],
                "locator": locators.get(qid),
            }
            for qid, mandatory, _text in c.QUESTIONNAIRE
        ],
        "lines": lines,
    }
    for key in ("unit_note", "discount", "footnotes", "unit_ambiguity", "default_unit_statement",
                "ambiguous_digit", "image_size", "skew_deg", "unit_statement", "body", "statements",
                "embedded_attachments"):  # fmt: skip
        if key in artefact:
            golden[key] = artefact[key]
    return golden


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    rfx = build_rfx()
    write_json(RFX_DIR / f"{c.RFX_ID}.json", rfx)
    write_json(
        RFX_DIR / "vendors.json",
        [
            {"vendor_id": v.vendor_id, "name": v.name, "contact": v.contact, "email": v.email, "city": v.city}
            for v in c.VENDORS
        ],
    )  # fmt: skip

    (RFX_DIR / "intake_notes.txt").write_text(intake_notes(), encoding="utf-8")

    attachments = make_attachments.build()  # first: Anand's email embeds the certificate
    artefacts = {
        "meridian": make_meridian.build(),
        "sribalaji": make_sribalaji.build(),
        "kaveri": make_kaveri.build(),
        "northbox": make_northbox.build(),
        "anand": make_anand.build(),
    }

    manifest = []
    for vendor in c.VENDORS:
        golden = build_golden(vendor.vendor_id, artefacts[vendor.vendor_id])
        attachment = attachments.get(vendor.vendor_id)
        golden["attachment"] = attachment
        write_json(GOLDEN / f"{vendor.vendor_id}.json", golden)
        files = [REPLIES / vendor.vendor_id / name for name in artefacts[vendor.vendor_id]["files"]]
        loose = []
        if attachment and attachment["delivered"] != "inside the email":
            loose = [ATTACHMENTS / attachment["file"]]
        manifest.append(
            {
                "vendor_id": vendor.vendor_id,
                "received_at": vendor.received_at,
                "files": [{"path": str(f.relative_to(REPO)), "sha256": sha256(f)} for f in files],
                "attachments": [{"path": str(f.relative_to(REPO)), "sha256": sha256(f)} for f in loose],
            }
        )
    write_json(REPLIES / "manifest.json", manifest)

    print(f"Seeded {c.RFX_ID}: {len(rfx['line_items'])} lines, {len(rfx['questionnaire'])} questions")
    for entry in manifest:
        names = [Path(f["path"]).name for f in entry["files"] + entry["attachments"]]
        golden = json.loads((GOLDEN / f"{entry['vendor_id']}.json").read_text())
        print(f"  {entry['vendor_id']:<10} {golden['lines_quoted_count']}/30 lines  {', '.join(names)}")
    print()
    print(c.summary().split("\n\n")[1])


if __name__ == "__main__":
    main()
