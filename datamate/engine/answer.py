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
from engine.semantics import metric_compatible, prefers_value, preferred_metrics
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
                       "lien tiep", "luon cao hon", "luon thap hon",
                       "cao hon thang truoc", "thap hon thang truoc")),
    ("compare_periods", ("so voi", "tang bao nhieu", "giam bao nhieu", "tang %",
                         "giam %", "hieu chinh", "chay bao nhieu", "thay doi bao nhieu")),
    ("filter_list", ("liet ke", "danh sach", "nhung don", "nhung khach",
                     "nhung mat hang")),
    ("rank_top", ("top ", "nhieu nhat", "it nhat", "nhat", "cao nhat", "thap nhat",
                  "ban chay nhat", "gioi nhat", "hot nhat")),
    ("lookup_single", ("la gi", "la nao", "ten gi", "ai la", "mat hang nao",
                       "khach nao")),
]

# "cửa hàng", "khách hàng", "nhóm hàng" không phải đối tượng mặt hàng.
# Không loại thì câu nào có "cửa hàng" cũng bị xếp hạng theo mặt hàng.
PRODUCT_EXCLUDE_RE = re.compile(r"\b(?:cua|khach|nhom|dong|loai|nha|don)\s+hang\b")

SUBJECT_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("category", ("nhom hang",)),
    ("customer", ("khach hang", "khach ", " ai")),
    ("product", ("mat hang", "san pham", "hang hoa", "mon ", "sp ", "thuoc",
                 " hang nao", "ban chay", "hot nhat", " hang ",
                 "hang ban", "top ")),
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


# Xếp hạng/liệt kê theo **đối tượng**, không theo mốc thời gian. "Tháng
# 11/2025 top 5 hàng bán chạy" từng bị nhóm theo tháng nên trả về ngày.
TEMPORAL_SUBJECTS = {"day", "week", "month"}
RANKING_INTENTS = {"rank_top", "filter_list", "lookup_single"}


def subjects_for_intent(subjects: list[str], intents: list[str]) -> list[str]:
    if intents and intents[0] in RANKING_INTENTS:
        entity_subjects = [s for s in subjects if s not in TEMPORAL_SUBJECTS]
        return entity_subjects or subjects
    return subjects


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
    q_product = PRODUCT_EXCLUDE_RE.sub(" ", q_nd)
    for subject, kws in SUBJECT_KEYWORDS:
        hay_subject = f" {q_product} " if subject == "product" else hay
        source = q_product if subject == "product" else q_nd
        if any(k in source or k in hay_subject for k in kws) and subject not in out:
            out.append(subject)
    return out


# "0,1%" trong tên hàng là nồng độ, không phải yêu cầu tỉ lệ.
_RE_CONCENTRATION = re.compile(r"\d+[,.]\d*\s*%")


def _asks_percent(q_nd: str) -> bool:
    return "%" in _RE_CONCENTRATION.sub(" ", q_nd)


def infer_output(q_nd: str, intent: str, metric: str, subject: str = "none",
                 limit: int | None = None) -> str:
    if intent == "cancel_rate" or _asks_percent(q_nd):
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
        if _asks_percent(q_nd) or "phan tram" in q_nd:
            return "percent"
        return "number"
    if intent == "compare_series":
        if re.search(r"lan luot|theo thu tu|moi thang|tung thang", q_nd):
            return "list"
        if subject in ("day", "month") or "ngay nao" in q_nd or "thang nao" in q_nd:
            return "date"
        return "string"
    if intent == "lookup_single":
        return "string"
    if intent == "group_share":
        return "percent"
    return "number"


LIMIT_ENTITY_WORDS = ("khach", "mat hang", "mon", "san pham", "don hang",
                      "don", "loai", "cua hang")


def infer_check(q_nd: str) -> str:
    """Chiều so sánh cho câu đúng/sai theo chuỗi kỳ."""
    if re.search(r"giam|giảm|thap hon|thấp hơn|kem hon|kém hơn", q_nd):
        return "series_decreasing"
    if re.search(r"tang|tăng|cao hon|cao hơn|lon hon|lớn hơn|nhieu hon|nhiều hơn",
                 q_nd):
        return "series_increasing"
    return "exists"


