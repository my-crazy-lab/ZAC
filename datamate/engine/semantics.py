"""So khớp ngữ nghĩa câu hỏi ↔ metric (schema-linking guard).

Bài học từ full-train: lỗi lớn nhất không phải tính sai SQL mà là **chọn sai
miền dữ liệu** — hỏi phiếu nhập nhưng chạy metric doanh thu, hỏi đơn huỷ
nhưng đếm mọi đơn. Câu trả lời vẫn ra một số trông hợp lý nên cửa kiểu đáp
án không chặn được.

Lớp này khai báo hai phía rồi so khớp:

- ``MetricDef.domain`` (registry): sales | purchase | inventory | debt.
- Tín hiệu chủ đề trong câu: từ vựng nghiệp vụ, không phải mẫu câu cụ thể.

Không phụ thuộc id, shop hay đáp án. Khi hai phía lệch nhau, ``predict`` bỏ
câu (0 điểm) thay vì nộp số sai (−1), và ``candidate_specs`` ưu tiên metric
đúng miền để vẫn có cơ hội trả lời đúng.
"""

from __future__ import annotations

import re

from engine.registry import get as get_metric

# --- miền dữ liệu ---------------------------------------------------------

DOMAIN_PATTERNS: dict[str, re.Pattern[str]] = {
    "purchase": re.compile(
        r"\bnhap hang\b|\bphieu nhap\b|\bgia nhap\b|\bnhap kho\b|\bnha cung cap\b"
        r"|\bncc\b|\bnhap vao\b|\btien nhap\b|\bnhap\b"),
    "inventory": re.compile(
        r"\bton kho\b|\bcon ton\b|\bhang ton\b|\bton cuoi\b|\btrong kho\b"
        r"|\bhet hang\b|\blo hang\b|\bhan su dung\b|\bhan dung\b|\bhsd\b"),
    "debt": re.compile(
        r"\bcong no\b|\bcon no\b|\bkhach no\b|\btuoi no\b|\bthu no\b|\btra no\b"
        r"|\btra gop\b|\bghi no\b|\bno cua\b|\bphai thu\b"),
}

# Metric mặc định của mỗi miền, xếp theo mức phổ biến của câu hỏi.
DOMAIN_METRICS: dict[str, tuple[str, ...]] = {
    "purchase": ("import_amount", "import_avg_price"),
    "inventory": ("stock", "stock_value", "expiring", "stock_split_unit"),
    "debt": ("debt", "debt_age"),
}

# --- tín hiệu trạng thái đơn ---------------------------------------------

_STATUS = r"(?:huy|hủy|tra hang|trả hàng|hoan hang|hoàn hàng|doi tra|đổi trả)"
_COUNT = r"(?:dem|đếm|bao nhieu|bao nhiu|mấy|may|so luong|số lượng|\bso\b|\bsố\b)"
STATUS_COUNT_RE = re.compile(
    rf"{_COUNT}[^\n]{{0,40}}{_STATUS}|{_STATUS}[^\n]{{0,30}}"
    rf"(?:{_COUNT}|don|đơn|phieu|phiếu)")
STATUS_RATE_RE = re.compile(
    rf"(?:ti le|tỷ lệ|tỉ lệ|ty le|phan tram|phần trăm|%|chiem|chiếm)"
    rf"[^\n]{{0,30}}{_STATUS}|{_STATUS}[^\n]{{0,30}}"
    rf"(?:ti le|tỷ lệ|tỉ lệ|ty le|phan tram|phần trăm|%)")


def topic_domains(q_nd: str) -> set[str]:
    """Miền dữ liệu mà câu hỏi nhắc tới (có thể nhiều)."""
    return {d for d, pat in DOMAIN_PATTERNS.items() if pat.search(q_nd)}


def domain_of(metric: str | None) -> str | None:
    m = get_metric(metric)
    return m.domain if m else None


def is_status_question(q_nd: str) -> bool:
    return bool(STATUS_COUNT_RE.search(q_nd) or STATUS_RATE_RE.search(q_nd))


def prefers_average(q_nd: str) -> bool:
    return bool(re.search(r"binh quan|bình quân|trung binh|trung bình|don gia|đơn giá",
                          q_nd))


def prefers_value(q_nd: str) -> bool:
    return bool(re.search(r"gia tri|giá trị|tien|tiền|bao nhieu tien", q_nd))


def preferred_metrics(q_nd: str) -> list[str]:
    """Metric nên thử trước, suy từ miền + chiều đo của câu hỏi."""
    if STATUS_RATE_RE.search(q_nd):
        return ["cancel_rate"]
    if STATUS_COUNT_RE.search(q_nd):
        return ["cancelled_orders"]

    domains = topic_domains(q_nd)
    if len(domains) != 1:
        return []
    domain = next(iter(domains))

    if domain == "purchase":
        order = ("import_avg_price", "import_amount") if prefers_average(q_nd) \
            else ("import_amount", "import_avg_price")
        return list(order)
    if domain == "inventory":
        if re.search(r"het han|hết hạn|han dung|hạn dùng|hsd", q_nd):
            return ["expiring", "stock", "stock_value"]
        if prefers_value(q_nd):
            return ["stock_value", "stock", "expiring"]
        return ["stock", "stock_value", "expiring"]
    if domain == "debt":
        if re.search(r"tuoi no|tuổi nợ", q_nd):
            return ["debt_age", "debt"]
        return ["debt", "debt_age"]
    return []


def metric_compatible(q_nd: str, metric: str | None, output: str | None = None,
                      has_entity: bool = True) -> tuple[bool, str]:
    """Spec có đúng miền câu hỏi hỏi không.

    ``output`` cần thiết cho câu hỏi tỉ lệ: metric đếm đơn huỷ vẫn tính ra
    phần trăm được (``compile`` đổi công thức khi output là percent).
    ``has_entity`` cho biết câu hỏi đã nhận ra đối tượng cụ thể chưa; metric
    ``requires_entity`` mà chưa có thì không nên trả số tổng của shop.
    """
    if not metric:
        return True, ""
    mdef = get_metric(metric)
    if mdef is not None and mdef.requires_entity and not has_entity:
        return False, "entity_required"
    if STATUS_RATE_RE.search(q_nd):
        if metric == "cancel_rate" or (metric == "cancelled_orders" and output == "percent"):
            return True, ""
        return False, "status_rate_needs_cancel_rate"
    if STATUS_COUNT_RE.search(q_nd):
        return (True, "") if metric == "cancelled_orders" else (False, "status_count_needs_cancelled")
    domains = topic_domains(q_nd)
    if len(domains) == 1:
        domain = next(iter(domains))
        if domain_of(metric) != domain:
            return False, f"domain_mismatch:{metric}!={domain}"
    return True, ""
