"""Paths, fonts and determinism helpers shared by the generators."""

from __future__ import annotations

import importlib.util
import re
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "data"
REPLIES = DATA / "replies"
ATTACHMENTS = DATA / "attachments"
GOLDEN = DATA / "golden"
RFX_DIR = DATA / "rfx"

FIXED_ZIP_TIME = (2026, 9, 22, 10, 0, 0)


def font_path(name: str) -> str:
    """DejaVu ships inside matplotlib, so the same glyphs (including ₹) render on any machine."""
    root = Path(importlib.util.find_spec("matplotlib").origin).parent
    return str(root / "mpl-data" / "fonts" / "ttf" / name)


def normalise_zip(path: Path) -> None:
    """Rewrite an OOXML container with fixed timestamps and order so re-seeding is byte-stable."""
    with zipfile.ZipFile(path) as src:
        entries = [(info.filename, src.read(info.filename)) for info in src.infolist()]
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as dst:
        for name, payload in entries:
            if name == "docProps/core.xml":  # openpyxl stamps the save time here
                payload = re.sub(
                    rb"(<dcterms:(created|modified)[^>]*>)[^<]*(</dcterms:)",
                    rb"\g<1>2026-09-22T10:00:00Z\g<3>",
                    payload,
                )
            info = zipfile.ZipInfo(name, FIXED_ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            dst.writestr(info, payload)


def dims_text(dims: tuple[int, ...] | None, sep: str = " x ") -> str:
    return sep.join(str(d) for d in dims) if dims else ""