def infer_limit(q_nd: str) -> int | None:
    m = re.search(r"top\s*(\d{1,2})", q_nd)
    if m:
        return int(m.group(1))
    m = re.search(r"liet ke\s*(\d{1,2})\b", q_nd)
    if m:
        return int(m.group(1))
    # Số đếm tường minh ("3 mặt hàng", "cho tôi 5 khách") thắng "nhất".
    # Từ thời gian (tháng/ngày/...) không bao giờ là limit; ngưỡng
    # "từ X đơn trở lên" cũng không phải limit.
    m = re.search(r"\b(\d{1,2})\s*(" + "|".join(LIMIT_ENTITY_WORDS) + r")\b",
                  q_nd)
    if m and not re.search(r"\d+\s*\w+(\s+\w+){0,2}\s*tro (len|xuong)", q_nd):
        return int(m.group(1))
    if "nhat" in q_nd or "gioi nhat" in q_nd:
        return 1
    return None


def _in_text(key: str, q_nd: str) -> bool:
    if not key:
        return False
    return f" {key} " in f" {q_nd} "


# Giá trị lọc quá chung — khớp sẽ thành nhiễu ("loại khác" không phải nhóm Khác).
GENERIC_VALUES = {"khac", "khong", "khong xac dinh", "hang hoa", "tat ca", "toan bo",
                  "khong ro"}

# Cách nói tương ứng với giá trị lưu trong dữ liệu (đã bỏ dấu, '_' → ' ').
# Chỉ những cụm **không thể nhầm**: "cửa hàng" là shop chứ không phải kênh
# `store`; "nợ"/"vỉ" là nghiệp vụ khác chứ không phải ví điện tử/tên kênh.
VALUE_SYNONYMS: dict[str, tuple[str, ...]] = {
    "store": ("tai quay", "tai cua hang"),
    "phone": ("dien thoai", "qua dien thoai", "ban qua dien thoai"),
    "zalo oa": ("zalo", "zalo oa", "qua zalo"),
    "online": ("online", "truc tuyen"),
    "cash": ("tien mat",),
    "transfer": ("chuyen khoan",),
    "cod": ("cod", "giao hang thu tien"),
    "ewallet": ("vi dien tu",),
    "debt": ("ghi no",),
}

VALUE_FILTER_FIELDS = ("category", "channel", "pay_method", "customer_group", "employee")


def _value_variants(value: str) -> list[str]:
    key = nd(value).replace("_", " ")
    out = [key] + list(VALUE_SYNONYMS.get(key, ()))
    return [v for v in dict.fromkeys(out) if len(v) >= 2]


def _mention_pos(q_nd: str, value: str) -> int | None:
    best: int | None = None
    for variant in _value_variants(value):
        m = re.search(rf"(?<!\w){re.escape(variant)}(?!\w)", q_nd)
        if m is not None:
            best = m.start() if best is None else min(best, m.start())
    return best


def matched_values(q_nd: str, values: list[str]) -> list[str]:
    """Giá trị có xuất hiện trong câu, xếp theo thứ tự được nhắc."""
    hits: list[tuple[int, str]] = []
    for v in values or []:
        if nd(v).replace("_", " ") in GENERIC_VALUES:
            continue
        pos = _mention_pos(q_nd, v)
        if pos is not None:
            hits.append((pos, v))
    hits.sort(key=lambda x: x[0])
    return [v for _, v in hits]


def _add_filter(filters: list[dict], field: str, value: str) -> None:
    for f in filters:
        if f["field"] == field and value in (f.get("values") or []):
            return
    filters.append({"field": field, "op": "=", "values": [value]})


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
            _add_filter(filters, "product", val)
        elif e.kind == "customer":
            _add_filter(filters, "customer", val)
        elif e.kind == "category":
            _add_filter(filters, "category", e.canonical_name)
    # Giá trị liệt kê: khớp **cụm chính xác** sau bỏ dấu, theo thứ tự được
    # nhắc; lấy giá trị đầu tiên cho câu một giá trị (câu nhiều giá trị do
    # `candidate_specs` tách thành list).
    for field in VALUE_FILTER_FIELDS:
        hits = matched_values(q_nd, value_dict.get(field) or [])
        if hits:
            _add_filter(filters, field, hits[0])
    return filters


