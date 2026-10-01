"""The normalised quote table the analyst queries (DuckDB).

A snapshot is written from the current grid for every question, so an answer can always be
tied to the exact data it ran on. The `quotes` table holds only cells that count: confident,
or overridden with a value. Cells in review, not quoted or excluded are in `excluded_cells`
with the reason, so an answer can say what it left out and why.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import duckdb

from app.config import VAR_DIR
from app.services.grid import GridResult

SNAPSHOT_DIR = VAR_DIR / "snapshots"

SCHEMA_DOC = """
quotes  -- one row per (vendor, RFx line) whose price COUNTS: confident or overridden. Use this for every figure.
  vendor_id TEXT, vendor TEXT, quality TEXT ('Pass' | 'Partial' | 'Fail' | NULL: questionnaire result),
  line_id TEXT ('L01'..), description TEXT, ply INTEGER (3, 5, 7 or NULL for ancillary items), gsm INTEGER,
  print TEXT (NULL means plain), qty INTEGER (annual quantity), uom TEXT,
  inr_per_1000 DOUBLE (normalised price, INR per 1,000 units),
  extended_inr DOUBLE (= inr_per_1000 * qty / 1000, the annual value of the line at this price),
  state TEXT ('confident' | 'overridden'), basis TEXT ('explicit' | 'per_kg' | 'carry_forward'),
  is_lowest BOOLEAN (lowest counted price on the line across ALL vendors, before any filter)

excluded_cells  -- one row per (vendor, line) that does NOT count, with why
  vendor_id TEXT, vendor TEXT, line_id TEXT, description TEXT,
  state TEXT ('needs_review' | 'not_quoted' | 'excluded'), reason TEXT

lines  -- the RFx: one row per line
  line_id TEXT, description TEXT, ply INTEGER, gsm INTEGER, print TEXT, qty INTEGER, uom TEXT,
  board_weight_kg_per_pc DOUBLE,
  last_year_inr_per_1000 DOUBLE (last year's contract price; NULL for lines new this year),
  last_year_extended_inr DOUBLE

vendors  -- one row per vendor
  vendor_id TEXT, vendor TEXT, quality TEXT, reply_format TEXT, quote_currency TEXT,
  lines_quoted INTEGER, lines_counted INTEGER, lines_in_review INTEGER, lines_not_quoted INTEGER,
  freight_kind TEXT ('included' | 'lump_sum' | 'extra_unpriced' | 'not_stated'), freight_inr DOUBLE,
  counted_total_inr DOUBLE (sum of extended_inr over this vendor's counted lines)

quality_answers  -- questionnaire verdicts
  vendor_id TEXT, vendor TEXT, question_id TEXT, mandatory BOOLEAN,
  status TEXT ('pass' | 'fail' | 'unanswered' | 'answered'), answer TEXT
""".strip()


def build_snapshot(result: GridResult) -> tuple[Path, str]:
    """Write the grid to a fresh DuckDB file. Returns (path, content hash)."""
    grid, rfx = result.grid, result.rfx
    lines = {line.line_id: line for line in rfx.line_items}
    vendors = {v.vendor_id: v for v in grid.vendors}
    quotes, excluded = [], []
    for row in grid.lines:
        line = lines[row.line_id]
        for vendor_id, cell in row.cells.items():
            vendor = vendors[vendor_id]
            if cell.inr_per_base is not None:
                quotes.append(
                    (vendor_id, vendor.name, vendor.quality, row.line_id, row.description,
                     line.spec.ply, line.spec.gsm, line.spec.print, row.qty, row.uom,
                     cell.inr_per_base, cell.extended_inr, cell.state, cell.how, cell.is_lowest)
                )  # fmt: skip
            else:
                state = "excluded" if cell.excluded else cell.state
                reason = (
                    (cell.override.reason if cell.override else None)
                    or cell.flag_reason
                    or (
                        "vendor did not quote this line"
                        if cell.state == "not_quoted"
                        else "open review item"
                    )
                )
                excluded.append(
                    (vendor_id, vendor.name, row.line_id, row.description, state, reason)
                )
    line_rows = [
        (item.line_id, item.description, item.spec.ply, item.spec.gsm, item.spec.print, item.qty, item.uom,
         item.spec.board_weight_kg_per_pc, item.last_year_price_inr,
         None if item.last_year_price_inr is None else round(item.last_year_price_inr * item.qty / 1000, 2))
        for item in rfx.line_items
    ]  # fmt: skip
    vendor_rows = [
        (v.vendor_id, v.name, v.quality, v.format, v.currency, v.lines_quoted, v.totals.lines_counted,
         v.totals.needs_review, v.totals.not_quoted, v.freight.kind, v.freight.amount_inr,
         v.totals.extended_inr)
        for v in grid.vendors
    ]  # fmt: skip
    answers = []
    for vendor_id, row in result.quality.items():
        for answer in row.answers or []:
            override = (row.overrides or {}).get(answer["question_id"])
            answers.append(
                (vendor_id, vendors[vendor_id].name if vendor_id in vendors else vendor_id,
                 answer["question_id"], bool(answer["mandatory"]),
                 override["status"] if override else answer["status"], answer.get("answer"))
            )  # fmt: skip

    payload = json.dumps(
        [quotes, excluded, line_rows, vendor_rows, answers], sort_keys=True, default=str
    )
    digest = hashlib.sha256(payload.encode()).hexdigest()[:12]
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = SNAPSHOT_DIR / f"{rfx.id}-{digest}.duckdb"
    if path.exists():
        return path, digest
    tmp = path.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    con = duckdb.connect(str(tmp))
    con.execute(
        "CREATE TABLE quotes (vendor_id TEXT, vendor TEXT, quality TEXT, line_id TEXT, description TEXT, "
        "ply INTEGER, gsm INTEGER, print TEXT, qty INTEGER, uom TEXT, inr_per_1000 DOUBLE, "
        "extended_inr DOUBLE, state TEXT, basis TEXT, is_lowest BOOLEAN)"
    )
    con.execute(
        "CREATE TABLE excluded_cells (vendor_id TEXT, vendor TEXT, line_id TEXT, description TEXT, "
        "state TEXT, reason TEXT)"
    )
    con.execute(
        "CREATE TABLE lines (line_id TEXT, description TEXT, ply INTEGER, gsm INTEGER, print TEXT, "
        "qty INTEGER, uom TEXT, board_weight_kg_per_pc DOUBLE, last_year_inr_per_1000 DOUBLE, "
        "last_year_extended_inr DOUBLE)"
    )
    con.execute(
        "CREATE TABLE vendors (vendor_id TEXT, vendor TEXT, quality TEXT, reply_format TEXT, "
        "quote_currency TEXT, lines_quoted INTEGER, lines_counted INTEGER, lines_in_review INTEGER, "
        "lines_not_quoted INTEGER, freight_kind TEXT, freight_inr DOUBLE, counted_total_inr DOUBLE)"
    )
    con.execute(
        "CREATE TABLE quality_answers (vendor_id TEXT, vendor TEXT, question_id TEXT, mandatory BOOLEAN, "
        "status TEXT, answer TEXT)"
    )
    for table, rows, width in (
        ("quotes", quotes, 15), ("excluded_cells", excluded, 6), ("lines", line_rows, 10),
        ("vendors", vendor_rows, 12), ("quality_answers", answers, 6),
    ):  # fmt: skip
        if rows:
            con.executemany(f"INSERT INTO {table} VALUES ({','.join('?' * width)})", rows)
    con.close()
    tmp.rename(path)
    return path, digest
