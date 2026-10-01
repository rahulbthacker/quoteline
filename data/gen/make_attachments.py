"""The three attached documents (brief section 1) plus Anand's filled questionnaire.

  Anand Papers           -> BRCGS certificate
  Sri Balaji Corrugators -> MSDS for flexographic inks
  Meridian Packaging     -> sample specification sheet

Every company and certificate number here is fabricated; each document says so in its footer.
"""

from __future__ import annotations

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

import catalog as c
from common import ATTACHMENTS
from make_sribalaji import register_fonts

DEMO_FOOTER = "Fabricated demonstration document for the Quoteline prototype. Not a real certificate or data sheet."

BRC = "Anand_BRCGS_Certificate.pdf"
MSDS = "SriBalaji_Ink_MSDS.pdf"
SPEC = "Meridian_Spec_Sheet.pdf"
ANAND_QUESTIONNAIRE = "Anand_Questionnaire_RFX-0147.pdf"


def _footer(canvas, _doc) -> None:
    canvas.saveState()
    canvas.setFont("Sans", 6.5)
    canvas.setFillColor(colors.HexColor("#777777"))
    canvas.drawCentredString(A4[0] / 2, 9 * mm, DEMO_FOOTER)
    canvas.restoreState()


def _doc(path, title: str, author: str) -> SimpleDocTemplate:
    return SimpleDocTemplate(
        str(path), pagesize=A4, invariant=1, title=title, author=author,
        leftMargin=20 * mm, rightMargin=20 * mm, topMargin=20 * mm, bottomMargin=18 * mm,
    )  # fmt: skip


def _styles() -> dict[str, ParagraphStyle]:
    return {
        "title": ParagraphStyle("title", fontName="Body-Bold", fontSize=17, leading=22, alignment=TA_CENTER),
        "centre": ParagraphStyle("centre", fontName="Body", fontSize=10.5, leading=16, alignment=TA_CENTER),
        "h": ParagraphStyle("h", fontName="Sans-Bold", fontSize=9.5, leading=13, spaceBefore=7, spaceAfter=2),
        "p": ParagraphStyle("p", fontName="Sans", fontSize=8.8, leading=12.2),
        "cell": ParagraphStyle("cell", fontName="Sans", fontSize=8.2, leading=10.5),
    }  # fmt: skip


def _grid(rows: list[list], widths: list[float]) -> Table:
    s = _styles()
    wrapped = [[Paragraph(str(value), s["cell"]) for value in row] for row in rows]
    return Table(
        wrapped,
        colWidths=widths,
        style=TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#8A8A8A")),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F0F0F0")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        ),
    )


def brc_certificate() -> None:
    s = _styles()
    story = [
        Spacer(1, 14 * mm),
        Paragraph("CERTIFICATE OF CONFORMITY", s["title"]),
        Spacer(1, 6 * mm),
        Paragraph("Northgate Assurance (India) Pvt Ltd certifies that, having conducted an audit of", s["centre"]),
        Spacer(1, 4 * mm),
        Paragraph("<b>ANAND PAPERS PRIVATE LIMITED</b>", s["title"]),
        Paragraph("Unit I: Plot 88, GIDC Phase III, Vapi 396195, Gujarat<br/>Unit II: Survey 214, Masat Industrial Estate, Silvassa 396230", s["centre"]),
        Spacer(1, 5 * mm),
        Paragraph("the sites meet the requirements of the", s["centre"]),
        Paragraph("<b>BRCGS Global Standard for Packaging Materials, Issue 6</b>", s["centre"]),
        Spacer(1, 6 * mm),
        _grid(
            [
                ["Certificate number", "BRC-PM-093357"],
                ["Grade achieved", "A"],
                ["Scope", "Manufacture of corrugated board, printed and plain corrugated boxes, sheets and die-cut items for food and non-food use"],
                ["Product category", "Paper and board making and conversion (hygiene category: high)"],
                ["Audit programme", "Announced"],
                ["Date of audit", "9 to 10 December 2025"],
                ["Certificate issue date", "14 January 2026"],
                ["Re-audit due", "from 12 November 2026 to 10 December 2026"],
                ["Certificate expiry date", "31 January 2027"],
            ],
            [55 * mm, 115 * mm],
        ),
        Spacer(1, 12 * mm),
        Paragraph("Authorised signatory, Northgate Assurance (India) Pvt Ltd", s["centre"]),
    ]  # fmt: skip
    _doc(ATTACHMENTS / BRC, "BRCGS certificate, Anand Papers", "Northgate Assurance").build(
        story, onFirstPage=_footer, onLaterPages=_footer
    )


