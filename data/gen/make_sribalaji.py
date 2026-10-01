"""Sri Balaji Corrugators: a three-page quotation PDF on letterhead.

Breakage (brief section 7): a 4% discount is buried in footnote 2 with a condition
("lines above ₹1 L"). The table itself follows the RFx order and quotes list prices.
"""

from __future__ import annotations

from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

import catalog as c
from common import REPLIES, font_path

FILENAME = "SriBalaji_Quotation_SBC-Q-2026-311.pdf"
QUOTE_REF = "SBC/Q/2026-27/311"
FOOTNOTES = [
    "1. Rates are in Indian Rupees per 1,000 pcs (per 1,000 sets for partitions), ex-works Sivakasi, exclusive of GST @ 18%.",
    "2. 4% discount on lines above ₹1 L.",
    "3. Quantity tolerance ±5%. Rates valid for 60 days from the date of this quotation.",
]  # fmt: skip
PAGE_1_LINES = 14  # lines 1-14 on page 1, 15-30 and the footnotes on page 2

NAVY = colors.HexColor("#7A1F1F")


def register_fonts() -> None:
    for name, file in [
        ("Body", "DejaVuSerif.ttf"),
        ("Body-Bold", "DejaVuSerif-Bold.ttf"),
        ("Body-Italic", "DejaVuSerif-Italic.ttf"),
        ("Sans", "DejaVuSans.ttf"),
        ("Sans-Bold", "DejaVuSans-Bold.ttf"),
    ]:
        pdfmetrics.registerFont(TTFont(name, font_path(file)))
    pdfmetrics.registerFontFamily("Body", normal="Body", bold="Body-Bold", italic="Body-Italic")
    pdfmetrics.registerFontFamily("Sans", normal="Sans", bold="Sans-Bold")


def describe(line: c.Line) -> str:
    """Sri Balaji restates the RFx description in its own typing habits."""
    text = line.description.replace("×", " x ").replace("5-ply", "5 Ply").replace("3-ply", "3 Ply")
    return text.replace("7-ply", "7 Ply").replace("printed 1 colour", "1 col. print").replace(
        "printed 2 colour", "2 col. print"
    )


def letterhead(canvas, doc) -> None:
    width, height = A4
    canvas.saveState()
    canvas.setFillColor(NAVY)
    canvas.rect(0, height - 30 * mm, width, 30 * mm, stroke=0, fill=1)
    canvas.setFillColor(colors.white)
    canvas.setFont("Body-Bold", 19)
    canvas.drawString(18 * mm, height - 15 * mm, "SRI BALAJI CORRUGATORS")
    canvas.setFont("Sans", 7.5)
    canvas.drawString(18 * mm, height - 21 * mm, "Manufacturers of Corrugated Boxes, Boards and Rolls · Since 1994")
    canvas.drawString(
        18 * mm, height - 25.5 * mm,
        "Works: 4/118 Sattur Road, Sivakasi 626123, Tamil Nadu · GSTIN 33AAGFS2291P1ZK · quotes@sribalajicorrugators.example",
    )  # fmt: skip
    canvas.setFillColor(colors.HexColor("#555555"))
    canvas.setFont("Sans", 7)
    canvas.drawString(18 * mm, 10 * mm, f"Quotation {QUOTE_REF} · {c.BUYER['company']} · {c.RFX_ID}")
    canvas.drawRightString(width - 18 * mm, 10 * mm, f"Page {doc.page} of 3")
    canvas.setStrokeColor(NAVY)
    canvas.line(18 * mm, 13.5 * mm, width - 18 * mm, 13.5 * mm)
    canvas.restoreState()


