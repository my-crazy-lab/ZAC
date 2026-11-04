"""Tập giá trị hợp lệ của các knob (M3).

Knob là **tham số có kiểu** của luật nghiệp vụ. Rulebook đổi theo split nên
luật phải là tham số, không hard-code trong code.
"""

from __future__ import annotations

from typing import Any

KNOB_DOMAINS: dict[str, list[Any]] = {
    "revenue_after_line_discount": [True, False],
    "revenue_deduct_order_voucher": [True, False],
    "revenue_include_vat": [True, False],
    "revenue_include_shipping": [True, False],
    "exclude_cancelled": [True, False],
    "returned_policy": ["exclude_order", "exclude_line", "ignore"],
    "bestseller_metric": ["qty", "revenue", "orders"],
    "week_start": [0, 6],
    "this_month": ["month_to_date", "full_month"],
    "this_week": ["week_to_date", "full_week"],
    "last_n_includes_today": [True, False],
    "cost_method": ["line_cost", "wavg_by_lot", "wavg_up_to_sale_date"],
    "tet_start": [("lunar", 12, 23, -1), ("lunar", 12, 22, -1)],
    "tet_end": [("lunar", 1, 10, 0), ("lunar", 1, 9, 0)],
    "shift_morning": [(6, 13), (7, 13), (6, 14)],
    "shift_afternoon": [(14, 21), (14, 22), (15, 22)],
    "rounding_money": ["half_up", "half_even"],
}

BOOL_KNOBS = {k for k, v in KNOB_DOMAINS.items() if v == [True, False]}


def is_valid(knob: str, value: Any) -> bool:
    """Giá trị có nằm trong tập hợp lệ không."""
    allowed = KNOB_DOMAINS.get(knob)
    if allowed is None:
        return False
    return any(value == a for a in allowed)