def ink_msds() -> None:
    s = _styles()
    sections = [
        ("1. Identification", "Product: AQUAFLEX WB-200 series water-based flexographic ink. Use: printing on kraft and test liner for corrugated packaging. Supplier of the ink: Varnika Inks and Coatings, Hosur. Document held and issued to customers by Sri Balaji Corrugators."),
        ("2. Hazard identification", "Not classified as hazardous under GHS. May cause mild skin irritation on prolonged contact."),
        ("3. Composition", "Water 45 to 60%; acrylic polymer emulsion 20 to 30%; organic and inorganic pigments 10 to 18%; additives below 5%. Free of mineral oil, heavy-metal pigments, phthalate plasticisers, benzophenone and 4-methylbenzophenone."),
        ("4. First aid", "Eyes: rinse with water for 15 minutes. Skin: wash with soap and water. Ingestion: rinse mouth and seek medical advice."),
        ("5. Fire fighting", "Non-flammable water-based product. Use extinguishing media suited to the surrounding fire."),
        ("7. Handling and storage", "Store between 5 and 35 °C in closed containers. Shelf life 12 months."),
        ("9. Physical and chemical properties", "Liquid; pH 8.5 to 9.5; viscosity 20 to 25 s (Zahn cup 2); VOC content below 2%."),
        ("15. Regulatory information: food-contact packaging", "Formulated in accordance with the EuPIA Guideline on Printing Inks applied to the non-food-contact surface of food packaging and the EuPIA Good Manufacturing Practice. All intentionally added substances are listed in Swiss Ordinance SR 817.023.21, Annex 10. Conforms to IS 15495:2020, printing ink for food packaging, code of practice."),
        ("16. Other information", "Revision 4, dated 3 March 2026."),
    ]  # fmt: skip
    story = [Paragraph("MATERIAL SAFETY DATA SHEET", s["title"]), Spacer(1, 3 * mm)]
    for heading, text in sections:
        story += [Paragraph(heading, s["h"]), Paragraph(text, s["p"])]
    _doc(ATTACHMENTS / MSDS, "MSDS, water-based flexographic inks", "Sri Balaji Corrugators").build(
        story, onFirstPage=_footer, onLaterPages=_footer
    )


def spec_sheet() -> None:
    s = _styles()
    line = c.LINE_BY_ID["L01"]
    story = [
        Paragraph("MERIDIAN PACKAGING PVT LTD", s["title"]),
        Paragraph("Product specification sheet (sample)", s["centre"]),
        Spacer(1, 5 * mm),
        _grid(
            [
                ["Product code", "MP-5R-604040"],
                ["Description", "RSC Carton 5 Ply 150 GSM KLB, plain"],
                ["Internal dimensions (L x W x H)", "600 x 400 x 400 mm, tolerance ±3 mm"],
                ["Board construction", "150 KLB / 120 fluting (B) / 150 test liner / 120 fluting (C) / 150 KLB"],
                ["Flute combination", "BC double wall, combined calliper 6.5 mm ±0.3"],
                ["Board grammage", f"{line.board_gsm:.0f} g/m² ±5%"],
                ["Weight per box", f"{line.weight_kg:.3f} kg ±5%"],
                ["Bursting strength", "14 kg/cm² minimum"],
                ["Edge crush test (ECT)", "8.5 kN/m minimum"],
                ["Box compression test (BCT)", "480 kgf minimum"],
                ["Moisture content", "7 to 9% at despatch"],
                ["Cobb value (60 s)", "below 30 g/m², outer liner"],
                ["Joint", "Glued manufacturer's joint, 40 mm flap"],
                ["Bundling", "25 boxes per bundle, strapped; 600 boxes per pallet"],
                ["Test standards", "IS 1060, IS 2771 (Part 1), ISO 3037, ISO 12048"],
            ],
            [60 * mm, 110 * mm],
        ),
        Spacer(1, 5 * mm),
        Paragraph("Issued by Quality Assurance, Meridian Packaging, Chakan. Specification MP/QA/SPEC/5R-604040, revision 2, 11 August 2026.", s["p"]),
    ]  # fmt: skip
    _doc(ATTACHMENTS / SPEC, "Specification sheet MP-5R-604040", "Meridian Packaging").build(
        story, onFirstPage=_footer, onLaterPages=_footer
    )


def anand_questionnaire() -> bytes:
    """Returned as bytes: it travels inside Anand's email, not as a loose file."""
    import io

    register_fonts()
    s = _styles()
    answers = c.QUALITY["anand"]["answers"]
    rows = [["No.", "Question", "Supplier response"]]
    for qid, mandatory, text in c.QUESTIONNAIRE:
        rows.append([qid + (" *" if mandatory else ""), text, answers[qid][1]])
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, invariant=1, title=f"Supplier questionnaire {c.RFX_ID}", author="Anand Papers",
        leftMargin=20 * mm, rightMargin=20 * mm, topMargin=20 * mm, bottomMargin=18 * mm,
    )  # fmt: skip
    story = [
        Paragraph(f"Supplier questionnaire, {c.RFX_ID}", s["title"]),
        Paragraph(f"{c.BUYER['company']} · {c.RFX_TITLE} · items marked * are mandatory", s["centre"]),
        Spacer(1, 4 * mm),
        Paragraph("Supplier: Anand Papers Private Limited, Vapi. Completed by Vinod Anand, Director, on 24 September 2026.", s["p"]),
        Spacer(1, 3 * mm),
        _grid(rows, [14 * mm, 82 * mm, 74 * mm]),
    ]  # fmt: skip
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buffer.getvalue()


def build() -> dict:
    register_fonts()
    ATTACHMENTS.mkdir(parents=True, exist_ok=True)
    brc_certificate()
    ink_msds()
    spec_sheet()
    return {
        "anand": {"file": BRC, "kind": "BRC certificate", "delivered": "inside the email"},
        "sribalaji": {"file": MSDS, "kind": "MSDS for inks", "delivered": "alongside the quotation"},
        "meridian": {"file": SPEC, "kind": "sample spec sheet", "delivered": "alongside the offer"},
    }


if __name__ == "__main__":
    print(build())
