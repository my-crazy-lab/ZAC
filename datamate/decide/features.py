"""Đặc trưng cho bộ quyết định trả lời (M12)."""

from __future__ import annotations

import re
from dtypes import BizContext, EntityMatch, TimeWindow
from text.normalize import nd

# Nhóm câu hỏi
GROUPS = ("core", "tail", "null", "other")

FEATURE_NAMES = [
    "schema_conf", "has_time", "has_entity", "has_filter_value", "n_windows",
    "metric_known", "subject_known", "question_len", "has_number", "has_percent",
    "has_comparison", "has_rank", "has_list", "has_date", "caps_count",
    "metric_revenue", "metric_qty", "metric_orders", "metric_aov",
    "intent_rank", "intent_compare", "intent_aggregate", "out_number", "out_list",
    "out_percent", "out_string", "n_filters", "n_entities",
]


def extract_features(question: str, ctx: BizContext, windows: list[TimeWindow],
                     entities: list[EntityMatch] | None = None,
                     spec_metric: str | None = None,
                     spec_subject: str | None = None,
                     spec_intent: str | None = None,
                     spec_output: str | None = None,
                     unresolved: list[str] | None = None) -> dict[str, float]:
    """Trả vector đặc trưng (giá trị số)."""
    q = nd(question)
    ents = entities or []
    feats: dict[str, float] = {
        "schema_conf": float(ctx.schema_conf),
        "has_time": 1.0 if windows else 0.0,
        "has_entity": 1.0 if ents else 0.0,
        "has_filter_value": 1.0 if any(e.score >= 0.85 for e in ents) else 0.0,
        "n_windows": float(len(windows)),
        "metric_known": 1.0 if spec_metric else 0.0,
        "subject_known": 1.0 if spec_subject else 0.0,
        "question_len": min(1.0, len(q.split()) / 25.0),
        "has_number": 1.0 if re.search(r"\d", q) else 0.0,
        "has_percent": 1.0 if "%" in q or "phan tram" in q else 0.0,
        "has_comparison": 1.0 if re.search(r"so voi|tang |giam |chay ", q) else 0.0,
        "has_rank": 1.0 if re.search(r"nhat|nhieu nhat|top ", q) else 0.0,
        "has_list": 1.0 if re.search(r"liet ke|danh sach|nhung ", q) else 0.0,
        "has_date": 1.0 if re.search(r"ngay ", q) else 0.0,
        "caps_count": min(1.0, len(ctx.data_caps or ()) / 12.0),
        "metric_revenue": 1.0 if spec_metric == "revenue" else 0.0,
        "metric_qty": 1.0 if spec_metric == "qty" else 0.0,
        "metric_orders": 1.0 if spec_metric == "orders" else 0.0,
        "metric_aov": 1.0 if spec_metric == "aov" else 0.0,
        "intent_rank": 1.0 if spec_intent in ("rank_top", "lookup_single") else 0.0,
        "intent_compare": 1.0 if spec_intent == "compare_periods" else 0.0,
        "intent_aggregate": 1.0 if spec_intent == "aggregate_total" else 0.0,
        "out_number": 1.0 if spec_output == "number" else 0.0,
        "out_list": 1.0 if spec_output == "list" else 0.0,
        "out_percent": 1.0 if spec_output == "percent" else 0.0,
        "out_string": 1.0 if spec_output == "string" else 0.0,
        "n_filters": 0.0,
        "n_entities": float(len(ents)),
    }
    return feats


def feature_vector(feats: dict[str, float]) -> list[float]:
    return [float(feats.get(name, 0.0)) for name in FEATURE_NAMES]


def group_of(question: str, is_null: bool = False) -> str:
    from dev.tag_group import tag_group

    return tag_group(question, is_null)
