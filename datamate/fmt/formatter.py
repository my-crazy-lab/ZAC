"""Formatter: kết quả truy vấn → đáp án đúng định dạng submission (M7)."""

from __future__ import annotations

import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from dtypes import Answer, AnswerType, BizContext, CompiledPlan, ExecResult, Knobs, Spec, TimeWindow

log = logging.getLogger(__name__)


def _dec(x: Any) -> Decimal | None:
    if x is None or isinstance(x, bool):
        return None
    try:
        return Decimal(str(x))
    except Exception:  # noqa: BLE001
        return None


def _round(value: Decimal, places: str) -> Decimal:
    return value.quantize(Decimal(places), rounding=ROUND_HALF_UP)


def _money(value: Decimal) -> int:
    return int(_round(value, "1"))


def _is_month_question(spec: Spec | None, windows: list[TimeWindow] | None) -> bool:
    if spec is not None and spec.subject == "month":
        return True
    if not windows:
        return False
    for w in windows:
        if w.start.day == 1 and w.end.day == 28 and w.start.month == w.end.month:
            return True
    return False


def to_submission(plan: CompiledPlan, result: ExecResult, spec: Spec | None,
                  out_type: str, ctx: BizContext | None = None,
                  knobs: Knobs | None = None,
                  windows: list[TimeWindow] | None = None) -> Answer:
    """Biến kết quả truy vấn thành ``Answer`` đúng format (rulebook §9)."""
    if result is None:
        return Answer(type=AnswerType.ABSTAIN.value)
    if result.error:
        return Answer(type=AnswerType.ABSTAIN.value)

    rows = list(result.rows or [])
    cols = list(result.columns or [])
    is_money = bool((plan.meta or {}).get("is_money"))
    limit = spec.limit if spec is not None else None

    # --- hậu xử lý Python (4.6)
    post = plan.post
    if post in ("series_increasing", "series_decreasing"):
        vals = [(_dec(r[-1]) if len(r) >= 1 else None) for r in rows]
        vals = [v for v in vals if v is not None]
        if len(vals) < 2:
            return Answer(type=AnswerType.ABSTAIN.value)
        increasing = all(vals[i] < vals[i + 1] for i in range(len(vals) - 1))
        decreasing = all(vals[i] > vals[i + 1] for i in range(len(vals) - 1))
        ok = increasing if post == "series_increasing" else decreasing
        return Answer(type=AnswerType.BOOLEAN.value, value=bool(ok))
    if post in ("argmax_label", "argmin_label"):
        if not rows:
            return Answer(type=AnswerType.ABSTAIN.value)
        best_idx = 0
        best_val = None
        for i, r in enumerate(rows):
            val = _dec(r[-1]) if len(r) >= 1 else None
            if val is None:
                continue
            if best_val is None or (post == "argmax_label" and val > best_val) or \
                    (post == "argmin_label" and val < best_val):
                best_val, best_idx = val, i
        label = rows[best_idx][0]
        if out_type == "date" and isinstance(label, str) and len(label) == 7:
            return Answer(type=AnswerType.DATE.value, value=label)
        return Answer(type=AnswerType.STRING.value, value=str(label))
    if post == "exists":
        return Answer(type=AnswerType.BOOLEAN.value, value=bool(rows))
    if post == "gt_threshold":
        if not rows:
            return Answer(type=AnswerType.ABSTAIN.value)
        val = _dec(rows[0][0])
        thr = _dec((spec.params or {}).get("threshold", 0)) if spec else None
        if val is None or thr is None:
            return Answer(type=AnswerType.ABSTAIN.value)
        return Answer(type=AnswerType.BOOLEAN.value, value=bool(val > thr))
    if post == "main_gt_base":
        if not rows:
            return Answer(type=AnswerType.ABSTAIN.value)
        val = _dec(rows[0][0])
        if val is None:
            return Answer(type=AnswerType.ABSTAIN.value)
        return Answer(type=AnswerType.BOOLEAN.value, value=bool(val > 0))

    # --- theo từng type
    if out_type == AnswerType.NUMBER.value:
        if not rows:
            return _empty_answer(spec, out_type)
        val = _dec(rows[0][0])
        if val is None:
            return Answer(type=AnswerType.ABSTAIN.value)
        if is_money:
            return Answer(type=AnswerType.NUMBER.value, value=_money(val))
        return Answer(type=AnswerType.NUMBER.value,
                      value=float(_round(val, "0.01")))

    if out_type == AnswerType.PERCENT.value:
        if not rows:
            return _empty_answer(spec, out_type)
        val = _dec(rows[0][0])
        if val is None:
            return Answer(type=AnswerType.ABSTAIN.value)
        return Answer(type=AnswerType.PERCENT.value, value=float(_round(val, "0.01")))

    if out_type == AnswerType.BOOLEAN.value:
        if not rows:
            return Answer(type=AnswerType.ABSTAIN.value)
        val = rows[0][0]
        return Answer(type=AnswerType.BOOLEAN.value, value=bool(val))

    if out_type == AnswerType.DATE.value:
        if not rows:
            return Answer(type=AnswerType.ABSTAIN.value)
        label = rows[0][0]
        text = str(label)[:10]
        if _is_month_question(spec, windows):
            return Answer(type=AnswerType.DATE.value, value=text[:7])
        return Answer(type=AnswerType.DATE.value, value=text)

    if out_type == AnswerType.STRING.value:
        if not rows:
            return Answer(type=AnswerType.ABSTAIN.value)
        return Answer(type=AnswerType.STRING.value, value=str(rows[0][0]))

    if out_type == AnswerType.LIST.value:
        if not rows:
            return Answer(type=AnswerType.ABSTAIN.value)
        # phát hiện hoà ở biên (4.8)
        if limit is not None and len(rows) > limit:
            if _tie_at(rows, limit):
                return Answer(type=AnswerType.ABSTAIN.value)
        picked = rows[:limit] if limit else rows
        values = [_list_item(r, cols) for r in picked]
        return Answer(type=AnswerType.LIST.value, value=values)

    if out_type == AnswerType.TABLE.value:
        if not rows:
            return Answer(type=AnswerType.ABSTAIN.value)
        if limit is not None and len(rows) > limit:
            if _tie_at(rows, limit):
                return Answer(type=AnswerType.ABSTAIN.value)
        picked = rows[:limit] if limit else rows
        table_rows = []
        for r in picked:
            table_rows.append([_table_cell(c) for c in r])
        return Answer(type=AnswerType.TABLE.value,
                      value={"columns": _table_columns(cols), "rows": table_rows})

    return Answer(type=AnswerType.ABSTAIN.value)


