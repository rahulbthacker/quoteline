"""Single source of truth for the fabricated dataset.

Everything a vendor file says and everything the golden set asserts is derived from the
structures in this module, so truth is exact by construction. The generator is deterministic:
the same seed always yields the same prices.

Pricing model (so a procurement person would nod):
  board weight per piece = blank area (from style and dimensions) x board grammage
  market price per piece = board weight x conversion rate per kg for the ply x style premium
  vendor price           = market x vendor positioning x small per-line noise,
                           rounded the way that vendor writes prices.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date

SEED = 147
RFX_ID = "RFX-0147"
RFX_TITLE = "Corrugated packaging, Q4 2026"
FX_USD_INR = 83.42
FX_AS_OF = date(2026, 9, 26)
SENT_ON = date(2026, 9, 18)

BUYER = {
    "company": "Sahyadri Foods Pvt Ltd",
    "address": "Plot 14, MIDC Phase II, Chakan, Pune 410501",
    "contact": "Rahul Thacker",
    "title": "Category Buyer, Packaging",
    "email": "rahul.thacker@sahyadrifoods.example",
}

FLUTE_GSM = 120
FLUTE_TAKE_UP = 1.40
GLUE_FLAP_MM = 40
# Conversion cost per kg of finished board, by ply (kraft, 2026 market).
RATE_PER_KG = {3: 37.6, 5: 41.6, 7: 45.5}
PRINT_PREMIUM = {None: 0.0, "1 colour": 0.02, "2 colour": 0.04}
STYLE_PREMIUM = {
    "rsc": 0.0, "hsc": 0.0, "sheet": 0.0, "tray": 0.05, "mailer": 0.05,
    "display": 0.05, "pad": 0.03, "partition": 0.03, "telescopic": 0.04,
}  # fmt: skip


@dataclass(frozen=True)
class Line:
    line_id: str
    description: str  # as written in the RFx
    style: str  # rsc | hsc | sheet | tray | mailer | display | pad | partition | telescopic | other
    ply: int | None
    gsm: int | None
    dims: tuple[int, ...] | None
    print_: str | None
    qty: int
    uom: str = "pcs"
    weight_override_kg: float | None = None
    price_override_per_pc: float | None = None
    new_this_year: bool = False

    @property
    def board_gsm(self) -> float:
        liners = self.ply // 2 + 1
        flutes = self.ply // 2
        return liners * self.gsm + flutes * FLUTE_GSM * FLUTE_TAKE_UP

    @property
    def blank_area_m2(self) -> float:
        d = self.dims
        if self.style == "rsc":
            length, width, height = d
            return (2 * (length + width) + GLUE_FLAP_MM) * (height + width) / 1e6
        if self.style == "hsc":
            length, width, height = d
            return (2 * (length + width) + GLUE_FLAP_MM) * (height + width / 2) / 1e6
        if self.style in ("tray", "display"):
            length, width, height = d
            return (length + 2 * height + 40) * (width + 2 * height + 40) / 1e6
        if self.style == "mailer":
            length, width, height = d
            return (length + 2 * height + 60) * (2 * width + 3 * height + 40) / 1e6
        if self.style == "telescopic":
            length, width, height = d
            base = (length + 2 * height + 40) * (width + 2 * height + 40)
            lid = (length + 10 + 2 * height + 40) * (width + 10 + 2 * height + 40)
            return (base + lid) / 1e6
        if self.style in ("sheet", "pad"):
            return d[0] * d[1] / 1e6
        raise ValueError(f"no blank formula for style {self.style}")

    @property
    def weight_kg(self) -> float:
        """Board weight per piece, as published in the RFx spec."""
        if self.weight_override_kg is not None:
            return self.weight_override_kg
        return round(self.blank_area_m2 * self.board_gsm / 1000, 3)

    @property
    def market_per_pc(self) -> float:
        if self.price_override_per_pc is not None:
            return self.price_override_per_pc
        premium = 1 + PRINT_PREMIUM[self.print_] + STYLE_PREMIUM[self.style]
        return self.weight_kg * RATE_PER_KG[self.ply] * premium

    @property
    def group(self) -> str:
        return {3: "3-ply", 5: "5-ply", 7: "7-ply"}.get(self.ply, "ancillary")


LINES: list[Line] = [
    Line("L01", "5-ply RSC box 600×400×400, 150 GSM KLB", "rsc", 5, 150, (600, 400, 400), None, 65_000),
    Line("L02", "3-ply RSC box 400×300×300, 120 GSM", "rsc", 3, 120, (400, 300, 300), None, 180_000),
    Line("L03", "5-ply die-cut tray 500×350×120, 150 GSM", "tray", 5, 150, (500, 350, 120), None, 75_000),
    Line("L04", "7-ply export carton 650×450×450, 180 GSM", "rsc", 7, 180, (650, 450, 450), None, 11_000),
    Line("L05", "Corrugated sheet 5-ply 1200×1000, 150 GSM", "sheet", 5, 150, (1200, 1000), None, 30_000),
    Line("L06", "Partition set, 3-ply, 12 cell, for 400×300×300 box", "partition", 3, 120, None, None, 110_000, "sets", weight_override_kg=0.210),
    Line("L07", "3-ply mailer 250×200×100, 120 GSM, printed 1 colour", "mailer", 3, 120, (250, 200, 100), "1 colour", 130_000),
    Line("L08", "Edge protector 50×50×3 mm, 600 mm long", "other", None, None, (50, 50, 3, 600), None, 70_000, weight_override_kg=0.135, price_override_per_pc=6.10),
    Line("L09", "3-ply RSC box 300×200×200, 120 GSM", "rsc", 3, 120, (300, 200, 200), None, 215_000),
    Line("L10", "3-ply RSC box 450×300×250, 120 GSM, printed 1 colour", "rsc", 3, 120, (450, 300, 250), "1 colour", 120_000),
    Line("L11", "3-ply RSC box 350×250×200, 140 GSM, printed 2 colour", "rsc", 3, 140, (350, 250, 200), "2 colour", 140_000),
    Line("L12", "3-ply die-cut shelf-ready tray 400×300×100, 140 GSM, printed 2 colour", "tray", 3, 140, (400, 300, 100), "2 colour", 100_000),
    Line("L13", "3-ply layer pad 390×290, 120 GSM", "pad", 3, 120, (390, 290), None, 340_000),
    Line("L14", "Corrugated sheet 3-ply 1000×800, 120 GSM", "sheet", 3, 120, (1000, 800), None, 50_000),
    Line("L15", "5-ply RSC box 500×400×300, 150 GSM, printed 1 colour", "rsc", 5, 150, (500, 400, 300), "1 colour", 70_000),
    Line("L16", "5-ply RSC box 450×350×350, 150 GSM", "rsc", 5, 150, (450, 350, 350), None, 60_000),
    Line("L17", "5-ply RSC box 550×350×300, 180 GSM, printed 2 colour", "rsc", 5, 180, (550, 350, 300), "2 colour", 48_000),
    Line("L18", "5-ply RSC box 400×400×400, 150 GSM", "rsc", 5, 150, (400, 400, 400), None, 52_000),
    Line("L19", "5-ply RSC box 700×450×350, 180 GSM", "rsc", 5, 180, (700, 450, 350), None, 26_000),
    Line("L20", "5-ply die-cut display shipper 600×400×200, 150 GSM, printed 2 colour", "display", 5, 150, (600, 400, 200), "2 colour", 22_000),
    Line("L21", "5-ply HSC 600×400×300, 150 GSM", "hsc", 5, 150, (600, 400, 300), None, 35_000),
    Line("L22", "Partition set, 5-ply, 6 cell, for 600×400×400 box", "partition", 5, 150, None, None, 65_000, "sets", weight_override_kg=0.520),
    Line("L23", "5-ply telescopic box 500×300×150, base and lid, 150 GSM", "telescopic", 5, 150, (500, 300, 150), None, 26_000),
    Line("L24", "7-ply export carton 600×450×400, 180 GSM", "rsc", 7, 180, (600, 450, 400), None, 9_500),
    Line("L25", "7-ply export carton 600×400×450, 180 GSM, printed 1 colour", "rsc", 7, 180, (600, 400, 450), "1 colour", 8_000, new_this_year=True),
    Line("L26", "Edge protector 40×40×4 mm, 1000 mm long", "other", None, None, (40, 40, 4, 1000), None, 35_000, weight_override_kg=0.245, price_override_per_pc=9.60),
    Line("L27", "Honeycomb pallet pad 1200×1000×20 mm", "other", None, None, (1200, 1000, 20), None, 6_000, weight_override_kg=1.900, price_override_per_pc=78.00, new_this_year=True),
    Line("L28", "Corner post 80×80×5 mm, 900 mm long", "other", None, None, (80, 80, 5, 900), None, 18_000, weight_override_kg=0.520, price_override_per_pc=15.20),
    Line("L29", "3-ply die-cut insert pad 380×280, 120 GSM", "pad", 3, 120, (380, 280), None, 190_000),
    Line("L30", "3-ply RSC box 250×200×150, 120 GSM", "rsc", 3, 120, (250, 200, 150), None, 165_000),
]  # fmt: skip
LINE_BY_ID = {line.line_id: line for line in LINES}

QUESTIONNAIRE = [
    ("Q1", True, "Do you hold a valid BRCGS Packaging Materials certificate, or an equivalent GFSI-recognised certification (FSSC 22000, ISO 22000)? State certificate number and expiry."),
    ("Q2", True, "Are the printing inks used on our packaging compliant for food-contact packaging? Name the standard (EuPIA GMP, Swiss Ordinance Annex 10 or IS 15495). An ink MSDS may be requested before award."),
    ("Q3", True, "How many production sites can supply this contract? A minimum of two is required for continuity of supply."),
    ("Q4", False, "What is your standard lead time from purchase order to delivery, in days?"),
    ("Q5", False, "What is your installed monthly conversion capacity, in tonnes?"),
    ("Q6", False, "Do you accept payment terms of 60 days from receipt of material?"),
    ("Q7", False, "What recycled fibre content do you offer, and do you hold FSC chain-of-custody certification?"),
    ("Q8", False, "Can you hold two weeks of safety stock at your warehouse at your cost?"),
]  # fmt: skip


@dataclass(frozen=True)
class Vendor:
    vendor_id: str
    name: str
    contact: str
    email: str
    city: str
    reply_format: str
    received_at: str  # ISO, IST


VENDORS = [
    Vendor("meridian", "Meridian Packaging", "Sneha Kulkarni", "sales@meridianpackaging.example", "Pune", "xlsx", "2026-09-22T11:18:00+05:30"),
    Vendor("sribalaji", "Sri Balaji Corrugators", "K. Venkatesh", "quotes@sribalajicorrugators.example", "Sivakasi", "pdf", "2026-09-23T16:45:00+05:30"),
    Vendor("kaveri", "Kaveri Boards", "Arun Subramanian", "exports@kaveriboards.example", "Chennai", "docx", "2026-09-25T10:07:00+05:30"),
    Vendor("northbox", "NorthBox Ltd", "Imran Shaikh", "imran@northbox.example", "Bhiwandi", "image", "2026-09-26T18:32:00+05:30"),
    Vendor("anand", "Anand Papers", "Vinod Anand", "vinod@anandpapers.example", "Vapi", "eml", "2026-09-24T14:02:00+05:30"),
]  # fmt: skip
VENDOR_BY_ID = {vendor.vendor_id: vendor for vendor in VENDORS}

# Lines a vendor does not quote.
NOT_QUOTED = {
    "kaveri": {"L27"},  # says so in the letter
    "northbox": {"L08", "L26", "L27"},  # silently absent from the rate card
}

# Vendor positioning against market: base factor plus adjustments by line group or style.
POSITIONING = {
    "meridian": {"base": 1.010, "tray": -0.07, "display": -0.07, "mailer": -0.065, "telescopic": -0.04, "printed": -0.03, "7-ply": 0.02},
    "sribalaji": {"base": 0.992, "7-ply": -0.02, "ancillary": -0.01},
    "kaveri": {"base": 1.032, "sheet": -0.09, "pad": -0.085, "partition": -0.04},
    "northbox": {"base": 0.996, "3-ply": -0.04},
}  # fmt: skip
NOISE = 0.035

ANAND_RATE_PER_KG = {5: 42.0, 3: 38.0}
LAST_YEAR_UPLIFT = 1.062  # last year's contract sat about 6% above this year's market

# NorthBox rate card: a blot covers the left half of one digit in the photo, so the tens
# digit of the L05 rate reads as either 3 or 8.
NORTHBOX_AMBIGUOUS = {"line_id": "L05", "true": 3935, "alt": 3985, "digit_index": 2}

SRIBALAJI_DISCOUNT = {"pct": 4.0, "threshold_inr": 100_000}


def _round_to(value: float, step: float) -> float:
    return round(round(value / step) * step, 2)


@dataclass
class Quote:
    """One vendor's statement about one line, in the vendor's own terms."""

    line_id: str
    quoted: bool
    how: str  # explicit | per_kg | carry_forward | carry_forward_unresolved | not_quoted
    raw_value: float | None = None
    raw_unit: str | None = None  # per_pc | per_100 | per_1000 | per_kg | per_box
    raw_currency: str | None = None
    true_inr_per_1000: float | None = None
    notes: list[str] = field(default_factory=list)


def last_year_prices() -> dict[str, float | None]:
    rng = random.Random(SEED + 1)
    prices: dict[str, float | None] = {}
    for line in LINES:
        jitter = 1 + rng.uniform(-0.012, 0.012)
        value = _round_to(line.market_per_pc * 1000 * LAST_YEAR_UPLIFT * jitter, 50)
        prices[line.line_id] = None if line.new_this_year else value
    return prices


def _factor(vendor_id: str, line: Line, rng: random.Random) -> float:
    pos = POSITIONING[vendor_id]
    factor = pos["base"] + pos.get(line.group, 0.0) + pos.get(line.style, 0.0)
    if line.print_:
        factor += pos.get("printed", 0.0)
    return factor * (1 + rng.uniform(-NOISE, NOISE))


def build_quotes() -> dict[str, dict[str, Quote]]:
    """Every vendor's quote for every line, with exact normalised truth."""
    quotes: dict[str, dict[str, Quote]] = {}
    last_year = last_year_prices()

    for vendor_id in ("meridian", "sribalaji", "kaveri", "northbox"):
        rng = random.Random(f"{SEED}-{vendor_id}")
        per_vendor: dict[str, Quote] = {}
        for line in LINES:
            target_per_pc = line.market_per_pc * _factor(vendor_id, line, rng)
            if line.line_id in NOT_QUOTED.get(vendor_id, set()):
                per_vendor[line.line_id] = Quote(line.line_id, False, "not_quoted")
                continue
            if vendor_id == "meridian":  # INR per piece, two decimals
                raw = round(target_per_pc, 2)
                quote = Quote(line.line_id, True, "explicit", raw, "per_pc", "INR", round(raw * 1000, 2))
            elif vendor_id == "sribalaji":  # INR per 1,000, rounded to 10
                raw = _round_to(target_per_pc * 1000, 10)
                quote = Quote(line.line_id, True, "explicit", raw, "per_1000", "INR", raw)
            elif vendor_id == "kaveri":  # USD per thousand, rounded to 0.05; L01 per box
                if line.line_id == "L01":
                    raw = round(target_per_pc / FX_USD_INR, 2)
                    quote = Quote(line.line_id, True, "explicit", raw, "per_box", "USD", round(raw * 1000 * FX_USD_INR, 2))
                    quote.notes.append("per box with 'packed 100 per bundle' in the same sentence")
                else:
                    raw = _round_to(target_per_pc * 1000 / FX_USD_INR, 0.05)
                    quote = Quote(line.line_id, True, "explicit", raw, "per_1000", "USD", round(raw * FX_USD_INR, 2))
            else:  # northbox: INR per 100, rounded to 5
                raw = _round_to(target_per_pc * 100, 5)
                if line.line_id == NORTHBOX_AMBIGUOUS["line_id"]:
                    raw = float(NORTHBOX_AMBIGUOUS["true"])
                quote = Quote(line.line_id, True, "explicit", raw, "per_100", "INR", round(raw * 10, 2))
            per_vendor[line.line_id] = quote
        quotes[vendor_id] = per_vendor

    anand: dict[str, Quote] = {}
    for line in LINES:
        if line.ply in ANAND_RATE_PER_KG:
            rate = ANAND_RATE_PER_KG[line.ply]
            anand[line.line_id] = Quote(
                line.line_id, True, "per_kg", rate, "per_kg", "INR",
                round(rate * line.weight_kg * 1000, 2),
            )  # fmt: skip
        elif last_year[line.line_id] is not None:
            anand[line.line_id] = Quote(
                line.line_id, True, "carry_forward", None, None, "INR", last_year[line.line_id]
            )
        else:
            anand[line.line_id] = Quote(line.line_id, True, "carry_forward_unresolved")
            anand[line.line_id].notes.append("'rest same as last year' but no last-year price exists")
    quotes["anand"] = anand
    return quotes


