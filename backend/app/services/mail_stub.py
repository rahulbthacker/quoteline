"""The only stub in the system: email transport.

"Receiving" is a folder. Anything dropped into mail/inbox/<vendor>/ is an inbound reply.
"Sending" writes .eml files to mail/outbox/ (added with the Sent screen). Nothing here
touches a model.
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path

from app.config import REPO_ROOT

INBOX = REPO_ROOT / "mail" / "inbox"
OUTBOX = REPO_ROOT / "mail" / "outbox"
SEED_MANIFEST = REPO_ROOT / "data" / "replies" / "manifest.json"


def deliver_seed_replies(only_vendors: list[str] | None = None) -> dict[str, list[str]]:
    """Drop the five fabricated vendor replies into the inbox, as their senders would."""
    manifest = json.loads(SEED_MANIFEST.read_text(encoding="utf-8"))
    delivered: dict[str, list[str]] = {}
    for entry in manifest:
        vendor_id = entry["vendor_id"]
        if only_vendors and vendor_id not in only_vendors:
            continue
        folder = INBOX / vendor_id
        if folder.exists():
            shutil.rmtree(folder)
        folder.mkdir(parents=True)
        received = datetime.fromisoformat(entry["received_at"]).timestamp()
        for item in entry["files"] + entry["attachments"]:
            source = REPO_ROOT / item["path"]
            target = folder / source.name
            shutil.copyfile(source, target)
            os.utime(target, (received, received))  # arrival time travels as the file's mtime
            delivered.setdefault(vendor_id, []).append(target.name)
    return delivered


def scan_inbox() -> dict[str, list[Path]]:
    """vendor_id -> files waiting in that vendor's inbox folder."""
    if not INBOX.exists():
        return {}
    found: dict[str, list[Path]] = {}
    for folder in sorted(p for p in INBOX.iterdir() if p.is_dir()):
        files = sorted(p for p in folder.iterdir() if p.is_file() and not p.name.startswith("."))
        if files:
            found[folder.name] = files
    return found


def received_at(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)


def write_outbox(
    filename: str,
    *,
    sender: str,
    to: str,
    subject: str,
    body: str,
    attachments: list[tuple[str, bytes, str, str]] | None = None,
    message_id: str | None = None,
) -> Path:
    """Write one .eml to mail/outbox/. This is the whole of "sending"."""
    from email.message import EmailMessage
    from email.policy import SMTP
    from email.utils import format_datetime

    message = EmailMessage(policy=SMTP)
    message["From"], message["To"], message["Subject"] = sender, to, subject
    message["Date"] = format_datetime(datetime.now(UTC))
    if message_id:
        message["Message-ID"] = message_id
    message.set_content(body)
    for name, payload, maintype, subtype in attachments or []:
        message.add_attachment(payload, maintype=maintype, subtype=subtype, filename=name)
    OUTBOX.mkdir(parents=True, exist_ok=True)
    path = OUTBOX / filename
    path.write_bytes(message.as_bytes())
    return path
