"""Sandboxed query executor for the analyst.

The model writes one read-only SQL statement. It runs in a separate Python process against a
read-only DuckDB snapshot, with file and network access switched off inside DuckDB, a memory
cap, and a hard timeout. The parent process never evaluates model output.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

TIMEOUT_S = 12
MAX_ROWS = 500

_RUNNER = r"""
import json, sys, time, datetime, decimal
import duckdb
request = json.load(sys.stdin)
con = duckdb.connect(request["db"], read_only=True)
con.execute("SET enable_external_access=false")
con.execute("SET memory_limit='512MB'")
con.execute("SET threads=2")
con.execute("SET lock_configuration=true")
started = time.perf_counter()
try:
    cursor = con.execute(request["sql"])
except Exception as exc:
    json.dump({"error": f"{type(exc).__name__}: {str(exc).splitlines()[0]}"}, sys.stdout)
    sys.exit(0)
columns = [d[0] for d in cursor.description]
rows = cursor.fetchmany(request["max_rows"] + 1)
def plain(v):
    if isinstance(v, decimal.Decimal): return float(v)
    if isinstance(v, (datetime.date, datetime.datetime)): return v.isoformat()
    return v
truncated = len(rows) > request["max_rows"]
rows = [[plain(v) for v in row] for row in rows[: request["max_rows"]]]
json.dump({"columns": columns, "rows": rows, "truncated": truncated,
           "elapsed_ms": int((time.perf_counter() - started) * 1000)}, sys.stdout)
"""

_FORBIDDEN = re.compile(
    r"\b(attach|detach|copy|export|import|install|load|pragma|set|create|insert|update|delete|"
    r"drop|alter|call|read_csv|read_parquet|read_json|read_text|read_blob|glob|httpfs)\b",
    re.I,
)


class QueryRejected(Exception):
    pass


class QueryFailed(Exception):
    pass


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[list]
    truncated: bool
    elapsed_ms: int

    def records(self) -> list[dict]:
        return [dict(zip(self.columns, row, strict=True)) for row in self.rows]


def check(sql: str) -> str:
    """Static gate before anything runs: one SELECT statement, nothing that leaves the sandbox."""
    stripped = re.sub(r"--[^\n]*", "", sql).strip().rstrip(";").strip()
    if not stripped:
        raise QueryRejected("empty query")
    if ";" in stripped:
        raise QueryRejected("only a single statement is allowed")
    if not re.match(r"(?is)^\s*(select|with)\b", stripped):
        raise QueryRejected("only SELECT queries are allowed")
    without_strings = re.sub(r"'(?:[^']|'')*'", "''", stripped)
    found = _FORBIDDEN.search(without_strings)
    if found:
        raise QueryRejected(f"'{found.group(1)}' is not allowed in analyst queries")
    return stripped


def run(db_path: Path, sql: str) -> QueryResult:
    statement = check(sql)
    request = json.dumps({"db": str(db_path), "sql": statement, "max_rows": MAX_ROWS})
    started = time.perf_counter()
    try:
        completed = subprocess.run(  # noqa: S603  fixed argv, no shell
            [sys.executable, "-I", "-c", _RUNNER],
            input=request, capture_output=True, text=True, timeout=TIMEOUT_S, env={}, cwd="/",
        )  # fmt: skip
    except subprocess.TimeoutExpired as exc:
        raise QueryFailed(f"the query did not finish within {TIMEOUT_S} seconds") from exc
    if completed.returncode != 0:
        message = (
            completed.stderr.strip().splitlines()[-1]
            if completed.stderr.strip()
            else "unknown error"
        )
        raise QueryFailed(message)
    payload = json.loads(completed.stdout)
    if "error" in payload:
        raise QueryFailed(payload["error"])
    payload["elapsed_ms"] = max(payload["elapsed_ms"], 1) or int(
        (time.perf_counter() - started) * 1000
    )
    return QueryResult(**payload)
