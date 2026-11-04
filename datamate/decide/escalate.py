"""Escalate (M12): khi không chắc ⇒ hỏi LLM đọc số liệu và trả lời."""

from __future__ import annotations

import json
import logging
from typing import Any

from dtypes import Answer, AnswerType, BizContext, TimeWindow
from llm.prompts import answer_prompt
from llm.schemas import ANSWER_SCHEMA

log = logging.getLogger(__name__)


def _data_block(ctx: BizContext, limit: int = 40) -> str:
    """Số liệu tổng hợp của shop (để LLM đọc)."""
    lines: list[str] = []
    queries = [
        ("doanh thu", "SELECT SUM(line_amount_net) FROM v_lines WHERE order_date <= DATE ?"),
        ("so don", "SELECT COUNT(*) FROM v_orders WHERE order_date <= DATE ?"),
        ("so khach", "SELECT COUNT(DISTINCT customer_key) FROM v_orders "
                     "WHERE order_date <= DATE ? AND NOT is_walkin"),
        ("mat hang", "SELECT COUNT(DISTINCT product_code) FROM v_products"),
    ]
    from datetime import date

    today = date.today()
    for label, sql in queries:
        try:
            rows = ctx.con.execute(sql, [today]).fetchall()
            lines.append(f"- {label}: {rows[0][0] if rows else None}")
        except Exception:  # noqa: BLE001
            continue
    try:
        rows = ctx.con.execute(
            "SELECT product_name, SUM(line_amount_net) v FROM v_lines "
            "WHERE order_date <= DATE ? GROUP BY 1 ORDER BY v DESC LIMIT ?",
            [today, limit]).fetchall()
        for name, v in rows:
            lines.append(f"- {name}: {v}")
    except Exception:  # noqa: BLE001
        pass
    return "\n".join(lines)


def escalate(question: str, ctx: BizContext, llm: Any, windows: list[TimeWindow] | None = None
              ) -> tuple[Answer | None, dict[str, Any]]:
    """Trả (Answer | None, debug)."""
    info: dict[str, Any] = {"path": "escalate"}
    if llm is None or not getattr(llm, "available", True):
        info["skipped"] = "no_llm"
        return None, info
    data = _data_block(ctx)
    prompt = answer_prompt(question, ctx, data)
    try:
        outs = llm.generate([prompt], json_schema=ANSWER_SCHEMA)
    except Exception as exc:  # noqa: BLE001
        info["error"] = str(exc)
        return None, info
    text = (outs or [""])[0]
    info["raw"] = text[:300]
    try:
        obj = json.loads(text)
    except (ValueError, TypeError):
        info["error"] = "parse_fail"
        return None, info
    ans = Answer.from_jsonl(obj)
    if ans.type == AnswerType.ABSTAIN.value:
        return None, info
    return ans, info
