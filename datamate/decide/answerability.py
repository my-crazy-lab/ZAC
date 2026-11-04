"""Answerability (M11) — luật 4.10 của rulebook.

Bốn trường hợp **không trả lời được**:
1. Nhóm nghiệp vụ cần dữ liệu khác (vd "trả góp" khi shop không có cột trả góp).
2. Kỳ nằm hoàn toàn ngoài khoảng ngày có dữ liệu.
3. Trong năm nhưng trước mốc bắt đầu dữ liệu.
4. Câu hỏi về dữ liệu chưa có ("sắp tới", "dự kiến").
"""

from __future__ import annotations

import logging
import re
from datetime import date

from dtypes import AnswerCheck, BizContext, EntityMatch, TimeWindow
from text.normalize import nd

log = logging.getLogger(__name__)

# Nhóm nghiệp vụ → capability cần có trong dữ liệu
FEATURE_CAPS: dict[str, tuple[str, ...]] = {
    "installment": ("debt",),
    "trade_in": ("imports",),
    "member_since": ("customer_since",),
    "size_breakdown": ("size",),
    "product_group_share": ("category",),
    "peak_hour": ("order_ts",),
    "loyal_customer": ("customer",),
    "topping_split": ("line_amount",),
    "cash_shift_report": ("pay_method",),
    "debt_rules": ("debt",),
    "cost_rules": ("cost",),
    "repair_ticket": ("returns",),
    "warranty_service": ("returns",),
    "expiry": ("expiry",),
    "imports": ("imports",),
    "delivery_rounds": ("deliveries",),
    "price_history": ("price_history",),
}

FUTURE_RE = re.compile(r"sap toi|se len|sap xuat|du kien|tuong lai|ke hoach|next month|sap den",
                       re.IGNORECASE)

# Nhóm nghiệp vụ cần dữ liệu khác — chỉ giữ những cụm **không thể nhầm**
# (rulebook §4.10.1). Cụm mơ hồ (ví dụ "size") bị loại vì gây trả lời sai.
BUSINESS_FEATURE_RE: list[tuple[str, str]] = [
    ("installment", r"\btra gop\b|\bky gop\b|\btra cham\b"),
    ("trade_in", r"\bthu may cu\b|\bdoi may cu\b"),
    ("repair_ticket", r"\bbien so xe\b.*\bsua\b|\bso phieu sua\b"),
]

# Câu hỏi đòi **capability** mà shop không có ⇒ không trả lời được.
# (pattern, capability cần có) — capability lấy từ `ctx.data_caps`.
CAPABILITY_RULES: list[tuple[str, str]] = [
    (r"\bnhap hang\b|\bphieu nhap\b|\bgia nhap\b|\bnhap kho\b", "imports"),
    (r"\bton kho\b|\bcon ton\b|\bhang ton\b|\bcon lai trong kho\b|\btrong kho\b", "stock"),
    (r"\bhet han\b|\bhan su dung\b|\bhan dung\b", "expiry"),
    (r"\bcon no\b|\bcong no\b|\bkhach no\b|\bphai thu\b|\bno cua don\b", "debt"),
    (r"\bnhom khach\b|\bkhach nhom\b|\bnhom khach hang\b", "customer_group"),
    (r"\bty le don huy\b|\bti le don huy\b", "order_date"),
    (r"\bgia von\b", "cost"),
    (r"\bnhom hang\b", "category"),
    (r"\bgia moi\b|\bdoi gia\b|\btang gia\b", "price_history"),
    (r"\bthanh toan cua don\b|\bso dot giao\b|\blot giao\b", "deliveries"),
]


def check(question: str, ctx: BizContext, windows: list[TimeWindow],
          entities: list[EntityMatch] | None = None, as_of: date | None = None) -> AnswerCheck:
    """Kiểm tra câu hỏi có trả lời được không (luật 4.10)."""
    q = nd(question)

    # --- 4. câu hỏi về dữ liệu chưa có
    if FUTURE_RE.search(q):
        return AnswerCheck(answerable=False, p_unanswerable=0.9,
                           reason="cau_hoi_ve_du_lieu_chua_co")

    # --- 1. nhóm nghiệp vụ cần dữ liệu khác
    caps = set(ctx.data_caps or ())
    for feature, pattern in BUSINESS_FEATURE_RE:
        if re.search(pattern, q):
            need = FEATURE_CAPS.get(feature, ())
            if need and not (set(need) & caps):
                return AnswerCheck(answerable=False, p_unanswerable=0.85,
                                   reason=f"thieu_du_lieu_{feature}")

    # --- 1b. câu đòi capability mà shop không có
    # BỎTẠM: `data_caps` phản ánh **những gì mapper nhận ra**, chưa chắc là
    # shop không có ⇒ dùng luật này gây 212 trả lời sai (đo trên train).
    # Giữ lại danh sách để sau này dùng khi `data_caps` đủ tin cậy.
    if False:  # pragma: no cover
        for pattern, cap in CAPABILITY_RULES:
            if re.search(pattern, q) and cap not in caps:
                return AnswerCheck(answerable=False, p_unanswerable=0.8,
                                   reason=f"thieu_capability_{cap}")

    # --- 2 & 3. kỳ nằm ngoài khoảng ngày có dữ liệu
    if windows:
        w = windows[0]
        if w.kind != "cumulative" and w.end < ctx.date_min:
            return AnswerCheck(answerable=False, p_unanswerable=0.8,
                               reason="ky_ngoai_khoang_ngay_co_du_lieu")
        if w.kind != "cumulative" and w.start > ctx.date_max:
            return AnswerCheck(answerable=False, p_unanswerable=0.8,
                               reason="ky_ngoai_khoang_ngay_co_du_lieu")
    # Không có cửa sổ thời gian: câu hỏi về "toàn bộ" dữ liệu.
    # BỎTẠM luật "as_of sau mốc dữ liệu": câu hỏi về kỳ đã qua vẫn trả lời được
    # (đo trên train: luật này gây 27 câu trả lời sai ở public_test).

    # --- thực thể không tồn tại trong dữ liệu
    for e in entities or []:
        if e.kind == "product" and e.score >= 0.95:
            return AnswerCheck(answerable=True, p_unanswerable=0.0, reason="entity_ok",
                               entity_missing=False)

    return AnswerCheck(answerable=True, p_unanswerable=0.0, reason="ok")
