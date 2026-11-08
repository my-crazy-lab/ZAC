"""Path 1 (M9): LLM chọn **template có sẵn** → validate → compile → execute.

Không để LLM viết SQL. LLM chỉ trả ``template_id`` + tham số trong tập đóng;
SQL do ``engine.compile`` render từ catalog của chính business đó.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from decide.verify import verify_result
from dtypes import Answer, AnswerType, BizContext, Knobs, Spec, TimeWindow
from engine.catalog import build_catalog, retrieve_templates
from engine.compile import compile_spec, validate_spec
from engine.executor import run_sql
from engine.semantics import (bestseller_compatible, metric_compatible,
                              subject_compatible)
from fmt.formatter import to_submission
from llm.prompts import planner_prompt, spec_prompt
from llm.schemas import PLAN_SCHEMA, SPEC_SCHEMA
from schema.business_graph import semantic_graph_issues
from text.normalize import expand_abbrev, nd

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


def parse_plan(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    try:
        obj = json.loads(text)
    except (ValueError, TypeError):
        return None
    if not isinstance(obj, dict):
        return None
    return obj


def run_path1(question: str, ctx: BizContext, knobs: Knobs, windows: list[TimeWindow],
              entities: list[str], as_of, llm: Any) -> tuple[Answer | None, dict[str, Any]]:
    """Trả (Answer | None, thông tin debug)."""
    if llm is None or not getattr(llm, "available", True):
        return None, {"path": "spec", "skipped": "no_llm"}
    if os.environ.get("DATAMATE_PLANNER", "1").lower() in ("0", "legacy", "off"):
        return _run_legacy(question, ctx, knobs, windows, entities, as_of, llm)
    return _run_planner(question, ctx, knobs, windows, entities, as_of, llm)


def _run_planner(question: str, ctx: BizContext, knobs: Knobs,
                 windows: list[TimeWindow], entities: list[str], as_of,
                 llm: Any) -> tuple[Answer | None, dict[str, Any]]:
    info: dict[str, Any] = {"path": "planner"}
    catalog = getattr(ctx, "catalog", None) or build_catalog(ctx)
    if not catalog:
        info["error"] = "no_catalog"
        return None, info
    k = int(os.environ.get("DATAMATE_PLANNER_K", "12") or 12)
    q_nd = expand_abbrev(nd(question))
    entity_kinds = {str(e).split(":")[0].strip() for e in (entities or []) if ":" in str(e)}
    templates = retrieve_templates(q_nd, catalog, k=k, windows=windows,
                                   entity_kinds=entity_kinds)
    info["catalog"] = [t.id for t in templates]
    prompt = planner_prompt(question, ctx, windows, entities, templates,
                            normalized=q_nd)
    attempts = info.setdefault("attempts", [])

    for attempt in range(2):
        try:
            outs = llm.generate([prompt], json_schema=PLAN_SCHEMA)
        except Exception as exc:  # noqa: BLE001
            log.warning("planner lỗi: %s", exc)
            info["error"] = str(exc)
            return None, info
        text = (outs or [""])[0]
        info["raw"] = text[:400]
        plan = parse_plan(text)
        if plan is None:
            prompt += "\n\nLần trước trả JSON hỏng. Chỉ trả đúng JSON theo schema."
            continue

        template_id = str(plan.get("template_id") or "")
        info["template"] = template_id
        info["evidence"] = str(plan.get("evidence") or "")[:300]
        info["prompt_chars"] = len(prompt)
        if not template_id:
            info["error"] = "no_template_chosen"
            attempts.append({"template": "", "error": "no_template",
                             "evidence": info.get("evidence")})
            if attempt == 0:
                prompt += ("\n\nBạn chưa chọn template. Hãy chọn template_id gần nghĩa "
                           "nhất trong danh sách và điền params/filters/time; "
                           "chỉ để trống nếu thật sự không có template nào.")
                continue
            return None, info
        template = next((t for t in templates if t.id == template_id), None)
        if template is None:
            attempts.append({"template": template_id, "error": "unknown_template",
                             "evidence": info.get("evidence")})
            prompt += (f"\n\nLần trước chọn template_id không có trong danh sách: "
                       f"{template_id}. Chỉ chọn đúng id đã liệt kê.")
            continue

        # LLM hay chọn .top nhưng vẫn điền limit>1 ("3 khách mua nhiều nhất").
        # Chuyển sang .rank cùng metric/subject thay vì bắt retry.
        if template.intent == "lookup_single":
            raw_limit = (plan.get("params") or {}).get("limit")
            try:
                n_limit = int(raw_limit) if raw_limit not in (None, "") else 1
            except (TypeError, ValueError):
                n_limit = 1
            if n_limit > 1:
                alt_id = template.id.replace(".top", ".rank")
                alt = next((t for t in catalog if t.id == alt_id), None)
                if alt is not None:
                    template, template_id = alt, alt.id
                    info["template"] = alt.id
            # Nhiều kỳ + "kỳ nào ... nhất" ⇒ so sánh chuỗi và trả nhãn kỳ.
            if (n_limit <= 1 and template.subject in ("day", "week", "month")
                    and len(windows) > 1):
                peak = next((t for t in catalog
                             if t.id == f"{template.metric}.window.peak"), None)
                if peak is not None:
                    template, template_id = peak, peak.id
                    info["template"] = peak.id

        confidence = plan.get("confidence")
        try:
            info["confidence"] = float(confidence)
        except (TypeError, ValueError):
            info["confidence"] = None

        spec, errs = template.to_spec(plan, windows)
        if spec is not None:
            errs = validate_spec(spec, ctx, windows)
            has_entity = any(f.get("field") in ("product", "customer")
                             for f in (spec.filters or []))
            ok_sem, sem_reason = metric_compatible(nd(question), spec.metric,
                                                   spec.output, has_entity=has_entity)
            if not ok_sem:
                errs.append(f"metric_domain_mismatch:{sem_reason}")
            ok_sub, sub_reason = subject_compatible(nd(question), spec.subject)
            if not ok_sub:
                errs.append(f"subject_mismatch:{sub_reason}")
            # "Bán chạy" chỉ áp cho chiều sản phẩm; "tháng nào bán nhiều tiền
            # nhất" là doanh thu theo tháng, không phải bestseller.
            if spec.subject in (None, "none", "product"):
                best_default = getattr(knobs, "bestseller_metric", "qty")
                ok_bs, bs_reason = bestseller_compatible(nd(question), spec.metric,
                                                         default=best_default)
                if not ok_bs:
                    errs.append(f"bestseller_mismatch:{bs_reason}")
        if errs:
            info["errors"] = errs
            attempts.append({"template": template_id, "errors": errs})
            prompt += f"\n\nPlan trước bị từ chối: {'; '.join(errs)}. Sửa lại."
            continue

        info["spec"] = spec.to_dict()
        plan_sql = compile_spec(spec, ctx, knobs, windows, as_of)
        info["sql"] = plan_sql.sql[:600]
        res = run_sql(ctx.con, plan_sql.sql)
        verify_errs = verify_result(res, spec)
        if verify_errs:
            info["verify_errors"] = verify_errs
            attempts.append({"template": template_id, "verify_errors": verify_errs})
            prompt += (f"\n\nKết quả template trước không dùng được: "
                       f"{'; '.join(verify_errs)}. Chọn template khác phù hợp hơn.")
            continue
        ans = to_submission(plan_sql, res, spec, spec.output, ctx, knobs, windows)
        if ans.type == AnswerType.ABSTAIN.value:
            info["abstain"] = True
            attempts.append({"template": template_id, "abstain": True})
            return None, info
        attempts.append({"template": template_id, "ok": True})
        return ans, info
    info["error"] = "planner_retries_exhausted"
    return None, info


def _run_legacy(question: str, ctx: BizContext, knobs: Knobs,
                windows: list[TimeWindow], entities: list[str], as_of,
                llm: Any) -> tuple[Answer | None, dict[str, Any]]:
    info: dict[str, Any] = {"path": "spec"}
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
    graph_errs = semantic_graph_issues(question, ctx.graph or {}, spec) \
        if os.environ.get("DATAMATE_SEMANTIC_GRAPH", "1") != "0" else []
    if graph_errs:
        info["graph_errors"] = graph_errs
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
