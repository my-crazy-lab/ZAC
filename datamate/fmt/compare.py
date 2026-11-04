"""Chấm điểm theo rulebook §9 (EXECUTION-MVP.md M0).

Bộ chấm dùng chung cho ``dev/evaluate.py`` và cho vòng dev M8 (đo tỉ lệ khớp).
"""

from __future__ import annotations

import unicodedata
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Hashable

from dtypes import Answer, AnswerType

PUNCT = set(" \t\r\n.,;:!?()[]{}<>\"'`~@#$%^&*_+=|\\/—–-…“”‘’")

_NUM_RE = None  # giữ chỗ; không dùng regex ở đây


def norm_text(s: str) -> str:
    """Bỏ khoảng trắng thừa + hạ chữ thường + bỏ dấu câu (GIỮ dấu tiếng Việt)."""
    if s is None:
        return ""
    s = str(s)
    s = unicodedata.normalize("NFC", s).lower()
    out = "".join(" " if ch in PUNCT else ch for ch in s)
    return " ".join(out.split())


def _to_decimal(x: Any) -> Decimal | None:
    if isinstance(x, bool):
        return None
    if isinstance(x, Decimal):
        return x
    if isinstance(x, int):
        return Decimal(x)
    if isinstance(x, float):
        return Decimal(str(x))
    return None


def norm_number(x: Any, is_money: bool | None = None) -> Decimal | None:
    """Chuẩn hoá số theo luật làm tròn của rulebook §9.

    - Tiền (VND): số nguyên, nửa đồng làm tròn lên (``ROUND_HALF_UP``).
    - Số khác: 2 chữ số thập phân.
    - Chuỗi bị từ chối (chuỗi là sai format).
    """
    d = _to_decimal(x)
    if d is None:
        return None
    if is_money is None:
        is_money = d == d.to_integral_value()
    if is_money:
        return d.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _text_variants(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value]
    return [str(value)]


def _match_text(pred: Any, candidates: list[Any]) -> bool:
    """``pred`` khớp một trong ``candidates`` (so theo norm_text, giữ dấu)."""
    if pred is None:
        return False
    if not isinstance(pred, str):
        pred = str(pred)
    p = norm_text(pred)
    for c in candidates:
        if c is None:
            continue
        if isinstance(c, (list, tuple)):
            for sub in c:
                if norm_text(str(sub)) == p:
                    return True
            continue
        if norm_text(str(c)) == p:
            return True
    return False


