"""Catalog truy vấn có sẵn cho từng business.

Mỗi ``Template`` là một dạng câu hỏi đã được code hoá: intent + metric +
subject + output + tham số. LLM chỉ chọn ``template_id`` và điền tham số;
SQL do ``engine.compile`` render từ context của shop.

Catalog sinh từ ``engine.registry.REGISTRY`` và capability thật của shop
(views/data_caps), nên không có ``if business_id`` và không có SQL viết tay
cho từng shop.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from dtypes import Spec, TimeWindow
from engine.registry import REGISTRY, MetricDef
from engine.semantics import subject_cues, topic_domains
from text.bm25 import build_bm25
from text.normalize import nd

# Subject có cột chiều tương ứng trong view.
DIMENSION_SUBJECTS = {"product", "category", "customer", "channel", "pay_method",
                      "employee", "customer_group", "supplier"}
# Subject dùng cho chuỗi nhiều kỳ.
SERIES_SUBJECTS = {"day", "week", "month", "window"}

SUBJECT_LABELS = {
    "product": "sản phẩm/mặt hàng",
    "category": "nhóm hàng/ngành hàng",
    "customer": "khách hàng",
    "channel": "kênh bán",
    "pay_method": "phương thức thanh toán",
    "employee": "nhân viên",
    "customer_group": "nhóm khách",
    "supplier": "nhà cung cấp",
    "day": "ngày",
    "week": "tuần",
    "month": "tháng",
    "window": "kỳ",
    "none": "toàn shop",
}

METRIC_LABELS = {
    "revenue": "doanh thu/tiền bán",
    "qty": "số lượng bán",
    "orders": "số đơn",
    "customers": "số khách",
    "aov": "giá trị trung bình mỗi đơn",
    "cancel_rate": "tỷ lệ huỷ",
    "cancelled_orders": "số đơn huỷ",
    "profit": "lợi nhuận",
    "stock": "tồn kho",
    "stock_value": "giá trị tồn kho",
    "debt": "công nợ",
    "debt_age": "tuổi nợ",
    "expiring": "hàng sắp hết hạn",
    "stock_split_unit": "tồn kho theo đơn vị",
    "price": "đơn giá",
    "import_amount": "tiền nhập hàng",
    "import_avg_price": "giá nhập bình quân",
}

# Tham số planner được phép điền. Không chứa SQL/ngày/giá trị tự do.
TEMPLATE_PARAM_KEYS = {
    "limit", "order", "having", "compare_mode", "check", "threshold",
    "expiring_days", "unit_name", "debt_age_stat", "slow_and_high_stock",
    "extra_metrics", "multi_field", "multi_values",
}

ADDITIVE = {"revenue", "qty", "orders", "customers", "profit", "import_amount",
            "cancelled_orders"}
# Metric đã là tỉ lệ/trung bình: xếp hạng theo chiều thời gian dễ sai nghĩa.
RATIO_METRICS = {"aov", "cancel_rate"}
# Metric cần đối tượng cụ thể nhưng vẫn có nghĩa khi tính tổng cho đối tượng đó.
ENTITY_TOTAL_METRICS = {
    "price": "Đơn giá bán của một sản phẩm trong kỳ",
    "import_avg_price": "Giá nhập bình quân của một sản phẩm",
}

# Chỉ những metric này có template point-in-time trả đúng hình dạng list.
POINT_SAFE = {"stock", "debt", "expiring"}


@dataclass(frozen=True)
class Template:
    id: str
    intent: str
    metric: str | None
    subject: str | None
    output: str
    description: str
    params: dict[str, Any] = field(default_factory=dict)
    priority: int = 0
    requires_entity: bool = False
    requires_windows: tuple[str, ...] = ()
    required: tuple[str, ...] = ()

    def to_spec(self, plan: dict[str, Any], windows: list[TimeWindow]) -> tuple[Spec | None, list[str]]:
        """Plan của LLM → ``Spec`` (None nếu tham số không hợp lệ)."""
        errs: list[str] = []
        params = dict(self.params)
        incoming = dict(plan.get("params") or {})
        for key, value in incoming.items():
            if key not in TEMPLATE_PARAM_KEYS:
                errs.append(f"param_unknown:{key}")
                continue
            params[key] = value
        for key in self.required:
            if params.get(key) in (None, "", []):
                errs.append(f"param_required:{key}")
        if errs:
            return None, errs

        order = params.pop("order", None)
        order = str(order) if order not in (None, "") else "desc"
        if order not in ("asc", "desc"):
            errs.append(f"order_invalid:{order}")
        limit = params.pop("limit", None)
        if limit in ("", []):
            limit = None
        if self.intent in ("rank_top", "lookup_single") and limit is None:
            limit = 1 if self.intent == "lookup_single" else 5
        if limit is not None:
            try:
                limit = int(limit)
            except (TypeError, ValueError):
                errs.append(f"limit_invalid:{limit}")
                limit = None
            if limit is not None and limit <= 0:
                errs.append(f"limit_invalid:{limit}")
        having = params.pop("having", None)
        if having in ({}, "", []):
            having = None
        if having is not None and not isinstance(having, dict):
            errs.append("having_invalid")

        labels = [w.label for w in windows]
        time = list(dict.fromkeys(plan.get("time") or []))
        # LLM hay bịa nhãn ISO/tháng thay vì nhãn cửa sổ. Bỏ nhãn lạ; với
        # tổng/xếp hạng thì mặc định "main", với chuỗi/trend thì dùng mọi kỳ.
        time = [lbl for lbl in time if lbl in labels]
        if not time:
            if self.intent == "compare_periods":
                time = [lbl for lbl in ("main", "base") if lbl in labels]
            elif self.intent in ("compare_series", "boolean_check"):
                time = list(labels)
            else:
                time = ["main"] if labels else []
        # Chuỗi/trend thường nói về **tất cả** kỳ đã tách được; LLM hay chỉ
        # liệt kê main/base và làm mất kỳ thứ ba.
        if self.intent in ("compare_series", "boolean_check") and len(labels) > len(time):
            time = list(labels)
        if self.intent == "compare_periods" and "base" not in labels:
            errs.append("compare_periods_needs_base_window")
        if self.intent in ("compare_series", "boolean_check") and len(labels) < 2:
            errs.append("series_needs_two_windows")

        filters = [f for f in (plan.get("filters") or [])
                   if isinstance(f, dict) and (f.get("values") or [])]
        if self.requires_entity and not filters:
            errs.append("entity_required")

        if errs:
            return None, errs
        return Spec(intent=self.intent, metric=self.metric, subject=self.subject,
                    filters=filters, time=time, having=having, order=order,
                    limit=limit, output=self.output, params=params), []


def _metric_available(m: MetricDef, views: set[str], caps: set[str]) -> bool:
    if m.source not in views:
        return False
    if caps and m.caps and not (m.caps & caps):
        return False
    return True


def _template(metric: str, intent: str, subject: str | None, output: str,
              params: dict[str, Any] | None = None, priority: int = 0,
              requires_entity: bool = False,
              requires_windows: tuple[str, ...] = (),
              required: tuple[str, ...] = (),
              template_id: str | None = None,
              description: str | None = None) -> Template:
    metric_label = METRIC_LABELS.get(metric, metric)
    subject_label = SUBJECT_LABELS.get(subject or "none", subject or "toàn shop")
    if intent == "aggregate_total":
        desc = f"Tổng {metric_label} trong kỳ"
    elif intent == "cancel_rate":
        desc = f"Tỷ lệ huỷ đơn trong kỳ"
    elif intent == "rank_top":
        desc = f"{metric_label} theo {subject_label}, xếp hạng top N"
    elif intent == "lookup_single":
        desc = f"{subject_label} có {metric_label} cao nhất/nhất"
    elif intent == "group_share":
        desc = f"Tỷ trọng {metric_label} theo {subject_label}"
    elif intent == "compare_periods":
        desc = f"So sánh {metric_label} giữa kỳ này và kỳ trước"
    elif intent == "compare_series":
        desc = f"Chuỗi {metric_label} theo {subject_label} qua các kỳ"
    elif intent == "boolean_check":
        desc = f"Kiểm tra {metric_label} tăng/giảm liên tục qua các kỳ"
    elif intent == "point_in_time":
        desc = f"{metric_label} tại một thời điểm"
    else:
        desc = f"{metric_label} theo {subject_label}"
    suffix = {
        "aggregate_total": "total",
        "cancel_rate": "rate",
        "rank_top": "rank",
        "group_share": "share",
        "compare_periods": "compare",
        "compare_series": "series",
        "boolean_check": "trend",
        "point_in_time": "point",
        "lookup_single": "top",
    }.get(intent, intent)
    tid = template_id or (f"{metric}.{suffix}" if subject in (None, "none")
                          else f"{metric}.{subject}.{suffix}")
    return Template(id=tid, intent=intent, metric=metric, subject=subject,
                    output=output, description=description or desc,
                    params=dict(params or {}), priority=priority,
                    requires_entity=requires_entity,
                    requires_windows=requires_windows, required=required)


def build_catalog(ctx: Any) -> list[Template]:
    """Sinh catalog từ registry + capability thật của một shop."""
    views = set(getattr(ctx, "views", set()) or set())
    caps = set(getattr(ctx, "data_caps", set()) or set())
    out: list[Template] = []
    for name, m in sorted(REGISTRY.items()):
        if not _metric_available(m, views, caps):
            continue
        if m.domain in ("inventory", "debt"):
            # Snapshot không cộng dồn theo kỳ được: chỉ dùng template point-in-time
            # đã có công thức riêng trong compile.
            if name in POINT_SAFE:
                params: dict[str, Any] = {"limit": 5, "order": "desc"}
                if name == "expiring":
                    params["expiring_days"] = 30
                out.append(_template(name, "point_in_time", None, "list", params,
                                     priority=20, requires_windows=("main",)))
            continue

        if name in ENTITY_TOTAL_METRICS:
            out.append(_template(name, "aggregate_total", "product", m.default_output,
                                 priority=52, requires_entity=True,
                                 description=ENTITY_TOTAL_METRICS[name]))
            continue
        if m.requires_entity:
            # Metric cần đối tượng cụ thể (tuổi nợ một khách) chưa có template
            # render đúng shape ⇒ không đưa vào catalog.
            continue
        if name == "orders":
            out.append(_template("orders", "aggregate_total", None, "number",
                                 {"threshold": None}, priority=52,
                                 required=("threshold",), template_id="orders.threshold",
                                 description="Số đơn có doanh thu/tiền hàng từ X trở lên"))
        if name == "customers":
            out.append(_template("customers", "aggregate_total", None, "number",
                                 {"threshold": None}, priority=52,
                                 required=("threshold",),
                                 template_id="customers.threshold",
                                 description="Số khách mua từ N đơn trở lên"))
        if m.default_output in ("number", "percent"):
            intent = "cancel_rate" if name in ("cancel_rate",) else "aggregate_total"
            out.append(_template(name, intent, None, m.default_output, priority=60))
        if name == "cancel_rate":
            continue

        if name not in RATIO_METRICS:
            for subject in sorted(m.subjects):
                if subject in DIMENSION_SUBJECTS:
                    out.append(_template(name, "aggregate_total", subject,
                                         m.default_output, priority=48,
                                         requires_entity=True))
                    out.append(_template(name, "rank_top", subject, "list",
                                         {"limit": 5, "order": "desc"}, priority=50))
                    out.append(_template(name, "lookup_single", subject, "string",
                                         {"limit": 1, "order": "desc"}, priority=45))
                    if name in ADDITIVE:
                        out.append(_template(name, "group_share", subject, "percent",
                                             {"limit": 5}, priority=35))
                elif subject in SERIES_SUBJECTS and subject != "window":
                    out.append(_template(name, "rank_top", subject, "list",
                                         {"limit": 5, "order": "desc"}, priority=40))
                    out.append(_template(name, "lookup_single", subject, "date",
                                         {"limit": 1, "order": "desc"}, priority=38))
        if name in ADDITIVE:
            out.append(_template(name, "compare_periods", "window", "percent",
                                 {"compare_mode": "pct"}, priority=30,
                                 requires_windows=("main", "base")))
        if m.subjects & SERIES_SUBJECTS:
            out.append(_template(name, "compare_series", "window", "list",
                                 priority=25, requires_windows=("main", "base")))
            out.append(_template(name, "compare_series", "window", "date",
                                 priority=32, requires_windows=("main", "base"),
                                 template_id=f"{name}.window.peak",
                                 description=("Kỳ nào có "
                                              f"{METRIC_LABELS.get(name, name)} cao nhất")))
            out.append(_template(name, "boolean_check", "window", "boolean",
                                 {"check": "series_increasing"}, priority=20,
                                 requires_windows=("main", "base")))

    # giữ một id duy nhất
    seen: set[str] = set()
    unique: list[Template] = []
    for t in sorted(out, key=lambda x: (-x.priority, x.id)):
        if t.id in seen:
            continue
        seen.add(t.id)
        unique.append(t)
    return unique


def render_catalog(templates: list[Template]) -> str:
    lines = []
    for t in templates:
        params = ", ".join(f"{k}={v}" for k, v in sorted(t.params.items())) or "-"
        need = " (cần filter đối tượng)" if t.requires_entity else ""
        lines.append(f"- {t.id}: intent={t.intent} metric={t.metric} "
                     f"subject={t.subject or 'none'} output={t.output} "
                     f"params=[{params}] | {t.description}{need}")
    return "\n".join(lines)


def retrieve_templates(question: str, templates: list[Template], k: int = 12,
                       windows: list[TimeWindow] | None = None,
                       entity_kinds: set[str] | None = None) -> list[Template]:
    """Chọn template liên quan câu hỏi bằng BM25 + miền dữ liệu."""
    if not templates:
        return []
    available_labels = {w.label for w in (windows or [])}
    labels = windows or []
    pool = []
    for t in templates:
        if t.intent == "compare_periods" and "base" not in available_labels:
            continue
        if t.requires_windows and len(labels) < 2:
            continue
        pool.append(t)
    if not pool:
        pool = list(templates)
    bm25 = build_bm25([t.description for t in pool])
    scored = {idx: score for idx, score in bm25.topk(nd(question), len(pool))}
    domains = topic_domains(nd(question))
    cues = subject_cues(nd(question))
    kinds = set(entity_kinds or ())
    ranked: list[tuple[float, Template]] = []
    for idx, t in enumerate(pool):
        # Tổng theo đối tượng chỉ hữu ích khi câu hỏi/entity nhắc đúng chiều đó;
        # nếu không, 12 template ".total" sẽ lấn hết danh sách gửi LLM.
        if (t.intent == "aggregate_total" and t.requires_entity
                and t.subject in DIMENSION_SUBJECTS
                and t.subject not in cues and t.subject not in kinds):
            continue
        score = scored.get(idx, 0.0)
        m = REGISTRY.get(t.metric or "")
        if m is not None and m.domain in domains:
            score += 1.5
        # Câu hỏi nhắc đích danh chiều phân tích (hàng/khách/tháng nào...)
        # phải thấy template của đúng chiều đó, kể cả khi BM25 nghiêng về
        # template thời gian vì câu có "tháng 12/2025".
        if t.subject in cues:
            score += 3.0
        elif t.subject in ("month", "day", "week") and cues and t.subject not in cues:
            score -= 1.0
        if re.search(r"tang lien tuc|giam lien tuc|tang dan|giam dan|co tang|co giam",
                     nd(question)):
            if t.intent in ("boolean_check", "compare_series"):
                score += 3.0
        if re.search(r"so sanh|so voi", nd(question)) and t.intent == "compare_periods":
            score += 2.0
        if (re.search(r"\bnao\b.*\bnhat\b", nd(question))
                and t.intent == "compare_series" and t.subject == "window"):
            score += 3.0
        if t.id.endswith(".threshold"):
            q = nd(question)
            if (not re.search(r"\bdon\b|\bbill\b|\bhoa don\b", q)
                    or not re.search(r"\d", q)):
                score -= 5.0
        if score <= 0 and t.intent != "aggregate_total":
            continue
        ranked.append((score + t.priority / 1000.0, t))
    ranked.sort(key=lambda x: (-x[0], x[1].id))

    # Tổng luôn phải có mặt: câu "bao nhiêu/tổng" rất phổ biến và BM25 có thể
    # không khớp từ vựng ("bill" vs "số đơn"). Giữ tối đa 6 tổng để chừa chỗ.
    out: list[Template] = []
    seen_ids: set[str] = set()
    idx_of = {id(t): i for i, t in enumerate(pool)}

    def total_score(t: Template) -> float:
        s = scored.get(idx_of.get(id(t), -1), 0.0)
        m = REGISTRY.get(t.metric or "")
        if m is not None and m.domain in domains:
            s += 1.5
        return s

    totals = sorted((t for t in pool if t.intent in ("aggregate_total", "cancel_rate")
                     and not t.requires_entity),
                    key=lambda t: (-total_score(t), -t.priority, t.id))
    for t in totals[:6]:
        out.append(t)
        seen_ids.add(t.id)
    per_metric: dict[str, int] = {}
    for _score, t in ranked:
        if len(out) >= k:
            break
        if t.id in seen_ids:
            continue
        key = t.metric or "?"
        if per_metric.get(key, 0) >= 3:
            continue
        per_metric[key] = per_metric.get(key, 0) + 1
        out.append(t)
        seen_ids.add(t.id)
    if not out:
        out = sorted(pool, key=lambda t: (-t.priority, t.id))[:k]
    return out


__all__ = ["Template", "TEMPLATE_PARAM_KEYS", "build_catalog", "render_catalog",
           "retrieve_templates"]