def build() -> dict:
    register_fonts()
    quotes = c.build_quotes()["sribalaji"]
    path = REPLIES / "sribalaji" / FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)

    body = ParagraphStyle("body", fontName="Body", fontSize=9.5, leading=13.5, alignment=TA_JUSTIFY)
    small = ParagraphStyle("small", fontName="Sans", fontSize=6.5, leading=8.5, textColor=colors.HexColor("#444444"))
    cell = ParagraphStyle("cell", fontName="Sans", fontSize=7.8, leading=9.6)
    heading = ParagraphStyle("heading", fontName="Body-Bold", fontSize=10.5, leading=14, textColor=NAVY)

    story = [
        Paragraph(f"Ref: {QUOTE_REF}<br/>Date: 23 September 2026", body),
        Spacer(1, 4 * mm),
        Paragraph(
            f"To<br/><b>{c.BUYER['company']}</b><br/>{c.BUYER['address']}<br/>"
            f"Kind attention: {c.BUYER['contact']}, {c.BUYER['title']}",
            body,
        ),
        Spacer(1, 4 * mm),
        Paragraph(f"<b>Sub: Quotation against your RFQ {c.RFX_ID}, {c.RFX_TITLE}</b>", body),
        Spacer(1, 3 * mm),
        Paragraph(
            "Dear Sir, we thank you for your valued enquiry and are pleased to submit our lowest "
            "offer for your annual requirement of corrugated packaging as per the schedule below. "
            "We have quoted for all thirty items in the order of your enquiry.",
            body,
        ),
        Spacer(1, 4 * mm),
    ]

    header = ["S.No", "Description", "Qty", "UOM", "Rate (₹)¹", "Amount (₹)"]
    per_line: dict[str, dict] = {}
    rows_by_page: dict[int, list] = {1: [header], 2: [header]}
    total = 0.0
    for index, line in enumerate(c.LINES, start=1):
        quote = quotes[line.line_id]
        amount = quote.raw_value * line.qty / 1000
        total += amount
        page = 1 if index <= PAGE_1_LINES else 2
        rate_text = c.money(quote.raw_value, 2)
        rows_by_page[page].append(
            [str(index), Paragraph(describe(line), cell), c.money(line.qty), line.uom, rate_text, c.money(amount, 2)]
        )  # fmt: skip
        per_line[line.line_id] = {
            "locator": f"page {page}, table row S.No {index}",
            "raw_text": rate_text,
            "vendor_description": describe(line),
        }
    rows_by_page[2].append(["", Paragraph("<b>Total, 30 items (before GST and freight)²</b>", cell), "", "", "", c.money(total, 2)])  # fmt: skip

    def table(rows: list, has_total: bool) -> Table:
        widths = [11 * mm, 84 * mm, 18 * mm, 11 * mm, 24 * mm, 27 * mm]
        style = [
            ("FONT", (0, 0), (-1, 0), "Sans-Bold", 7.8),
            ("FONT", (0, 1), (-1, -1), "Sans", 7.8),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EFE3E3")),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#8A8A8A")),
            ("ALIGN", (2, 0), (2, -1), "RIGHT"),
            ("ALIGN", (4, 0), (5, -1), "RIGHT"),
            ("ALIGN", (0, 0), (0, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 2.2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2),
        ]
        if has_total:
            style.append(("FONT", (5, -1), (5, -1), "Sans-Bold", 7.8))
        return Table(rows, colWidths=widths, repeatRows=1, style=TableStyle(style))

    story += [table(rows_by_page[1], False), Spacer(1, 2 * mm), Paragraph("<i>continued overleaf</i>", small), PageBreak()]
    story += [Paragraph("Schedule of rates (continued)", heading), Spacer(1, 2 * mm), table(rows_by_page[2], True), Spacer(1, 3 * mm)]
    story += [Paragraph(note, small) for note in FOOTNOTES]
    story.append(PageBreak())

    story += [Paragraph("Commercial terms", heading), Spacer(1, 1.5 * mm)]
    for term in [
        f"<b>Freight:</b> {c.FREIGHT['sribalaji']['statement']}",
        "<b>Payment:</b> 45 days from date of invoice. 60 days acceptable against LC or with 1% loading.",
        "<b>Delivery:</b> 12 days from receipt of purchase order, in full truck loads.",
        "<b>Printing:</b> stereo and die charges extra at actuals for new designs.",
    ]:
        story += [Paragraph(term, body), Spacer(1, 1.2 * mm)]
    story += [Spacer(1, 4 * mm), Paragraph("Supplier questionnaire: our responses", heading), Spacer(1, 1.5 * mm)]
    answers = c.QUALITY["sribalaji"]["answers"]
    question_rows = [["No.", "Your question", "Our response"]]
    for qid, _mandatory, text in c.QUESTIONNAIRE:
        question_rows.append([qid, Paragraph(text, cell), Paragraph(answers[qid][1], cell)])
    story.append(
        Table(
            question_rows,
            colWidths=[10 * mm, 82 * mm, 83 * mm],
            repeatRows=1,
            style=TableStyle(
                [
                    ("FONT", (0, 0), (-1, 0), "Sans-Bold", 7.8),
                    ("FONT", (0, 1), (-1, -1), "Sans", 7.8),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EFE3E3")),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#8A8A8A")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            ),
        )
    )
    story += [
        Spacer(1, 5 * mm),
        Paragraph("Enclosure: MSDS for water-based flexographic inks.", body),
        Spacer(1, 7 * mm),
        Paragraph("Yours faithfully,<br/>for <b>Sri Balaji Corrugators</b><br/><br/><br/>K. Venkatesh<br/>Partner, Marketing", body),
    ]  # fmt: skip

    doc = BaseDocTemplate(
        str(path), pagesize=A4, invariant=1,
        leftMargin=18 * mm, rightMargin=18 * mm, topMargin=36 * mm, bottomMargin=18 * mm,
        title=f"Quotation {QUOTE_REF}", author="Sri Balaji Corrugators",
    )  # fmt: skip
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="main")
    doc.addPageTemplates([PageTemplate(id="letterhead", frames=[frame], onPage=letterhead)])
    doc.build(story)

    threshold = c.SRIBALAJI_DISCOUNT["threshold_inr"]
    by_rate = [l.line_id for l in c.LINES if quotes[l.line_id].raw_value > threshold]
    by_value = [l.line_id for l in c.LINES if quotes[l.line_id].raw_value * l.qty / 1000 > threshold]
    return {
        "files": [FILENAME],
        "lines": per_line,
        "footnotes": FOOTNOTES,
        "discount": {
            "text": FOOTNOTES[1],
            "locator": "page 2, footnote 2",
            "pct": c.SRIBALAJI_DISCOUNT["pct"],
            "vendor_intent": "rate_per_1000_above_threshold",
            "qualifying_lines_by_rate": by_rate,
            "qualifying_lines_by_line_value": by_value,
        },
        "freight_locator": "page 3, Commercial terms",
        "questionnaire_locators": {qid: "page 3, questionnaire table" for qid, _, _ in c.QUESTIONNAIRE},
    }


if __name__ == "__main__":
    out = build()
    print(out["lines"]["L04"], out["discount"]["qualifying_lines_by_rate"], len(out["discount"]["qualifying_lines_by_line_value"]))
