"""NorthBox Ltd: a phone photo of a printed rate card.

Breakage (brief section 7): 14 degree skew, slight blur, 27 of 30 lines (three rows are simply
absent), one digit that is physically smudged so that it reads as either a 1 or a 7, and a
company footer that fails the two-site requirement.
"""

from __future__ import annotations

import math
import random

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

import catalog as c
from common import REPLIES, font_path

FILENAME = "NorthBox_ratecard.jpg"
PAPER_W, PAPER_H = 1654, 2339  # A4 at 200 dpi
CANVAS_W, CANVAS_H = 2400, 2900
SKEW_DEG = 14.0
ROW_H = 53
TABLE_TOP = 392
COLS = [("Sr", 96, 86), ("Item", 182, 560), ("Size (mm)", 742, 330), ("Ply / GSM", 1072, 190), ("Rate ₹ / 100 pcs", 1262, 296)]
INK = (28, 28, 34)


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(font_path("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"), size)


def item_name(line: c.Line) -> str:
    printed = {None: "", "1 colour": ", 1 col print", "2 colour": ", 2 col print"}[line.print_]
    names = {
        "rsc": "RSC Box", "hsc": "HSC Box (no top flaps)", "sheet": "Plain Sheet",
        "telescopic": "Telescopic Box (base+lid)", "mailer": "Mailer Box", "display": "Display Shipper",
    }  # fmt: skip
    if line.ply == 7:
        return "Export Carton HD" + printed
    if line.style == "tray":
        return ("SRP Tray die-cut" if "shelf-ready" in line.description else "Tray die-cut") + printed
    if line.style == "pad":
        return "Insert Pad die-cut" if "insert" in line.description else "Layer Pad"
    if line.style == "partition":
        return "Partition Set " + ("12 cell" if "12 cell" in line.description else "6 cell")
    if line.line_id == "L28":
        return "Corner Post 80x80x5"
    return names[line.style] + printed


def size_text(line: c.Line) -> str:
    if line.style == "partition":
        return "for " + line.description.split("for ")[1].replace("×", "x").replace(" box", "")
    if line.line_id == "L28":
        return "L 900"
    return "x".join(str(d) for d in line.dims[:3])


def ply_text(line: c.Line) -> str:
    return f"{line.ply} / {line.gsm}" if line.ply else "-"


def rate_text(value: float) -> str:
    return c.money(value)


def to_photo_xy(x: float, y: float, offset: tuple[int, int]) -> tuple[float, float]:
    """Map a paper coordinate to the final photo after pasting and rotating the canvas."""
    px, py = x + offset[0], y + offset[1]
    cx, cy = CANVAS_W / 2, CANVAS_H / 2
    theta = math.radians(SKEW_DEG)
    dx, dy = px - cx, py - cy
    return (cx + dx * math.cos(theta) + dy * math.sin(theta), cy - dx * math.sin(theta) + dy * math.cos(theta))