def _empty_answer(spec: Spec | None, out_type: str) -> Answer:
    """Rỗng: tổng ⇒ 0; xếp hạng/tra cứu ⇒ abstain."""
    if spec is not None and spec.intent == "aggregate_total":
        if out_type == AnswerType.PERCENT.value:
            return Answer(type=AnswerType.PERCENT.value, value=0.0)
        return Answer(type=AnswerType.NUMBER.value, value=0)
    return Answer(type=AnswerType.ABSTAIN.value)


def _tie_at(rows: list[tuple], limit: int) -> bool:
    """Hai hàng kề nhau bằng nhau ở biên ⇒ hoà (4.8)."""
    if limit <= 0 or len(rows) <= limit:
        return False
    a = _dec(rows[limit - 1][-1]) if len(rows[limit - 1]) >= 1 else None
    b = _dec(rows[limit][-1]) if len(rows[limit]) >= 1 else None
    if a is None or b is None:
        return False
    return a == b


def _list_item(row: tuple, cols: list[str]) -> Any:
    """Phần tử của list: số nếu là số, chuỗi nếu là tên."""
    if not row:
        return None
    val = row[0]
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        return float(_round(Decimal(str(val)), "0.01"))
    if hasattr(val, "isoformat"):
        return val.isoformat()
    return str(val)


def _table_cell(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return float(_round(Decimal(str(value)), "0.01"))
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _table_columns(cols: list[str]) -> list[str]:
    from text.normalize import nd

    out = []
    for c in cols:
        key = nd(str(c)).replace(" ", "_")
        out.append(key)
    return out
