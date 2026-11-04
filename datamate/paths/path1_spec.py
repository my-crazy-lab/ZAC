"""Path 1 (M9): LLM → ``Spec`` → validate → compile → execute.

Ưu tiên hơn Path 2 vì Spec **có schema + validate bằng code**.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from dtypes import Answer, AnswerType, BizContext, Knobs, Spec, TimeWindow
from engine.compile import compile_spec, validate_spec
from engine.executor import run_sql
from fmt.formatter import to_submission
from llm.prompts import spec_prompt
from llm.schemas import SPEC_SCHEMA

log = logging.getLogger(__name__)


def parse_spec(text: str) -> Spec | None:
    """Parse JSON → ``Spec`` (None nếu hỏng)."""
    if not text:
        return None
    try:
        obj = json.loads(text)
    except (ValueError, TypeError):
        return None
    try:
        return Spec.from_dict(obj)
    except (KeyError, TypeError, ValueError):
        return None


def run_path1(question: str, ctx: BizContext, knobs: Knobs, windows: list[TimeWindow],
              entities: list[str], as_of, llm: Any) -> tuple[Answer | None, dict[str, Any]]:
    """Trả (Answer | None, thông tin debug)."""
    info: dict[str, Any] = {"path": "spec"}
    if llm is None or not getattr(llm, "available", True):
        info["skipped"] = "no_llm"
        return None, info
    prompt = spec_prompt(question, ctx, windows, entities)
    try:
        outs = llm.generate([prompt], json_schema=SPEC_SCHEMA)
    except Exception as exc:  # noqa: BLE001
        log.warning("path1 lỗi: %s", exc)
        info["error"] = str(exc)
        return None, info
    text = (outs or [""])[0]
    info["raw"] = text[:400]
    spec = parse_spec(text)
    if spec is None:
        info["error"] = "parse_fail"
        return None, info
    info["spec"] = spec.to_dict()
    errs = validate_spec(spec, ctx, windows)
    if errs:
        info["errors"] = errs
        return None, info
    plan = compile_spec(spec, ctx, knobs, windows, as_of)
    res = run_sql(ctx.con, plan.sql)
    if res.error:
        info["sql_error"] = res.error
        return None, info
    ans = to_submission(plan, res, spec, spec.output, ctx, knobs, windows)
    info["sql"] = plan.sql[:500]
    if ans.type == AnswerType.ABSTAIN.value:
        return None, info
    return ans, info
