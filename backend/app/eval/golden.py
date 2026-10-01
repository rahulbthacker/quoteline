"""Golden set loader. The generator knows the truth, so accuracy is measured, not estimated."""

from __future__ import annotations

import json
from functools import lru_cache

from app.config import REPO_ROOT

GOLDEN_DIR = REPO_ROOT / "data" / "golden"
VENDORS = ["meridian", "sribalaji", "kaveri", "northbox", "anand"]
# The generator's unit names -> the app's unit codes.
UNIT_CODE = {
    "per_pc": "per_piece",
    "per_100": "per_100",
    "per_1000": "per_1000",
    "per_kg": "per_kg",
    "per_box": "per_box",
}


@lru_cache
def load(vendor_id: str) -> dict:
    return json.loads((GOLDEN_DIR / f"{vendor_id}.json").read_text(encoding="utf-8"))
