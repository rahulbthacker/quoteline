"""Anand Papers: a two-line email from the incumbent.

Breakage (brief section 7): "₹42/kg for the 5-ply, 38 for the 3-ply, rest same as last year,
freight extra". Per-kg prices need the RFx board weights; "rest" needs last year's contract
prices, and two of the "rest" lines are new this year so have none.
"""

from __future__ import annotations

from email.message import EmailMessage
from email.policy import SMTP

import catalog as c
from common import ATTACHMENTS, REPLIES
from make_attachments import ANAND_QUESTIONNAIRE, BRC, anand_questionnaire

FILENAME = "Anand_reply.eml"
LINE_1 = "₹42/kg for the 5-ply, 38 for the 3-ply, rest same as last year, freight extra."
LINE_2 = "Questionnaire answers and BRC cert attached."


def build() -> dict:
    vendor = c.VENDOR_BY_ID["anand"]
    message = EmailMessage(policy=SMTP)
    message["From"] = f"{vendor.contact} <{vendor.email}>"
    message["To"] = f"{c.BUYER['contact']} <{c.BUYER['email']}>"
    message["Subject"] = f"Re: {c.RFX_ID} {c.RFX_TITLE}: request for quotation"
    message["Date"] = "Thu, 24 Sep 2026 14:02:00 +0530"
    message["Message-ID"] = "<20260924140200.anand-0147@anandpapers.example>"
    message["In-Reply-To"] = f"<{c.RFX_ID.lower()}-anand@quoteline.local>"
    message.set_content(f"{LINE_1}\n{LINE_2}\n")
    message.add_attachment(
        anand_questionnaire(), maintype="application", subtype="pdf", filename=ANAND_QUESTIONNAIRE
    )
    message.add_attachment(
        (ATTACHMENTS / BRC).read_bytes(), maintype="application", subtype="pdf", filename=BRC
    )
    message.set_boundary("===============quoteline0147anand==")

    path = REPLIES / "anand" / FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(message.as_bytes())

    quotes = c.build_quotes()["anand"]
    per_line = {}
    for line in c.LINES:
        quote = quotes[line.line_id]
        if quote.how == "per_kg":
            snippet = "₹42/kg for the 5-ply" if line.ply == 5 else "38 for the 3-ply"
        else:
            snippet = "rest same as last year"
        per_line[line.line_id] = {
            "locator": "email body, line 1",
            "raw_text": snippet,
            "vendor_description": f"{line.ply}-ply" if quote.how == "per_kg" else "rest",
        }
    return {
        "files": [FILENAME],
        "lines": per_line,
        "body": [LINE_1, LINE_2],
        "embedded_attachments": [ANAND_QUESTIONNAIRE, BRC],
        "statements": [
            {"kind": "per_kg_rate", "text": "₹42/kg for the 5-ply", "rate_inr_per_kg": 42.0, "applies_to": "ply == 5"},
            {"kind": "per_kg_rate", "text": "38 for the 3-ply", "rate_inr_per_kg": 38.0, "applies_to": "ply == 3"},
            {"kind": "same_as_last_year", "text": "rest same as last year", "applies_to": "all other lines"},
            {"kind": "freight", "text": "freight extra", "applies_to": "all lines"},
        ],
        "freight_locator": "email body, line 1",
        "questionnaire_locators": {qid: f"{ANAND_QUESTIONNAIRE}, row {qid}" for qid, _, _ in c.QUESTIONNAIRE},
    }


if __name__ == "__main__":
    print(build()["lines"]["L04"])
