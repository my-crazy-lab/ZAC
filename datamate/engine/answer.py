"""Pipeline trả lời: sinh spec ứng viên → thực thi → đáp án (M13).

Chung cho ``dev/enumerate_match.py`` (đo tỉ lệ khớp) và ``predict.py`` (sinh
submission) để hai đường đi **giống nhau** như rulebook §9.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Callable

from dtypes import Answer, BizContext, EntityMatch, Knobs, Spec, TimeWindow
from engine.compile import compile_spec, validate_spec
from engine.executor import run_sql
from engine.registry import get as get_metric
from fmt.formatter import to_submission
from text.normalize import nd

log = logging.getLogger(__name__)

MAX_SPECS = 24

METRIC_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("import_avg_price", ("gia nhap binh quan", "gia nhap trung binh")),
    ("import_amount", ("tien nhap", "gia tri phieu nhap", "tong tien phieu nhap")),
    ("debt_age", ("tuoi no",)),
    ("debt", ("cong no", "con no", "khach no", "no phai tra")),
    ("cancelled_orders", ("don huy", "so don huy", "trang thai huy", "bi huy",
                          "ti le huy", "ty le huy", "tiet le huy")),
    ("stock_value", ("gia tri ton", "gia tri hang ton", "gia tri kho")),
    ("stock", ("ton kho", "con ton", "ton cuoi", "hang ton")),
    ("profit", ("loi nhuan", "loi gop")),
    ("aov", ("gia tri trung binh", "trung binh tren mot don", "trung binh mot don",
             "trung binh cua don", "trung binh moi don", "trung binh moi",
             "tb moi don", "binh quan moi don", "binh quan tren mot don",
             "binh quan mot don", "doanh thu binh quan")),
    ("customers", ("so khach", "bao nhieu khach", "khach da mua", "khach mua")),
    ("orders", ("so don", "bao nhieu don", "so phieu ban", "so don hang", "may don",
                "so bill", "so phieu")),
    ("revenue", ("doanh thu", "dthu", "tien ban", "bao nhieu tien",
                 "thu ve bao nhieu tien", "tong gia tri don", "gia tri don")),
    ("qty", ("so luong", "so luong ban", "ban chay", "ban chay nhat",
             "ban duoc bao nhieu (cai|chai|lon|goi|hop|thung|kg|con|tep|thoi|lo|goi|"
             "vi|tuy|vien|phan|ly|tui)",
             "ban bao nhieu (cai|chai|lon|goi|hop|thung|kg|con|tep|thoi|lo|goi|"
             "vi|tuy|vien|phan|ly|tui)",
             "bao nhieu (cai|chai|lon|goi|hop|thung|kg|con|tep|thoi|lo|goi|"
             "vi|tuy|vien|phan|ly|tui)")),
    ("price", ("gia ban", "gia cua hang", "gia 1", "don gia", "gia bao nhieu")),
]

INTENT_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("cancel_rate", ("ty le huy", "tiet le huy", "ti le huy")),
    ("group_share", ("ty trong", "chiem bao nhieu %", "ty le trong", "tỉ trọng")),
    ("compare_series", ("thang nao", "ngay nao", "ky nao")),
    ("boolean_check", ("tang lien tuc", "giam lien tuc", "co tang", "co giam",
                       "lien tiep")),
    ("compare_periods", ("so voi", "tang bao nhieu", "giam bao nhieu", "tang %",
                         "giam %", "hieu chinh", "chay bao nhieu", "thay doi bao nhieu")),
    ("filter_list", ("liet ke", "danh sach", "nhung don", "nhung khach",
                     "nhung mat hang")),
    ("rank_top", ("top ", "nhieu nhat", "it nhat", "nhat", "cao nhat", "thap nhat",
                  "ban chay nhat", "gioi nhat", "hot nhat")),
    ("lookup_single", ("la gi", "la nao", "ten gi", "ai la", "mat hang nao",
                       "khach nao")),
]

SUBJECT_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("category", ("nhom hang",)),
    ("customer", ("khach hang", "khach ", " ai")),
    ("product", ("mat hang", "san pham", "hang hoa", "mon ", "sp ", "thuoc",
                 " hang nao")),
    ("day", ("ngay ",)),
    ("month", ("thang ",)),
    ("channel", ("kenh ",)),
    ("pay_method", ("phuong thuc thanh toan", "hinh thuc thanh toan", "thanh toan")),
    ("employee", ("nhan vien",)),
]

UNIT_WORDS = ("kg", "cai", "chai", "lon", "goi", "hop", "thung", "con", "tep", "thoi",
              "lo", "vi", "tuy", "vien", "phan", "ly", "tui")

CHANNEL_SYNONYMS = {
    "store": "tai quay", "tai cua hang": "tai quay", "cua hang": "tai quay",
    "offline": "tai quay", "online": "online", "zalo oa": "zalo oa",
    "zalo": "zalo", "facebook": "facebook", "tiktok": "tiktok",
    "shopee": "shopee", "lazada": "lazada", "sieu thi": "sieu thi",
}


def keyword_metrics(q_nd: str) -> list[str]:
    return [m for m, kws in METRIC_KEYWORDS if any(k in q_nd for k in kws)]


def keyword_intents(q_nd: str) -> list[str]:
    out: list[str] = []
    for intent, kws in INTENT_KEYWORDS:
        if any(k in q_nd for k in kws) and intent not in out:
            out.append(intent)
    return out


def keyword_subjects(q_nd: str, has_product_entity: bool,
                     has_customer_entity: bool = False) -> list[str]:
    out: list[str] = []
    if has_product_entity:
        out.append("product")
    if has_customer_entity:
        out.append("customer")
    # Đệm trắng hai đầu để từ khóa có dấu cách đầu (" ai", " hang nao")
    # khớp cả đầu câu mà không dính "ngay mai"/"thang nao".
    hay = f" {q_nd} "
    for subject, kws in SUBJECT_KEYWORDS:
        if any(k in q_nd or k in hay for k in kws) and subject not in out:
            out.append(subject)
    return out


def infer_output(q_nd: str, intent: str, metric: str, subject: str = "none",
                 limit: int | None = None) -> str:
    if intent == "cancel_rate" or "%" in q_nd:
        return "percent"
    if intent == "rank_top":
        if limit == 1:
            return "date" if subject in ("day", "month") else "string"
        return "list"
    if intent == "filter_list":
        return "list"
    if intent == "boolean_check":
        return "boolean"
    if intent == "compare_periods":
        if "%" in q_nd or "phan tram" in q_nd:
            return "percent"
        return "number"
    if intent == "compare_series":
        return "date" if "ngay nao" in q_nd else "string"
    if intent == "lookup_single":
        return "string"
    if intent == "group_share":
        return "percent"
    return "number"


def infer_limit(q_nd: str) -> int | None:
    m = re.search(r"top\s*(\d{1,2})", q_nd)
    if m:
        return int(m.group(1))
    if "nhat" in q_nd or "gioi nhat" in q_nd:
        return 1
    return None


def _in_text(key: str, q_nd: str) -> bool:
    if not key:
        return False
    return f" {key} " in f" {q_nd} "


def _unit_filter(q_nd: str) -> list[dict]:
    m = re.search(r"bao nhieu\s+(\w+)", q_nd)
    if not m:
        return []
    unit = m.group(1)
    if unit in UNIT_WORDS:
        return [{"field": "unit_name", "op": "=", "values": [unit]}]
    return []


def filters_from(entities: list[EntityMatch], value_dict: dict[str, list[str]],
                 q_nd: str) -> list[dict]:
    filters: list[dict] = []
    filters.extend(_unit_filter(q_nd))
    for e in entities:
        val = e.code or nd(e.canonical_name)
        if e.kind == "product":
            filters.append({"field": "product", "op": "=", "values": [val]})
        elif e.kind == "customer":
            filters.append({"field": "customer", "op": "=", "values": [val]})
        elif e.kind == "category":
            filters.append({"field": "category", "op": "=", "values": [e.canonical_name]})
    for field in ("channel", "pay_method", "customer_group", "employee"):
        vals = value_dict.get(field) or []
        for v in vals:
            key = nd(v)
            if len(key) >= 2 and _in_text(key, q_nd):
                filters.append({"field": field, "op": "=", "values": [v]})
                break
        for v in vals:
            syn = CHANNEL_SYNONYMS.get(nd(v))
            if syn and _in_text(syn, q_nd):
                filters.append({"field": field, "op": "=", "values": [v]})
                break
    return filters


def candidate_specs(q_nd: str, windows: list[TimeWindow], entities: list[EntityMatch],
                    having: dict | None,
                    value_dict: dict[str, list[str]]) -> list[Spec]:
    """Sinh danh sách spec ứng viên (đã lọc theo khả năng của metric)."""
    metrics = keyword_metrics(q_nd) or ["revenue"]
    intents = keyword_intents(q_nd) or ["aggregate_total"]
    subjects = keyword_subjects(q_nd,
                                any(e.kind == "product" for e in entities),
                                any(e.kind == "customer" for e in entities))
    labels = [w.label for w in windows]
    filters = filters_from(entities, value_dict, q_nd)
    specs: list[Spec] = []
    for intent in intents[:3]:
        for metric in metrics[:3]:
            mdef = get_metric(metric)
            allowed = set(mdef.subjects) if mdef else set()
            cand = [s for s in (subjects[:2] or ["none"]) if s in allowed or s == "none"]
            if not cand:
                cand = ["none"]
            for subject in cand:
                for label in (labels[:2] or [None]):
                    limit = infer_limit(q_nd)
                    out = infer_output(q_nd, intent, metric, subject, limit)
                    if intent in ("rank_top", "lookup_single"):
                        limit = limit or (1 if intent == "lookup_single" else 3)
                    elif intent == "filter_list":
                        limit = None
                    specs.append(Spec(
                        intent=intent, metric=metric, subject=subject,
                        filters=list(filters), time=[label] if label else [],
                        having=having, order="desc", limit=limit, output=out,
                        params={"compare_mode": "pct"} if intent == "compare_periods" else {},
                    ))
    return specs[:MAX_SPECS]


def run_specs(specs: list[Spec], ctx: BizContext, knobs: Knobs,
              windows: list[TimeWindow], as_of,
              accept: Callable[[Answer, Spec], bool] | None = None
              ) -> tuple[Answer | None, Spec | None, dict[str, Any]]:
    """Chạy các spec theo thứ tự; trả (đáp án đầu tiên được chấp nhận, spec, debug)."""
    debug: dict[str, Any] = {"tried": 0, "errors": []}
    for spec in specs:
        errs = validate_spec(spec, ctx, windows)
        if errs:
            debug["errors"].append(errs[0])
            continue
        plan = compile_spec(spec, ctx, knobs, windows, as_of)
        res = run_sql(ctx.con, plan.sql, timeout_s=20, max_rows=1000)
        debug["tried"] += 1
        if res.error:
            debug["errors"].append("exec:" + res.error[:80])
            continue
        ans = to_submission(plan, res, spec, spec.output, ctx, knobs, windows)
        if ans.type == "abstain":
            continue
        if accept is None or accept(ans, spec):
            debug["spec"] = spec.to_dict()
            debug["sql"] = plan.sql[:400]
            return ans, spec, debug
    return None, None, debug
