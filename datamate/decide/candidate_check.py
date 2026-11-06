"""Kiểm tra đáp án có đúng "kiểu" câu hỏi đòi không (M12b).

Sai = −1, bỏ = 0, nên đáp án lệch kiểu rõ ràng (hỏi đếm đơn mà đáp
tổng tiền, hỏi % mà đáp số tiền thô, hỏi ngày nào mà đáp tên người)
thà bỏ chứ không nộp. Luật cứng, không gọi LLM.
"""

from __future__ import annotations

import re
from typing import Any

_STRONG_MONEY = (
    r"trung bình|trung binh|bình quân|binh quan|giá trị|gia tri|thu về|thu ve"
    r"|tổng thu|tong thu|tổng tiền|tong tien|tổng dthu|tong dthu"
    r"|tổng doanh thu|tong doanh thu|tổng giá trị|tong gia tri|total bn"
)
_WEAK_MONEY = r"tiền|tien|doanh thu|dthu|revenue|giá |gia |nợ|chi phí|chi phi"

# Đơn vị đếm được. "bao" vắng mặt (lẫn với "bao nhiêu"), "ngày" bắt riêng
# bằng mẫu "mấy/bao nhiêu ngày" (không lẫn trạng ngữ "trong ngày hôm nay").
_COUNT_UNIT = (
    r"đơn|don|khách|khach|đợt|dot|\bkg\b|người|nguoi|sản phẩm|san pham|mặt hàng|mat hang"
    r"|loại|loai|con nợ|\bly\b|\bcốc\b|coc|đĩa|dia|cục|cuc|chai|lon|\bthùng\b|thung"
    r"|gói|goi|cuộn|cuon|\bhộp\b|hop|chiếc|chiec|\bcái\b|cai|\bmón\b|mon|kiện|kien"
)
_COUNT_Q = (
    r"mấy|may |bao nhiêu|bao nhiu|bao nhieu|đếm|dem|\bsố\b|co bao|được mấy|đc mấy"
    r"|ra bao|bán.*mấy"
)
_RE_STRONG_MONEY = re.compile(_STRONG_MONEY)
_RE_COUNT_UNIT = re.compile(_COUNT_UNIT)
_RE_COUNT_Q = re.compile(_COUNT_Q)
_RE_COUNT_DAYS = re.compile(r"(mấy|bao nhiêu|bao nhiu|bao nhieu) ngày")

# "0,1%" trong tên hàng (otrivin 0,1%) là nồng độ, không phải câu hỏi tỉ lệ —
# phải loại trước khi tìm dấu %.
_RE_CONCENTRATION = re.compile(r"\d+[,.]\d*\s*%")
_RE_RATE_WORD = re.compile(
    r"phần trăm|phan tram|tỉ lệ|ti le|tỷ lệ|ty le|chiếm|chiem|đóng góp|dong gop")
_RE_PERCENT_ASK = re.compile(
    r"bnhiu|bao nhiu|bao nhiêu|bao nhieu|mấy|may |nhiêu|nhieu|tăng|tang|giảm|giam"
    r"|hơn|hon|kém|kem|bằng|bang|chênh|chenh")


def _looks_like_percent(t: str) -> bool:
    if _RE_RATE_WORD.search(t):
        return True
    stripped = _RE_CONCENTRATION.sub(" ", t)
    return "%" in stripped and _RE_PERCENT_ASK.search(stripped) is not None
_RE_DATE = re.compile(
    r"ngày nào|ngay nao|hôm nào|hom nao|ngày bao nhiêu|ngay nao.*(cao|thấp) nhất")
_RE_LIST = re.compile(
    r"top\s*\d|liệt kê|liet ke|kể (ra|tên)|mỗi tháng|moi thang|những gì|nhung gi"
    r"|theo từng|từng tháng|cho tôi \d|cho toi \d")
_RE_WEAK_MONEY = re.compile(_WEAK_MONEY)
# Câu hỏi đúng/sai: kết thúc bằng "không?", "đúng không", "phải không".
_RE_YES_NO = re.compile(
    r"(dung khong|đúng không|phai khong|phải không|hay khong|hay không"
    r"|(khong|không|ko|hok|chua|chưa)\s*[?.!]*$)")

PERCENT_ABS_MAX = 10000.0   # gold train: max 391 — biên rất rộng, chỉ chặn số tiền lọt sang
COUNT_MAX = 1_000_000       # đáp đếm là số nguyên nhỏ; tổng tiền hàng triệu không phải đáp đếm


def expect_kind(question: str) -> str:
    """Đoán kiểu đáp án câu hỏi đòi: percent | date | list | count | other."""
    t = (question or "").lower()
    if _looks_like_percent(t):
        return "percent"
    if _RE_YES_NO.search(t.strip()):
        return "boolean"
    if _RE_DATE.search(t):
        return "date"
    if _RE_LIST.search(t):
        return "list"
    if _RE_STRONG_MONEY.search(t):
        return "other"
    if (_RE_COUNT_UNIT.search(t) and _RE_COUNT_Q.search(t)) or _RE_COUNT_DAYS.search(t):
        return "count"
    if _RE_WEAK_MONEY.search(t):
        return "other"
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
    # Kể cả đáp án đã gắn nhãn "percent": engine/LLM đôi khi gắn nhãn đúng
    # nhưng nhét số tiền thô vào value (vd percent=360000). Gold train max 391.
    if kind == "percent" and not (
            ptype in ("percent", "number") and num and abs(value) <= PERCENT_ABS_MAX):
        return False, "percent_q_badpred"
    if kind == "date" and ptype != "date":
        return False, "date_q_badpred"
    if kind == "list" and ptype not in ("list", "table"):
        return False, "list_q_badpred"
    if kind == "boolean" and ptype != "boolean":
        return False, "boolean_q_badpred"
    if kind == "count" and not (
            ptype == "number" and num and float(value).is_integer() and 0 <= value <= COUNT_MAX):
        return False, "count_q_badpred"
    return True, ""
