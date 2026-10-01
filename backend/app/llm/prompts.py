"""Prompt registry. Prompts are versioned files; the version travels into every trace."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

PROMPT_DIR = Path(__file__).resolve().parents[1] / "prompts"
_HEADER = re.compile(r"\A<!--\s*version:\s*(\S+)\s*\n\s*purpose:\s*(.+?)\s*-->\s*\n", re.S)


@dataclass(frozen=True)
class Prompt:
    version: str
    purpose: str
    text: str


@lru_cache
def load(name: str) -> Prompt:
    """Load `app/prompts/<name>.md`. The file must start with a version and purpose header."""
    raw = (PROMPT_DIR / f"{name}.md").read_text(encoding="utf-8")
    match = _HEADER.match(raw)
    if not match:
        raise ValueError(f"Prompt {name} is missing its version/purpose header")
    version, purpose = match.group(1), match.group(2)
    if version != name:
        raise ValueError(f"Prompt file {name}.md declares version {version}")
    return Prompt(version=version, purpose=purpose, text=raw[match.end() :].strip())
