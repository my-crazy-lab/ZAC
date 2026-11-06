"""Kiểm tra đáp án có đúng "kiểu" câu hỏi đòi không (M12b).

Sai = −1, bỏ = 0, nên đáp án lệch kiểu rõ ràng (hỏi đếm đơn mà đáp
tổng tiền, hỏi % mà đáp số tiền thô, hỏi ngày nào mà đáp tên người)
thà bỏ chứ không nộp. Luật cứng, không gọi LLM.
"""

from __future__ import annotations

import re
from typing import Any

_MONEY_HINT = r"tiền|giá trị|doanh thu|dthu|thu về|giá |trung bình|tổng thu|chi phí|nợ"

_RE_PERCENT = re.compile(
    r"%\s|phần trăm|tỉ lệ|ti le|ty le|bnhiu %|bao nhiu %|mấy %|may %|bao nhiêu %|chiếm")
_RE_DATE = re.compile(
    r"ngày nào|ngay nao|hôm nào|hom nao|ngày bao nhiêu|ngay nao.*(cao|thấp) nhất")
_RE_LIST = re.compile(
    r"top\s*\d|liệt kê|liet ke|kể (ra|tên)|mỗi tháng|moi thang|những gì|nhung gi"
    r"|theo từng|từng tháng|cho tôi \d|cho toi \d")
_RE_MONEY = re.compile(_MONEY_HINT)
_RE_COUNT = re.compile(
    r"đơn|don|khách|khach|đợt|dot|\bkg\b|người|nguoi|sản phẩm|san pham|loại|loai"
    r"|con nợ|co bao|bao nhieu don|bao nhiu don")

PERCENT_ABS_MAX = 10000.0   # gold train: max 391 — biên rất rộng, chỉ chặn số tiền lọt sang
COUNT_MAX = 1_000_000       # đáp đếm là số nguyên nhỏ; tổng tiền hàng triệu không phải đáp đếm


def expect_kind(question: str) -> str:
    """Đoán kiểu đáp án câu hỏi đòi: percent | date | list | count | other."""
    t = (question or "").lower()
    if _RE_PERCENT.search(t):
        return "percent"
    if _RE_DATE.search(t):
        return "date"
    if _RE_LIST.search(t):
        return "list"
    if _RE_MONEY.search(t):
        return "other"
    if _RE_COUNT.search(t):
        return "count"
    return "other"


def check_candidate(question: str, candidate: Any) -> tuple[bool, str]:
    """Trả (True, '') nếu đáp án hợp kiểu câu hỏi, ngược lại (False, lý do)."""
    kind = expect_kind(question)
    ptype = getattr(candidate, "type", None)
    value = getattr(candidate, "value", None)
    num = isinstance(value, (int, float)) and not isinstance(value, bool)

    if ptype == "percent" and kind != "percent":
        return False, "percent_pred_nonpercent_q"
    if ptype == "date" and kind != "date":
        return False, "date_pred_nondate_q"
    if ptype in ("list", "table") and kind != "list":
        return False, "list_pred_nonlist_q"
    if kind == "percent" and not (
            ptype == "percent" or (ptype == "number" and num and abs(value) <= PERCENT_ABS_MAX)):
        return False, "percent_q_badpred"
    if kind == "date" and ptype != "date":
        return False, "date_q_badpred"
    if kind == "list" and ptype not in ("list", "table"):
        return False, "list_q_badpred"
    if kind == "count" and not (
            ptype == "number" and num and float(value).is_integer() and 0 <= value <= COUNT_MAX):
        return False, "count_q_badpred"
    return True, ""