FREIGHT = {
    "meridian": {"kind": "included", "amount_inr": None, "statement": "Rates are delivered to your Chakan plant; freight is included."},
    "sribalaji": {"kind": "lump_sum", "amount_inr": 520_000, "statement": "Freight extra at ₹5,20,000 lump sum for the contract period, delivered Chakan."},
    "kaveri": {"kind": "fob_not_stated", "amount_inr": None, "statement": "FOB Chennai; onward freight to Pune is to the buyer's account."},
    "northbox": {"kind": "lump_sum", "amount_inr": 410_000, "statement": "Transport extra: ₹4,10,000 for the full contract quantity, delivery Chakan."},
    "anand": {"kind": "extra_unpriced", "amount_inr": None, "statement": "freight extra"},
}  # fmt: skip

# Questionnaire truth: (expected verdict, the text the vendor actually writes or None if silent).
QUALITY = {
    "meridian": {
        "result": "Pass",
        "answers": {
            "Q1": ("pass", "BRCGS Packaging Materials Issue 6, Grade AA, certificate no. BRC-PM-118204, valid to 14 March 2027."),
            "Q2": ("pass", "All inks are water-based flexo inks compliant with EuPIA GMP and IS 15495. MSDS available on request."),
            "Q3": ("pass", "Two plants: Chakan (Pune) and Sinnar (Nashik). Either plant can run the full range."),
            "Q4": ("answered", "10 working days from PO; 5 days for repeat items held as board stock."),
            "Q5": ("answered", "2,400 tonnes per month across both plants."),
            "Q6": ("answered", "Yes, 60 days from GRN is acceptable."),
            "Q7": ("answered", "70 to 85% recycled fibre depending on grade. FSC chain of custody held, licence FSC-C151902."),
            "Q8": ("answered", "Yes, two weeks of safety stock at Chakan at our cost."),
        },
    },
    "sribalaji": {
        "result": "Pass",
        "answers": {
            "Q1": ("pass", "FSSC 22000 (Version 6) for packaging manufacture, certificate no. FSSC-IN-447731, valid until 30 June 2027."),
            "Q2": ("pass", "Yes. Water-based flexographic inks conforming to Swiss Ordinance Annex 10 and IS 15495. MSDS enclosed."),
            "Q3": ("pass", "Three units: Sivakasi (Unit I and Unit II) and Hosur."),
            "Q4": ("answered", "12 days from receipt of PO."),
            "Q5": ("answered", "3,100 tonnes per month."),
            "Q6": ("answered", "45 days preferred; 60 days acceptable against LC or with 1% loading."),
            "Q7": ("answered", "Minimum 80% recycled fibre. FSC certification in progress."),
            "Q8": ("answered", "Safety stock of 10 days can be held at Hosur."),
        },
    },
    "kaveri": {
        "result": "Partial",
        "answers": {
            "Q1": ("unanswered", None),
            "Q2": ("pass", "all our inks are water-based and compliant with EuPIA good manufacturing practice for food packaging"),
            "Q3": ("pass", "We run two plants, at Sriperumbudur near Chennai and at Hosur"),
            "Q4": ("answered", "Shipment is within 15 days of a confirmed order"),
            "Q5": ("answered", "combined capacity is 1,800 tonnes a month"),
            "Q6": ("answered", "Payment by 30-day letter of credit"),
            "Q7": ("unanswered", None),
            "Q8": ("unanswered", None),
        },
    },
    "northbox": {
        "result": "Fail",
        "answers": {
            "Q1": ("unanswered", "ISO 9001:2015"),  # a quality-management cert, not a GFSI food-safety one
            "Q2": ("unanswered", "Water based flexo inks"),  # no compliance statement
            "Q3": ("fail", "Works: single unit at Bhiwandi, Dist. Thane"),
            "Q4": ("answered", "Delivery 7 days"),
            "Q5": ("unanswered", None),
            "Q6": ("answered", "Payment 30 days"),
            "Q7": ("unanswered", None),
            "Q8": ("unanswered", None),
        },
    },
    "anand": {
        "result": "Pass",
        "answers": {
            "Q1": ("pass", "Yes. BRCGS Packaging Materials Issue 6, Grade A, certificate no. BRC-PM-093357, expiry 31 January 2027. Copy attached."),
            "Q2": ("pass", "Yes. Inks comply with EuPIA GMP and IS 15495."),
            "Q3": ("pass", "Two units: Vapi (Unit I) and Silvassa (Unit II)."),
            "Q4": ("answered", "8 days."),
            "Q5": ("answered", "1,500 tonnes."),
            "Q6": ("answered", "Yes, as per current contract."),
            "Q7": ("answered", "75% recycled. No FSC."),
            "Q8": ("answered", "Yes, as we do today."),
        },
    },
}  # fmt: skip


