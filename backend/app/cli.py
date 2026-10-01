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
    args = parser.parse_args()

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
