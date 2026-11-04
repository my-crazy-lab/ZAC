"""Bộ lọc điều kiện số từ câu hỏi (M6).

Luật rulebook §2: "Quá N, hơn N, trên N, dưới N" ⇒ **không** gồm N;
"Từ N trở lên" ⇒ gồm N.
"""

from __future__ import annotations

import re

from text.normalize import nd

_NUM = r"(\d+(?:[.,]\d+)?)"

_SUFFIX_MULT = {
    "k": 1e3,
    "ng": 1e3,
    "nghin": 1e3,
    "ngan": 1e3,
    "tr": 1e6,
    "trieu": 1e6,
    "ty": 1e9,
    "b": 1e9,
}

_GT_RE = re.compile(
    r"\b(?:qua|hon|tren|lon hon|nhieu hon|it hon|toi da|at least|more than)\b"
)
_LT_RE = re.compile(r"\b(?:duoi|it hon|nho hon|duoi hon)\b")
_GE_RE = re.compile(r"\b(?:tu .*? tro len|tu .*? tro len|tro len)\b")
_LE_RE = re.compile(r"\b(?:tu .*? tro xuong|tro xuong)\b")

_NORM_RE = re.compile(
    rf"(?P<num>{_NUM})\s*(?P<suf>nghin|ng|ngan|trieu|tr|ty|k|b)?", re.IGNORECASE
)


def _parse_number(text: str) -> float | None:
    m = _NORM_RE.search(text)
    if not m:
        return None
    num = m.group("num").replace(".", "").replace(",", ".")
    try:
        val = float(num)
    except ValueError:
        return None
    suf = (m.group("suf") or "").lower()
    if suf:
        val *= _SUFFIX_MULT.get(suf, 1.0)
    return val


def extract_having(q_nd: str) -> dict | None:
    """Rút điều kiện số: ``{"op": ">", "value": 2000000}`` hoặc ``None``."""
    if not q_nd:
        return None
    text = nd(q_nd)
    # "tu N tro len" / "tu N tro xuong" phải thắng trước
    m_ge = re.search(rf"\btu\s+(?P<num>{_NUM})\s*(?P<suf>nghin|ng|trieu|tr|ty|k|b)?\s*(?:tro len|tro len)", text)
    if m_ge:
        val = _parse_number(m_ge.group(0))
        if val is not None:
            return {"op": ">=", "value": int(val) if float(val).is_integer() else val}
    m_le = re.search(rf"\btu\s+(?P<num>{_NUM})\s*(?P<suf>nghin|ng|trieu|tr|ty|k|b)?\s*(?:tro xuong|truoc)", text)
    if m_le:
        val = _parse_number(m_le.group(0))
        if val is not None:
            return {"op": "<=", "value": int(val) if float(val).is_integer() else val}
    m_num = re.search(rf"\b{_NUM}\s*(?:nghin|ng|trieu|tr|ty|k|b)?", text)
    if not m_num:
        return None
    val = _parse_number(m_num.group(0))
    if val is None:
        return None
    head = text[: m_num.start()]
    if _GE_RE.search(text):
        op = ">="
    elif _LE_RE.search(text):
        op = "<="
    elif _GT_RE.search(head) or _GT_RE.search(text):
        op = ">"
    elif _LT_RE.search(text):
        op = "<"
    else:
        return None
    return {"op": op, "value": int(val) if float(val).is_integer() else val}
