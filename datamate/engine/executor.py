"""Executor: chạy SQL an toàn, trả ``ExecResult`` (không raise) (M5)."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

from dtypes import ExecResult
from engine.sandbox import SqlRejected, check_sql

log = logging.getLogger(__name__)


def run_sql(con: Any, sql: str, timeout_s: float = 20, max_rows: int = 1000) -> ExecResult:
    """Chạy SQL (chỉ SELECT/WITH), cắt ngắt nếu quá thời gian."""
    t0 = time.time()
    try:
        check_sql(sql)
    except SqlRejected as exc:
        return ExecResult(columns=[], rows=[], error=f"sql_rejected: {exc}", elapsed_s=0.0)

    result: dict[str, Any] = {}

    def _run() -> None:
        try:
            cur = con.execute(sql)
            cols = list(cur.description and [d[0] for d in cur.description] or [])
            rows = cur.fetchmany(max_rows)
            result["columns"] = cols
            result["rows"] = [tuple(r) for r in rows]
        except Exception as exc:  # noqa: BLE001
            result["error"] = f"{type(exc).__name__}: {exc}"

    th = threading.Thread(target=_run, daemon=True)
    th.start()
    th.join(timeout_s)
    if th.is_alive():
        try:
            con.interrupt()
        except Exception:  # noqa: BLE001
            pass
        return ExecResult(columns=[], rows=[], error=f"timeout sau {timeout_s}s",
                          elapsed_s=time.time() - t0)
    elapsed = time.time() - t0
    if "error" in result:
        return ExecResult(columns=[], rows=[], error=result["error"], elapsed_s=elapsed)
    return ExecResult(columns=result.get("columns", []), rows=result.get("rows", []),
                      error=None, elapsed_s=elapsed)
