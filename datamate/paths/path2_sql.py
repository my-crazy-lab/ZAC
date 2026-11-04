"""Path 2 (M10): LLM → SQL → sandbox → execute.

SQL do LLM viết **phải qua sandbox** (chỉ SELECT/WITH, không lệnh ghi).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from dtypes import Answer, AnswerType, BizContext, Knobs, Spec, TimeWindow
from engine.executor import run_sql
from engine.sandbox import SqlRejected, check_sql
from fmt.formatter import to_submission
from llm.prompts import sql_prompt

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


def run_path2(question: str, ctx: BizContext, knobs: Knobs, windows: list[TimeWindow],
              as_of, llm: Any) -> tuple[Answer | None, dict[str, Any]]:
    """Trả (Answer | None, thông tin debug)."""
    info: dict[str, Any] = {"path": "sql"}
    if llm is None or not getattr(llm, "available", True):
        info["skipped"] = "no_llm"
        return None, info
    tables = _tables_block(ctx)
    prompt = sql_prompt(question, ctx, as_of.isoformat(), tables)
    try:
        outs = llm.generate([prompt], json_schema=SQL_SCHEMA)
    except Exception as exc:  # noqa: BLE001
        log.warning("path2 lỗi: %s", exc)
        info["error"] = str(exc)
        return None, info
    text = (outs or [""])[0]
    info["raw"] = text[:400]
    sql = ""
    try:
        obj = json.loads(text)
        sql = str(obj.get("sql", ""))
    except (ValueError, TypeError, AttributeError):
        sql = extract_sql(text)
    if not sql:
        info["error"] = "no_sql"
        return None, info
    try:
        check_sql(sql)
    except SqlRejected as exc:
        info["rejected"] = str(exc)
        return None, info
    info["sql"] = sql[:800]
    res = run_sql(ctx.con, sql)
    if res.error:
        info["sql_error"] = res.error
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
            "WHERE table_schema='main' ORDER BY table_name"
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
