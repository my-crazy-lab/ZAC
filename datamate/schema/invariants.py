"""Bất biến dữ liệu: phát hiện cách hiểu cột của từng shop (M4.E).

Mỗi hàm trả ``(passed, penalty, info)``.
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

log = logging.getLogger(__name__)


def _num(s: pd.Series | None) -> pd.Series:
    if s is None:
        return pd.Series(dtype="float64")
    return pd.to_numeric(s, errors="coerce")


def inv_line_math(c_lines: pd.DataFrame) -> tuple[bool, float, dict[str, Any]]:
    """``qty × unit_price − line_discount ≈ line_amount``."""
    if c_lines is None or c_lines.empty:
        return True, 0.0, {"note": "không có dòng bán"}
    qty = _num(c_lines.get("qty"))
    price = _num(c_lines.get("unit_price"))
    amt = _num(c_lines.get("line_amount"))
    disc = _num(c_lines.get("line_discount"))
    valid = qty.notna() & price.notna() & amt.notna() & (amt.abs() > 0)
    if not valid.any():
        return False, 0.1, {"note": "thiếu cột tính toán"}
    calc = qty[valid] * price[valid] - (disc[valid] if len(disc) == len(qty) else 0.0)
    ref = amt[valid]
    rel = ((calc - ref).abs() / ref.abs()).replace([float("inf"), float("-inf")], pd.NA).dropna()
    ratio = float((rel <= 0.01).mean()) if len(rel) else 0.0
    info = {"ratio_ok": round(ratio, 4), "n": int(valid.sum())}
    if ratio >= 0.95:
        return True, 0.0, info
    # biến thể: line_amount = qty*price*(1+vat) hoặc chưa trừ giảm giá
    calc_nodisc = qty[valid] * price[valid]
    rel2 = ((calc_nodisc - ref).abs() / ref.abs()).replace([float("inf"), float("-inf")], pd.NA).dropna()
    ratio2 = float((rel2 <= 0.01).mean()) if len(rel2) else 0.0
    info["ratio_nodisc"] = round(ratio2, 4)
    if ratio2 >= 0.95:
        info["discount_already_applied"] = False
        return True, 0.05, info
    return False, 0.1, info


def inv_order_total(c_lines: pd.DataFrame, c_orders: pd.DataFrame
                    ) -> tuple[bool, float, dict[str, Any]]:
    """So ``order_total`` với tổng thành tiền các dòng."""
    if c_orders is None or c_orders.empty or c_lines is None or c_lines.empty:
        return True, 0.0, {"note": "thiếu dữ liệu"}
    total = _num(c_orders.get("order_total"))
    if "order_total" not in c_orders.columns or total.notna().sum() == 0:
        return True, 0.0, {"note": "không có cột tổng tiền đơn"}
    agg = _num(c_lines.get("line_amount")).groupby(c_lines["order_id"]).sum()
    joined = pd.DataFrame({"order_total": total}).join(agg, how="inner")
    joined = joined.dropna()
    if joined.empty:
        return True, 0.0, {"note": "không khớp đơn nào"}
    diff = (joined["order_total"] - joined["line_amount"]).abs()
    scale = joined["order_total"].abs().replace(0, pd.NA)
    rel = (diff / scale).fillna(0.0)
    ratio = float((rel <= 0.02).mean())
    info = {"ratio_ok": round(ratio, 4), "n": int(len(joined))}
    if ratio >= 0.9:
        return True, 0.0, info
    return False, 0.05, info


def inv_qty_base(c_lines: pd.DataFrame, c_units: pd.DataFrame
                 ) -> tuple[bool, float, dict[str, Any]]:
    """``qty_base ≈ qty × unit_factor``."""
    if c_lines is None or c_lines.empty:
        return True, 0.0, {"note": "không có dòng bán"}
    qty = _num(c_lines.get("qty"))
    qb = _num(c_lines.get("qty_base"))
    if qb.notna().sum() == 0:
        return False, 0.1, {"note": "không có cột qty_base"}
    if c_units is None or c_units.empty:
        return True, 0.0, {"note": "không có bảng quy đổi"}
    units = c_units.copy()
    units["_key"] = units["product_code"].astype(str) + "|" + units["unit_name"].astype(str)
    lines = pd.DataFrame({"code": c_lines.get("product_code"), "unit": c_lines.get("unit_name"),
                          "qty": qty, "qb": qb}).dropna(subset=["qb"])
    lines["_key"] = lines["code"].astype(str) + "|" + lines["unit"].astype(str)
    fac = units.set_index("_key")["unit_factor"].to_dict()
    lines["factor"] = lines["_key"].map(fac)
    ok = lines.dropna(subset=["factor", "qty"])
    if ok.empty:
        return False, 0.05, {"note": "không khớp đơn vị"}
    exp = ok["qty"] * ok["factor"]
    rel = ((ok["qb"] - exp).abs() / exp.abs().replace(0, pd.NA)).fillna(0.0)
    ratio = float((rel <= 0.02).mean())
    info = {"ratio_ok": round(ratio, 4), "n": int(len(ok)),
            "qty_base_is_converted": ratio >= 0.95}
    if ratio >= 0.95:
        return True, 0.0, info
    return False, 0.05, info


def inv_cost(c_lines: pd.DataFrame) -> tuple[bool, float, dict[str, Any]]:
    """Giá vốn trên dòng có hợp lý không (≤ thành tiền ở ≥90% dòng)."""
    if c_lines is None or c_lines.empty:
        return True, 0.0, {"note": "không có dòng bán"}
    cost = _num(c_lines.get("line_cost_total"))
    amt = _num(c_lines.get("line_amount"))
    if cost.notna().sum() == 0:
        return False, 0.1, {"note": "không có cột giá vốn"}
    valid = cost.notna() & amt.notna() & (amt.abs() > 0)
    if not valid.any():
        return False, 0.05, {"note": "không có dòng nào có cả giá vốn và thành tiền"}
    ratio = float((cost[valid] <= amt[valid] * 1.05).mean())
    info = {"ratio_ok": round(ratio, 4), "n": int(valid.sum()),
            "cost_is_unit": ratio < 0.9}
    if ratio >= 0.9:
        return True, 0.0, info
    return False, 0.05, info


def inv_debt(c_orders: pd.DataFrame, c_payments: pd.DataFrame
             ) -> tuple[bool, float, dict[str, Any]]:
    """``order_debt_total`` có khớp cột "còn nợ" không."""
    if c_orders is None or c_orders.empty:
        return True, 0.0, {"note": "không có đơn"}
    if "order_debt_total" not in c_orders.columns:
        return True, 0.0, {"note": "không có cột công nợ"}
    debt = _num(c_orders.get("order_debt_total"))
    if debt.notna().sum() == 0:
        return True, 0.0, {"note": "cột công nợ rỗng"}
    ratio = float((debt >= -1e-6).mean())
    info = {"ratio_nonneg": round(ratio, 4)}
    if ratio >= 0.95:
        return True, 0.0, info
    return False, 0.05, info


def inv_dates(c_orders: pd.DataFrame) -> tuple[bool, float, dict[str, Any]]:
    """Tỉ lệ ngày parse được và khoảng ngày dữ liệu."""
    if c_orders is None or c_orders.empty:
        return False, 0.2, {"note": "không có đơn"}
    d = c_orders.get("order_date")
    if d is None:
        return False, 0.2, {"note": "không có cột ngày"}
    nonnull = d.dropna()
    if nonnull.empty:
        return False, 0.2, {"note": "cột ngày rỗng"}
    ratio = float(len(nonnull) / max(1, len(c_orders)))
    info = {"parse_ratio": round(ratio, 4), "n": int(len(nonnull))}
    if ratio < 0.9:
        return False, 0.1, info
    return True, 0.0, info


def inv_join(c_lines: pd.DataFrame, c_orders: pd.DataFrame) -> tuple[bool, float, dict[str, Any]]:
    """Dòng mồ côi (không khớp đơn)."""
    if c_lines is None or c_lines.empty or c_orders is None or c_orders.empty:
        return True, 0.0, {"note": "thiếu dữ liệu"}
    orders = set(c_orders["order_id"].dropna().tolist())
    if not orders:
        return True, 0.0, {"note": "không có mã đơn"}
    orphan = float((~c_lines["order_id"].isin(orders)).mean())
    info = {"orphan_ratio": round(orphan, 4)}
    if orphan <= 0.02:
        return True, 0.0, info
    return False, 0.05, info


def compute_all(c_lines: pd.DataFrame, c_orders: pd.DataFrame, c_units: pd.DataFrame,
                c_payments: pd.DataFrame) -> tuple[dict[str, Any], dict[str, float]]:
    """Chạy mọi bất biến; trả (info theo bất biến, penalty theo bất biến)."""
    results: dict[str, Any] = {}
    penalties: dict[str, float] = {}
    checks = [
        ("line_math", inv_line_math(c_lines)),
        ("order_total", inv_order_total(c_lines, c_orders)),
        ("qty_base", inv_qty_base(c_lines, c_units)),
        ("cost", inv_cost(c_lines)),
        ("debt", inv_debt(c_orders, c_payments)),
        ("dates", inv_dates(c_orders)),
        ("join", inv_join(c_lines, c_orders)),
    ]
    for name, (passed, penalty, info) in checks:
        results[name] = {"passed": bool(passed), "info": info}
        if penalty:
            penalties[name] = penalty
    return results, penalties
