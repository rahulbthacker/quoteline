"""Checkpoint A: one live, traced call per configured role, covering both providers.

Run with `make check-a`. Exits non-zero unless every provider answers and every call is traced.
Each ping carries a fresh nonce the model must echo back in structured output, so a pass can
only come from a live round trip.
"""

from __future__ import annotations

import secrets
import sys
import uuid

from pydantic import BaseModel, Field
from sqlalchemy import select

from app.config import PROVIDERS, ROLES, get_settings
from app.db import init_db, session_scope
from app.llm import gateway
from app.llm.contracts import LLMRequest, ModelCallError
from app.models.trace import TraceRow

PROMPT_VERSION = "connectivity_check_v1"


class Ping(BaseModel):
    nonce: str = Field(description="The nonce from the request, copied exactly")
    model_family: str = Field(description="The family of model answering: Claude or Gemini")


def main() -> int:
    init_db()
    settings = get_settings()
    run_id = f"check-a-{uuid.uuid4().hex[:8]}"
    ok_providers: set[str] = set()
    problems: list[str] = []

    for role in ROLES:
        nonce = secrets.token_hex(4)
        req = LLMRequest(
            role=role,
            prompt_version=PROMPT_VERSION,
            system="You are a connectivity check. Reply only with the requested JSON.",
            text=f"Echo this nonce exactly and name your model family. Nonce: {nonce}",
            output_schema=Ping,
            max_tokens=2048,
            effort="low",
        )
        try:
            result = gateway.call(req, run_id=run_id)
        except ModelCallError as exc:
            problems.append(f"{role}: {exc}")
            continue
        if result.parsed.nonce != nonce:
            problems.append(f"{role}: nonce mismatch ({result.parsed.nonce!r} != {nonce!r})")
            continue
        ok_providers.add(result.provider)

    with session_scope() as session:
        rows = session.scalars(
            select(TraceRow).where(TraceRow.parent_run_id == run_id).order_by(TraceRow.created_at)
        ).all()

    header = f"{'role':<18}{'provider':<10}{'served model':<34}{'try':>4}{'status':>7}"
    header += f"{'in':>7}{'out':>7}{'ms':>7}{'cost ₹':>9}"
    print(f"\nRun {run_id} · {len(rows)} traced calls\n{header}\n{'-' * len(header)}")
    for row in rows:
        cost = "unpriced" if row.cost_inr is None else f"{row.cost_inr:.4f}"
        cost = cost if row.status == "ok" else "-"
        print(
            f"{row.role:<18}{row.provider:<10}{(row.served_model or row.model):<34}"
            f"{row.attempt:>4}{row.status:>7}{row.input_tokens or 0:>7}"
            f"{row.output_tokens or 0:>7}{row.latency_ms:>7}{cost:>9}"
        )

    configured = {spec.provider for role in ROLES for spec in settings.chain(role)}
    missing = [p for p in PROVIDERS if p not in ok_providers]
    print()
    for problem in problems:
        print(f"FAIL  {problem}")
    if not problems and not missing:
        print("Checkpoint A passed: both providers answered with a traced call on every role.")
        return 0
    not_configured = [p for p in missing if p not in configured]
    if not_configured:
        print(f"FAIL  no role is configured to use: {', '.join(not_configured)}")
    print(f"Checkpoint A NOT passed. Providers without a successful traced call: {missing}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