def _norm_date(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if len(s) == 7 and s[4] == "-":  # YYYY-MM
        return s
    if len(s) >= 10:
        return s[:10]
    return s


def _same_month(a: str, b: str) -> bool:
    return a[:7] == b[:7]


def _table_rows(value: Any) -> list[list[Any]] | None:
    if not isinstance(value, dict):
        return None
    rows = value.get("rows")
    if not isinstance(rows, list):
        return None
    return [list(r) if isinstance(r, (list, tuple)) else [r] for r in rows]


def _table_columns(value: Any) -> list[Any] | None:
    if not isinstance(value, dict):
        return None
    cols = value.get("columns")
    if not isinstance(cols, list):
        return None
    return list(cols)


def _cell_equal(pred_cell: Any, ref_cell: Any, alias_cells: list[Any]) -> bool:
    if isinstance(ref_cell, str) or isinstance(pred_cell, str):
        cands = [ref_cell] + list(alias_cells)
        return _match_text(pred_cell, cands)
    pn = norm_number(pred_cell)
    rn = norm_number(ref_cell)
    if pn is None or rn is None:
        return pred_cell == ref_cell
    return abs(pn - rn) <= Decimal("1e-9")


def is_correct(pred: Answer, ref: dict[str, Any]) -> bool:
    """Kiểm tra đáp án dự đoán có đúng theo rulebook §9 không."""
    if pred is None or pred.type == AnswerType.ABSTAIN.value:
        return False

    ref_type = str(ref.get("type", ""))
    ref_value = ref.get("answer")
    alias = ref.get("alias") or []

    if ref_value is None:
        # Câu không trả lời được: chỉ đúng khi ta cũng trả unanswerable.
        return pred.type == AnswerType.UNANSWERABLE.value

    if pred.type == AnswerType.UNANSWERABLE.value:
        return False

    if ref_type == AnswerType.NUMBER.value:
        pn = norm_number(pred.value)
        rn = norm_number(ref_value)
        if pn is None or rn is None:
            return False
        is_money = rn == rn.to_integral_value()
        pn2 = norm_number(pn, is_money)
        rn2 = norm_number(rn, is_money)
        return abs(pn2 - rn2) <= Decimal("1e-9")

    if ref_type == AnswerType.PERCENT.value:
        pn = norm_number(pred.value, is_money=False)
        rn = norm_number(ref_value, is_money=False)
        if pn is None or rn is None:
            return False
        return abs(pn - rn) <= Decimal("1e-9")

    if ref_type == AnswerType.BOOLEAN.value:
        if isinstance(pred.value, bool):
            return pred.value == bool(ref_value)
        return str(pred.value).strip().lower() == str(ref_value).strip().lower()

    if ref_type == AnswerType.DATE.value:
        pd = _norm_date(pred.value)
        rd = _norm_date(ref_value)
        if pd is None or rd is None:
            return False
        if len(pd) == 7 or len(rd) == 7:
            return _same_month(pd, rd)
        return pd == rd

    if ref_type == AnswerType.STRING.value:
        cands = [ref_value] + _text_variants(alias)
        return _match_text(pred.value, cands)

    if ref_type == AnswerType.LIST.value:
        if not isinstance(pred.value, (list, tuple)):
            return False
        if not isinstance(ref_value, (list, tuple)):
            return False
        if len(pred.value) != len(ref_value):
            return False
        for i, rv in enumerate(ref_value):
            al: list[Any] = []
            if isinstance(alias, list) and len(alias) == len(ref_value) and isinstance(alias[i], (list, tuple)):
                al = list(alias[i])
            elif isinstance(alias, list) and alias and not isinstance(alias[0], (list, tuple)):
                al = list(alias)
            if not _match_text(pred.value[i], [rv] + al):
                return False
        return True

    if ref_type == AnswerType.TABLE.value:
        prows = _table_rows(pred.value)
        rrows = _table_rows(ref_value)
        if prows is None or rrows is None:
            return False
        pcols = _table_columns(pred.value)
        rcols = _table_columns(ref_value)
        if pcols is None or rcols is None:
            return False
        if len(pcols) != len(rcols):
            return False
        if len(prows) != len(rrows):
            return False
        for i, rrow in enumerate(rrows):
            if len(prows[i]) != len(rrow):
                return False
            for j, rcell in enumerate(rrow):
                al: list[Any] = []
                if isinstance(alias, list) and len(alias) == len(rrows) and isinstance(alias[i], (list, tuple)):
                    if len(alias[i]) == len(rrow) and isinstance(alias[i][j], (list, tuple)):
                        al = list(alias[i][j])
                if not _cell_equal(prows[i][j], rcell, al):
                    return False
        return True

    # Không rõ type: so chuỗi hoá
    return _match_text(pred.value, [ref_value] + _text_variants(alias))


def canon_key(ans: Answer) -> Hashable:
    """Khoá chuẩn hoá để vote/gom nhóm đáp án giống nhau."""
    if ans is None:
        return ("abstain",)
    t = ans.type
    v = ans.value
    if t in (AnswerType.NUMBER.value, AnswerType.PERCENT.value):
        d = norm_number(v)
        if d is None:
            return (t, str(v))
        # làm tròn 6 chữ số có nghĩa
        return (t, float(round(d, 6)))
    if t == AnswerType.BOOLEAN.value:
        return (t, bool(v))
    if t == AnswerType.DATE.value:
        d = _norm_date(v)
        return (t, d)
    if t == AnswerType.STRING.value:
        return (t, norm_text(str(v)))
    if t == AnswerType.LIST.value:
        if not isinstance(v, (list, tuple)):
            return (t, str(v))
        out = []
        for item in v:
            if isinstance(item, (int, float)) and not isinstance(item, bool):
                d = norm_number(item)
                out.append(float(round(d, 6)) if d is not None else str(item))
            else:
                out.append(norm_text(str(item)))
        return (t, tuple(out))
    if t == AnswerType.TABLE.value:
        rows = _table_rows(v) or []
        cols = _table_columns(v) or []
        out_rows = []
        for row in rows:
            r = []
            for cell in row:
                if isinstance(cell, (int, float)) and not isinstance(cell, bool):
                    d = norm_number(cell)
                    r.append(float(round(d, 6)) if d is not None else str(cell))
                else:
                    r.append(norm_text(str(cell)))
            out_rows.append(tuple(r))
        return (t, tuple(norm_text(str(c)) for c in cols), tuple(out_rows))
    if t == AnswerType.UNANSWERABLE.value:
        return (t,)
    return (t, str(v))


def score(pred: Answer, ref: dict[str, Any]) -> int:
    """Điểm PA: đúng +1, sai −1, abstain 0."""
    if pred is None or pred.type == AnswerType.ABSTAIN.value:
        return 0
    return 1 if is_correct(pred, ref) else -1


def safe_decimal(x: Any) -> Decimal | None:
    try:
        return _to_decimal(x)
    except (InvalidOperation, ValueError):
        return None