def money(value: float, decimals: int = 0) -> str:
    """Indian digit grouping: 1,18,000."""
    negative = value < 0
    value = abs(value)
    whole, _, frac = f"{value:.{decimals}f}".partition(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups + [tail])
    text = whole + (f".{frac}" if decimals else "")
    return f"-{text}" if negative else text


def summary() -> str:
    """Human-readable check that the dataset tells a coherent story."""
    quotes = build_quotes()
    last_year = last_year_prices()
    out = []
    totals = {v: 0.0 for v in quotes}
    covered = {v: 0 for v in quotes}
    wins_all = {v: 0 for v in quotes}
    wins_pass = {v: 0 for v in quotes}
    split_all = split_pass = last_year_total = 0.0
    passers = [v for v in quotes if QUALITY[v]["result"] == "Pass"]
    out.append(f"{'line':<5}{'wt kg':>7}{'market':>10}" + "".join(f"{v:>11}" for v in quotes) + f"{'lastyr':>10}")
    for line in LINES:
        prices = {v: quotes[v][line.line_id].true_inr_per_1000 for v in quotes}
        row = f"{line.line_id:<5}{line.weight_kg:>7.3f}{line.market_per_pc * 1000:>10.0f}"
        for v, price in prices.items():
            row += f"{price:>11.0f}" if price is not None else f"{'-':>11}"
            if price is not None:
                totals[v] += price * line.qty / 1000
                covered[v] += 1
        ly = last_year[line.line_id]
        row += f"{ly:>10.0f}" if ly else f"{'new':>10}"
        out.append(row)
        valid = {v: p for v, p in prices.items() if p is not None}
        best = min(valid, key=valid.get)
        wins_all[best] += 1
        split_all += valid[best] * line.qty / 1000
        valid_pass = {v: p for v, p in valid.items() if v in passers}
        best_pass = min(valid_pass, key=valid_pass.get)
        wins_pass[best_pass] += 1
        split_pass += valid_pass[best_pass] * line.qty / 1000
        if ly:
            last_year_total += ly * line.qty / 1000
    out.append("")
    for v in quotes:
        out.append(
            f"{v:<10} total ₹{totals[v] / 1e7:.3f} Cr on {covered[v]} lines · wins(all) {wins_all[v]:>2}"
            f" · wins(pass-only) {wins_pass[v]:>2} · quality {QUALITY[v]['result']}"
        )
    out.append(f"split, all vendors  ₹{split_all / 1e7:.3f} Cr")
    out.append(f"split, pass only    ₹{split_pass / 1e7:.3f} Cr")
    out.append(f"last year (28 lines) ₹{last_year_total / 1e7:.3f} Cr")
    return "\n".join(out)


if __name__ == "__main__":
    print(summary())
