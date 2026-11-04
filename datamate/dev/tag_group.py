"""Gán nhóm câu hỏi để đo cổng G2 (M8).

``core``  : câu lõi (doanh thu, bán chạy, số đơn…) — ngưỡng khớp cao
``tail``  : câu đuôi (công nợ, tồn kho, giá vốn…) — ngưỡng khớp thấp hơn
``null``  : câu không có đáp án
"""

from __future__ import annotations

import re

from text.normalize import nd

CORE_RE = re.compile(
    r"doanh thu|dthu|ban chay|ban duoc nhieu nhat|so don|so luong|tuan|thang|so voi|"
    r"tang |giam |gia tri don|trung binh|khach da mua|so khach|mat hang|sp |san pham"
)
TAIL_RE = re.compile(
    r"no|ton kho|gia von|loi nhuan|het han|thuoc|xi mang|vat lieu|tang gia|nhap hang|"
    r"cong no|luot giao|dot giao|thanh toan|tra gop|hoa don|ca sang|ca chieu|"
    r"khach trung thanh|khach so p|gia tri ton|het hang|hang ton"
)


def tag_group(question_nd: str, is_null: bool = False) -> str:
    """Nhóm của một câu hỏi (đã bỏ dấu)."""
    if is_null:
        return "null"
    s = nd(question_nd)
    if CORE_RE.search(s):
        return "core"
    if TAIL_RE.search(s):
        return "tail"
    return "other"
