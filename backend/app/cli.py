"""Command-line entry points used by the Makefile."""

from __future__ import annotations

import argparse
import json

from app.services import ingest, mail_stub

RFX_ID = "RFX-0147"


def main() -> None:
    parser = argparse.ArgumentParser(prog="quoteline")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("load-rfx", help="load the seeded RFx and vendors into the database")
    deliver = sub.add_parser("deliver", help="drop the seeded vendor replies into mail/inbox")
    deliver.add_argument("--vendor", action="append")
    run = sub.add_parser(
        "ingest", help="read everything in the inbox with both models (live calls)"
    )
    run.add_argument("--vendor", action="append")
    sub.add_parser("reverify", help="re-run the source check on stored readings (no model calls)")
    sub.add_parser("reset", help="delete all app state (database, snapshots, inbox, outbox)")
    sub.add_parser("send", help="send the RFx to every vendor (writes .eml files to mail/outbox)")
    args = parser.parse_args()

    if args.command == "reset":
        import shutil

        from app.config import VAR_DIR

        shutil.rmtree(VAR_DIR, ignore_errors=True)
        for folder in (mail_stub.INBOX, mail_stub.OUTBOX):
            for path in folder.glob("*"):
                if path.name != ".gitkeep":
                    shutil.rmtree(path) if path.is_dir() else path.unlink()
        print("State cleared: database, snapshots, inbox and outbox.")
        return
    if args.command == "reverify":
        from sqlalchemy import select

        from app.agents.extractor import verify_source
        from app.db import session_scope
        from app.models import ExtractionRow
        from app.services import parsers

        documents = {}
        for vendor, paths in mail_stub.scan_inbox().items():
            for path in paths:
                documents[(vendor, path.name)] = parsers.parse(path.name, path.read_bytes())
        changed = 0
        with session_scope() as session:
            for row in session.scalars(select(ExtractionRow)):
                document = documents.get((row.vendor_id, row.file))
                if document is None:
                    continue
                payload = dict(row.payload)
                ref = dict(payload["source_ref"])
                verified = verify_source(
                    document, ref["locator"], ref["snippet"], payload["raw_value"]
                )
                if verified != ref.get("snippet_verified"):
                    ref["snippet_verified"] = verified
                    payload["source_ref"] = ref
                    row.payload = payload
                    changed += 1
        print(f"Re-checked stored readings against the files in the inbox; {changed} changed.")
        return
    if args.command == "send":
        from app.services import outbound

        ingest.load_seed_rfx()
        for item in outbound.send_rfx(RFX_ID, actor="R. Thacker (category buyer)"):
            print(f"  outbox: {item['path']} -> {item['to']}")
        return

    if args.command == "load-rfx":
        rfx = ingest.load_seed_rfx()
        print(f"Loaded {rfx.id}: {len(rfx.line_items)} lines, {len(rfx.questionnaire)} questions")
    elif args.command == "deliver":
        for vendor, files in mail_stub.deliver_seed_replies(args.vendor).items():
            print(f"  inbox/{vendor}: {', '.join(files)}")
    elif args.command == "ingest":
        ingest.load_seed_rfx()
        print(json.dumps(ingest.ingest(RFX_ID, args.vendor), indent=2, default=str))


if __name__ == "__main__":
    main()
