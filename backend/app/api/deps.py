"""Shared API dependencies: the persona switcher (a demo device, not authentication)."""

from __future__ import annotations

from typing import Annotated

from fastapi import Header, HTTPException

from app.services import audit

PERSONAS = ("buyer", "vp", "evaluator", "admin")


def persona(x_persona: Annotated[str | None, Header()] = None) -> str:
    value = (x_persona or "buyer").lower()
    if value not in PERSONAS:
        raise HTTPException(400, f"unknown persona '{value}'")
    return value


Persona = Annotated[str, Header(alias="X-Persona")]


def require(current: str, *allowed: str) -> str:
    """Return the actor's display name, or refuse if this persona may not do this."""
    if current not in allowed:
        raise HTTPException(
            403, f"The {current} persona cannot do this. Allowed: {', '.join(allowed)}."
        )
    return audit.actor_name(current)
