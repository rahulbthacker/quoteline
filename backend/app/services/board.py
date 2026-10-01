"""Board weight estimate for a drafted line, from the category template. Deterministic.

Used only when a buyer drafts a new RFx without stating board weights. The estimate is marked
as an assumption on the draft; a per-kg quote can only be converted with a weight.
"""

from __future__ import annotations

FLUTE_GSM = 120
FLUTE_TAKE_UP = 1.40
GLUE_FLAP_MM = 40


def board_gsm(ply: int, liner_gsm: int) -> float:
    return (ply // 2 + 1) * liner_gsm + (ply // 2) * FLUTE_GSM * FLUTE_TAKE_UP


def estimate_weight_kg(
    description: str, ply: int | None, gsm: int | None, dims: list[int]
) -> float | None:
    """RSC boxes (three dimensions) and flat sheets or pads (two). Anything else: no estimate."""
    if not ply or not gsm or ply not in (3, 5, 7):
        return None
    text = description.lower()
    if any(
        word in text
        for word in ("die-cut", "die cut", "tray", "mailer", "partition", "telescopic", "display")
    ):
        return None
    if len(dims) == 3:
        length, width, height = dims
        area = (2 * (length + width) + GLUE_FLAP_MM) * (height + width) / 1e6
    elif len(dims) == 2:
        area = dims[0] * dims[1] / 1e6
    else:
        return None
    return round(area * board_gsm(ply, gsm) / 1000, 3)