def build() -> dict:
    quotes = c.build_quotes()["northbox"]
    rng = random.Random(c.SEED + 7)
    paper = Image.new("RGB", (PAPER_W, PAPER_H), (250, 249, 244))
    draw = ImageDraw.Draw(paper)

    # Letterhead.
    draw.rectangle([90, 86, 150, 146], outline=(20, 70, 140), width=6)
    draw.rectangle([108, 104, 168, 164], outline=(20, 70, 140), width=6)
    draw.text((196, 84), "NORTHBOX LTD", font=font(60, True), fill=(20, 70, 140))
    draw.text((198, 156), "Corrugated Boxes · Cartons · Sheets · Die-cut Items", font=font(25), fill=INK)
    draw.text((90, 204), "Gala 7, Rajlaxmi Complex, Kalher, Bhiwandi, Dist. Thane 421302 · Mob. 98190 55 0173", font=font(23), fill=INK)
    draw.line([90, 248, PAPER_W - 90, 248], fill=(20, 70, 140), width=4)
    draw.text((90, 270), "RATE CARD", font=font(38, True), fill=INK)
    draw.text((90, 322), f"For: {c.BUYER['company']}, Chakan  ·  Your enquiry {c.RFX_ID}", font=font(25), fill=INK)
    draw.text((PAPER_W - 90, 278), "Date: 26/09/2026", font=font(25), fill=INK, anchor="ra")

    # Table header.
    table_right = COLS[-1][1] + COLS[-1][2]
    draw.rectangle([COLS[0][1], TABLE_TOP, table_right, TABLE_TOP + ROW_H], fill=(225, 232, 242), outline=INK, width=2)
    for title, x, width in COLS:
        anchor_x = x + width - 14 if title.startswith("Rate") else x + 12
        draw.text((anchor_x, TABLE_TOP + ROW_H / 2), title, font=font(25, True), fill=INK, anchor="rm" if title.startswith("Rate") else "lm")

    per_line: dict[str, dict] = {}
    boxes: dict[str, tuple[float, float, float, float]] = {}
    ambiguous_box = None
    y = TABLE_TOP + ROW_H
    row_font, rate_font = font(27), font(29)
    quoted = [line for line in c.LINES if quotes[line.line_id].quoted]
    for line in quoted:
        quote = quotes[line.line_id]
        number = int(line.line_id[1:])
        cells = [str(number), item_name(line), size_text(line), ply_text(line)]
        for (_title, x, _width), text in zip(COLS[:4], cells, strict=True):
            draw.text((x + 12, y + ROW_H / 2), text, font=row_font, fill=INK, anchor="lm")
        text = rate_text(quote.raw_value)
        right = COLS[4][1] + COLS[4][2] - 14
        text_width = draw.textlength(text, font=rate_font)
        left = right - text_width
        if line.line_id == c.NORTHBOX_AMBIGUOUS["line_id"]:
            ambiguous_box = _draw_ambiguous(paper, draw, text, left, y + ROW_H / 2, rate_font, rng)
        else:
            draw.text((left, y + ROW_H / 2), text, font=rate_font, fill=INK, anchor="lm")
        draw.line([COLS[0][1], y + ROW_H, table_right, y + ROW_H], fill=(120, 120, 126), width=1)
        boxes[line.line_id] = (COLS[4][1], y, table_right, y + ROW_H)
        per_line[line.line_id] = {
            "locator": f"rate card row Sr {number}",
            "raw_text": text,
            "vendor_description": f"{item_name(line)} {size_text(line)} {ply_text(line)}",
        }
        y += ROW_H
    table_bottom = y
    for _title, x, _width in COLS:
        draw.line([x, TABLE_TOP, x, table_bottom], fill=INK, width=2)
    draw.line([table_right, TABLE_TOP, table_right, table_bottom], fill=INK, width=2)
    draw.line([COLS[0][1], table_bottom, table_right, table_bottom], fill=INK, width=2)

    # Footer: terms and the company details that answer (or fail) the questionnaire.
    answers = c.QUALITY["northbox"]["answers"]
    footer = [
        "Rates are per 100 pcs. GST 18% extra. Rates valid 30 days.",
        c.FREIGHT["northbox"]["statement"],
        f"{answers['Q6'][1]}. {answers['Q4'][1]}.",
        f"{answers['Q3'][1]}  ·  {answers['Q1'][1]}  ·  {answers['Q2'][1]}",
    ]
    fy = table_bottom + 34
    for text in footer:
        draw.text((96, fy), text, font=font(24), fill=INK)
        fy += 40
    draw.text((PAPER_W - 96, fy + 70), "For NorthBox Ltd", font=font(24), fill=INK, anchor="ra")
    stamp = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
    stamp_draw = ImageDraw.Draw(stamp)
    stamp_draw.ellipse([14, 14, 286, 286], outline=(40, 60, 150, 150), width=7)
    stamp_draw.text((150, 120), "NORTHBOX LTD", font=font(27, True), fill=(40, 60, 150, 150), anchor="mm")
    stamp_draw.text((150, 172), "BHIWANDI", font=font(25, True), fill=(40, 60, 150, 150), anchor="mm")
    stamp = stamp.rotate(-11, resample=Image.BICUBIC)
    paper.paste(stamp, (PAPER_W - 620, int(fy) - 20), stamp)

    # Photograph it: desk, shadow, skew, uneven light, blur, sensor noise, JPEG.
    desk = np.zeros((CANVAS_H, CANVAS_W, 3), dtype=np.float32)
    desk[:] = (96, 72, 52)
    grain_rng = np.random.default_rng(c.SEED)
    streaks = grain_rng.normal(0, 7, size=(1, CANVAS_W, 1)).repeat(CANVAS_H, axis=0)
    desk += streaks + grain_rng.normal(0, 3, size=desk.shape)
    canvas = Image.fromarray(np.clip(desk, 0, 255).astype(np.uint8))
    offset = ((CANVAS_W - PAPER_W) // 2, (CANVAS_H - PAPER_H) // 2)
    shadow = Image.new("L", canvas.size, 0)
    ImageDraw.Draw(shadow).rectangle(
        [offset[0] + 18, offset[1] + 22, offset[0] + PAPER_W + 18, offset[1] + PAPER_H + 22], fill=150
    )
    canvas = Image.composite(Image.new("RGB", canvas.size, (30, 22, 16)), canvas, shadow.filter(ImageFilter.GaussianBlur(16)))
    canvas.paste(paper, offset)
    photo = canvas.rotate(SKEW_DEG, resample=Image.BICUBIC, fillcolor=(96, 72, 52))

    pixels = np.asarray(photo).astype(np.float32)
    ys, xs = np.mgrid[0:CANVAS_H, 0:CANVAS_W]
    light = 1.06 - 0.26 * ((xs / CANVAS_W) * 0.55 + (ys / CANVAS_H) * 0.45)  # window at top left
    pixels *= light[..., None]
    pixels[..., 0] *= 1.03  # warm indoor white balance
    pixels[..., 2] *= 0.95
    photo = Image.fromarray(np.clip(pixels, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.25))
    pixels = np.asarray(photo).astype(np.float32) + grain_rng.normal(0, 3.2, size=pixels.shape)
    photo = Image.fromarray(np.clip(pixels, 0, 255).astype(np.uint8))

    path = REPLIES / "northbox" / FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    photo.save(path, "JPEG", quality=80, subsampling=2)

    def photo_bbox(box: tuple[float, float, float, float]) -> list[int]:
        corners = [to_photo_xy(x, y, offset) for x in (box[0], box[2]) for y in (box[1], box[3])]
        xs_, ys_ = [p[0] for p in corners], [p[1] for p in corners]
        return [int(min(xs_)), int(min(ys_)), int(max(xs_)) + 1, int(max(ys_)) + 1]

    for line_id, box in boxes.items():
        per_line[line_id]["bbox_px"] = photo_bbox(box)
    ambiguous = dict(c.NORTHBOX_AMBIGUOUS)
    ambiguous["digit_bbox_px"] = photo_bbox(ambiguous_box)
    ambiguous["readings"] = [rate_text(ambiguous["true"]), rate_text(ambiguous["alt"])]
    return {
        "files": [FILENAME],
        "lines": per_line,
        "image_size": [CANVAS_W, CANVAS_H],
        "skew_deg": SKEW_DEG,
        "ambiguous_digit": ambiguous,
        "unit_statement": "Rates are per 100 pcs.",
        "freight_locator": "rate card footer",
        "questionnaire_locators": {q: "rate card footer" for q in ("Q1", "Q2", "Q3", "Q4", "Q6")},
    }


def _draw_ambiguous(paper, draw, text, left, y_mid, rate_font, rng):
    """Print the rate, then blot one digit so it is honestly unreadable as 3 versus 8.

    The printed digit is the true one. An ink blot covers its left half, which is exactly
    the part that distinguishes a 3 from an 8.
    """
    index = c.NORTHBOX_AMBIGUOUS["digit_index"]
    digit_positions = [i for i, ch in enumerate(text) if ch.isdigit()]
    target = digit_positions[index]
    draw.text((left, y_mid), text, font=rate_font, fill=INK, anchor="lm")
    x = left + draw.textlength(text[:target], font=rate_font)
    width = draw.textlength(text[target], font=rate_font)
    top, bottom = y_mid - 15, y_mid + 13

    pad = 26
    region = (int(x) - pad, int(top) - pad, int(x + width) + pad, int(bottom) + pad)
    layer = Image.new("RGBA", (region[2] - region[0], region[3] - region[1]), (0, 0, 0, 0))
    blot = ImageDraw.Draw(layer)
    ink = (34, 36, 58)
    ox, oy = pad, pad
    height = bottom - top
    blot.ellipse([ox - 3, oy - 3, ox + width * 0.56, oy + height + 4], fill=ink + (235,))
    for _ in range(7):  # ragged edge
        bx = ox + rng.uniform(-6, width * 0.42)
        by = oy + rng.uniform(-6, height)
        radius = rng.uniform(3, 6.5)
        blot.ellipse([bx - radius, by - radius, bx + radius, by + radius], fill=ink + (225,))
    blot.ellipse([ox - 15, oy + height * 0.55, ox + 2, oy + height * 0.9], fill=ink + (110,))  # drag
    layer = layer.filter(ImageFilter.GaussianBlur(1.1))
    paper.paste(layer, region[:2], layer)
    return (x - 8, top - 6, x + width + 6, bottom + 6)


if __name__ == "__main__":
    out = build()
    print(out["lines"]["L05"], out["ambiguous_digit"])
