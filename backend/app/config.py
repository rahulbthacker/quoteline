"""Runtime configuration. Everything comes from the environment or the repo-root .env."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
VAR_DIR = BACKEND_ROOT / "var"

Provider = Literal["anthropic", "gemini"]
Role = Literal["EXTRACT_PRIMARY", "EXTRACT_SECONDARY", "JUDGE", "ROUTER", "ANALYST"]
ROLES: tuple[Role, ...] = ("EXTRACT_PRIMARY", "EXTRACT_SECONDARY", "JUDGE", "ROUTER", "ANALYST")
PROVIDERS: tuple[Provider, ...] = ("anthropic", "gemini")


@dataclass(frozen=True)
class ModelSpec:
    provider: Provider
    model: str

    def __str__(self) -> str:
        return f"{self.provider}:{self.model}"


def parse_chain(raw: str) -> list[ModelSpec]:
    """Parse 'provider:model,provider:model' into an ordered fallback chain."""
    chain: list[ModelSpec] = []
    for entry in (part.strip() for part in raw.split(",")):
        if not entry:
            continue
        provider, sep, model = entry.partition(":")
        if not sep or provider not in PROVIDERS or not model:
            raise ValueError(
                f"Bad model spec {entry!r}: expected provider:model with provider in {PROVIDERS}"
            )
        chain.append(ModelSpec(provider=provider, model=model))  # type: ignore[arg-type]
    if not chain:
        raise ValueError("Model chain is empty")
    return chain


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    anthropic_api_key: str = ""
    gemini_api_key: str = ""

    extract_primary: str = "anthropic:claude-opus-5-5"
    extract_secondary: str = "gemini:gemini-3.1-pro-preview"
    judge: str = "anthropic:claude-opus-5-5"
    router: str = "anthropic:claude-haiku-4-5"
    analyst: str = "anthropic:claude-opus-5-5"

    cost_usd_inr: float = 83.42
    database_url: str = f"sqlite:///{VAR_DIR / 'quoteline.db'}"

    def chain(self, role: Role) -> list[ModelSpec]:
        return parse_chain(getattr(self, role.lower()))

    def api_key(self, provider: Provider) -> str:
        return getattr(self, f"{provider}_api_key")


@lru_cache
def get_settings() -> Settings:
    return Settings()
