"""Path 2 (M10): LLM → SQL → sandbox → execute.

SQL do LLM viết **phải qua sandbox** (chỉ SELECT/WITH, không lệnh ghi).
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from dtypes import Answer, AnswerType, BizContext, Knobs, Spec, TimeWindow
from engine.executor import run_sql
from engine.sandbox import SqlRejected, check_sql
from fmt.formatter import to_submission
from llm.prompts import sql_prompt
from schema.business_graph import semantic_graph_issues

log = logging.getLogger(__name__)

SQL_SCHEMA = {
    "type": "object",
    "properties": {"sql": {"type": "string"}},
    "required": ["sql"],
    "additionalProperties": False,
}

_FENCE_RE = re.compile(r"```(?:sql)?\s*(.*?)```", re.S)


def extract_sql(text: str) -> str:
    """Lấy SQL từ lời LLM (bỏ fence, bỏ dấu ; cuối)."""
    if not text:
        return ""
    m = _FENCE_RE.search(text)
    sql = m.group(1) if m else text
    sql = sql.strip()
    if sql.endswith(";"):
        sql = sql[:-1]
    return sql


def _parse_sql_text(text: str) -> str:
    try:
        return str((json.loads(text) or {}).get("sql", ""))
    except (ValueError, TypeError, AttributeError):
        return extract_sql(text)


def _validate_sql_refs(ctx: BizContext, sql: str) -> str | None:
    if re.search(r"\bas_of\b", sql, re.IGNORECASE):
        return "không dùng as_of như tên cột/biến; dùng ngày ISO literal"
    names = set(getattr(ctx, "views", set()))
    try:
        names |= {str(x[0]) for x in ctx.con.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='main'"
        ).fetchall()}
    except Exception:
        pass
    for name in re.findall(r"\b(?:FROM|JOIN)\s+([A-Za-z_][A-Za-z0-9_]*)", sql, re.IGNORECASE):
        if name not in names:
            return f"view/table không tồn tại: {name}"
        if not name.startswith("v_"):
            return f"chỉ được query canonical view v_*: {name}"
    return None


def run_path2(question: str, ctx: BizContext, knobs: Knobs, windows: list[TimeWindow],
              as_of, llm: Any) -> tuple[Answer | None, dict[str, Any]]:
    """Trả (Answer | None, thông tin debug)."""
    info: dict[str, Any] = {"path": "sql"}
    if os.environ.get("DATAMATE_PATH2", "0") != "1":
        info["skipped"] = "disabled"
        return None, info
    if llm is None or not getattr(llm, "available", True):
        info["skipped"] = "no_llm"
        return None, info
    tables = _tables_block(ctx)
    prompt = sql_prompt(question, ctx, as_of.isoformat(), tables, windows)
    sql = ""
    res = None
    for attempt in range(2):
        try:
            outs = llm.generate([prompt], json_schema=SQL_SCHEMA)
        except Exception as exc:  # noqa: BLE001
            log.warning("path2 lỗi: %s", exc)
            info["error"] = str(exc)
            return None, info
        text = (outs or [""])[0]
        info["raw"] = text[:400]
        sql = _parse_sql_text(text)
        if not sql:
            info["error"] = "no_sql"
            return None, info
        try:
            check_sql(sql)
            ref_error = _validate_sql_refs(ctx, sql)
            if ref_error:
                raise SqlRejected(ref_error)
            graph_errors = semantic_graph_issues(question, ctx.graph or {}) \
                if os.environ.get("DATAMATE_SEMANTIC_GRAPH", "1") != "0" else []
            if graph_errors:
                raise SqlRejected("; ".join(graph_errors))
        except SqlRejected as exc:
            info["rejected"] = str(exc)
            if attempt == 0:
                prompt += f"\n\nSQL trước bị từ chối: {exc}. Hãy sinh lại chỉ dùng view v_* và cột đã liệt kê."
                continue
            return None, info
        info["sql"] = sql[:800]
        res = run_sql(ctx.con, sql)
        if not res.error:
            break
        info["sql_error"] = res.error
        if attempt == 0:
            prompt += f"\n\nSQL trước lỗi DuckDB: {res.error[:600]}. Hãy sửa SQL và chỉ trả JSON."
    if res is None or res.error:
        return None, info
    if not res.rows:
        info["empty"] = True
        return None, info
    out_type = _guess_output(res, question)
    spec = Spec(intent="aggregate_total", metric=None, subject="none", filters=[],
                time=["main"], order="desc", limit=None, output=out_type, params={})
    plan = _plan_from_result(res, out_type)
    ans = to_submission(plan, res, spec, out_type, ctx, knobs, windows)
    if ans.type == AnswerType.ABSTAIN.value:
        return None, info
    return ans, info


def _tables_block(ctx: BizContext) -> str:
    lines = []
    try:
        rows = ctx.con.execute(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema='main' AND table_name LIKE 'v_%' "
            "ORDER BY table_name"
        ).fetchall()
    except Exception:  # noqa: BLE001
        return "(không đọc được)"
    cur = None
    for t, c in rows:
        if t != cur:
            cur = t
            lines.append(f"- {t}: ")
        lines.append(f"    {c}")
    return "\n".join(lines)


def _guess_output(res, question: str) -> str:
    q = question.lower()
    if "%" in q:
        return "percent"
    cols = [str(c).lower() for c in (res.columns or [])]
    if any("name" in c for c in cols):
        return "string"
    if len(res.rows) > 1:
        return "list"
    return "number"


def _plan_from_result(res, out_type: str):
    from dtypes import CompiledPlan

    return CompiledPlan(sql="", post=None, out_type=out_type,
                        meta={"is_money": out_type == "number", "value_col": "value",
                              "subject": "none", "metric": None, "intent": "sql"})