def candidate_specs(q_nd: str, windows: list[TimeWindow], entities: list[EntityMatch],
                    having: dict | None,
                    value_dict: dict[str, list[str]]) -> list[Spec]:
    """Sinh danh sách spec ứng viên (đã lọc theo khả năng của metric)."""
    has_entity = any(e.kind in ("product", "customer") for e in entities)
    pref = preferred_metrics(q_nd)
    raw_metrics = pref + [m for m in keyword_metrics(q_nd) if m not in pref]
    metrics = [m for m in raw_metrics
               if metric_compatible(q_nd, m, has_entity=has_entity)[0]]
    # Không có tín hiệu nào ⇒ câu tổng quát, mặc định doanh thu. Có tín hiệu
    # nhưng không metric nào dùng được (thiếu đối tượng/miền) ⇒ để trống:
    # trả số doanh thu cho câu hỏi giá một món là sai chắc.
    if not metrics and not raw_metrics:
        metrics = ["revenue"]
    intents = keyword_intents(q_nd) or ["aggregate_total"]
    labels = [w.label for w in windows]
    # Câu liệt kê nhiều kỳ rồi hỏi giá trị từng kỳ ("tháng 1, 2, 3 ghi lần
    # lượt") là chuỗi, không phải tổng. Nhận theo cấu trúc (≥3 cửa sổ + từ
    # chỉ thứ tự), không theo mẫu câu cụ thể.
    if (len(labels) >= 3
            and re.search(r"lan luot|theo thu tu|moi thang|tung thang", q_nd)
            and intents[0] == "aggregate_total"):
        intents = ["compare_series"]
    # Xếp hạng "nhiều tiền / chi tiêu / doanh thu" phải xếp theo metric tiền.
    # Nếu không, "khách mua nhiều tiền nhất" chọn metric đếm khách (customers)
    # và trả về rỗng/tên hàng.
    if intents[0] in ("rank_top", "lookup_single") and prefers_value(q_nd):
        money = [m for m in metrics if get_metric(m) and get_metric(m).is_money]
        if money:
            metrics = [money[0]] + [m for m in metrics if m != money[0]]
        elif "revenue" not in metrics and metric_compatible(
                q_nd, "revenue", has_entity=has_entity)[0]:
            metrics = ["revenue"] + metrics
    subjects = keyword_subjects(q_nd,
                                any(e.kind == "product" for e in entities),
                                any(e.kind == "customer" for e in entities))
    subjects = subjects_for_intent(subjects, intents)
    filters = filters_from(entities, value_dict, q_nd)

    # Câu nêu **nhiều giá trị của cùng một chiều** ("doanh thu Zalo OA và
    # tại quầy", "COD với tiền mặt") là hai phép tính, không phải một bộ
    # lọc gộp. Tách thành list theo thứ tự được nhắc.
    multi_field: str | None = None
    multi_values: list[str] = []
    # "Tổng ... A và B" là một phép cộng, không phải hai đáp án.
    if not re.search(r"\btong\b|tong cong|toan bo", q_nd):
        for field in VALUE_FILTER_FIELDS:
            hits = matched_values(q_nd, value_dict.get(field) or [])
            if len(hits) >= 2:
                multi_field, multi_values = field, hits
                break
    if multi_field:
        filters = [f for f in filters if f["field"] != multi_field]

    # Intent so chuỗi cần **tất cả** cửa sổ trong một spec; các intent khác
    # chỉ dùng một cửa sổ mỗi spec.
    if intents[0] in ("compare_series", "boolean_check") and len(labels) >= 2:
        time_options: list[list[str]] = [labels[:8]]
    else:
        time_options = [[lab] for lab in labels[:2]] or [[]]

    specs: list[Spec] = []
    for intent in intents[:3]:
        for metric in metrics[:3]:
            mdef = get_metric(metric)
            allowed = set(mdef.subjects) if mdef else set()
            cand = [s for s in (subjects[:2] or ["none"]) if s in allowed or s == "none"]
            if not cand:
                cand = ["none"]
            for subject in cand:
                for tlabels in time_options:
                    limit = infer_limit(q_nd)
                    out = infer_output(q_nd, intent, metric, subject, limit)
                    if intent in ("rank_top", "lookup_single"):
                        limit = limit or (1 if intent == "lookup_single" else 3)
                    elif intent == "filter_list":
                        pass  # giữ limit suy ra được (None = toàn bộ)
                    params: dict[str, Any] = {}
                    if intent == "compare_periods":
                        params["compare_mode"] = "pct"
                    elif intent == "boolean_check":
                        params["check"] = infer_check(q_nd)
                    spec_intent = intent
                    if multi_field and intent == "aggregate_total":
                        spec_intent = "multi_value"
                        out = "list"
                        params["multi_field"] = multi_field
                        params["multi_values"] = list(multi_values)
                    specs.append(Spec(
                        intent=spec_intent, metric=metric, subject=subject,
                        filters=list(filters), time=list(tlabels),
                        having=having, order="desc", limit=limit, output=out,
                        params=params,
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
