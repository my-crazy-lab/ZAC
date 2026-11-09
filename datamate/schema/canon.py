"""Canonicalize bảng thô → bảng ``c_*`` (M4.D).

Hấp thụ khác biệt giữa các archetype: sau bước này, mọi business đều có cùng
tập bảng canonical với tên cột cố định (EXECUTION-MVP.md §4.1).
"""

from __future__ import annotations

import logging
import re
from datetime import date
from typing import Any

import pandas as pd

from ingest.clean import parse_date_series, parse_datetime_series, parse_number_series
from text.normalize import nd

log = logging.getLogger(__name__)

CANCELLED_WORDS = ("huy", "cancel", "void", "that bai", "failed")
# "Đã hoàn thành" KHÔNG phải trả hàng ⇒ kiểm tra "hoàn hàng" trước "hoàn"
RETURNED_WORDS = ("hoan hang", "doi tra", "tra hang", "tra lai", "hoan tra",
                  "return", "refund", "returned", "tra ve", "bi tra")
SERVICE_RE = re.compile(
    r"phi phuc vu|phi dich vu|phi ship|shipping|service|phu phi|voucher|dung diem",
    re.IGNORECASE,
)
WALKIN_RE = re.compile(r"khach le|vang lai|khach vang lai|khong ten", re.IGNORECASE)
# tên khách lẻ (rulebook §6): "Khách lẻ", "lẻ", "kl", "Khách vãng lai"
WALKIN_NAMES = {"le", "khach le", "kl", "vang lai", "khach vang lai", "khong ten",
                "guest", "khach vang lai", "khach le si", "an danh", "khac"}

CANON_LINES_COLS = ["order_id", "line_no", "product_code", "product_name", "qty",
                    "qty_base", "unit_name", "unit_price", "line_discount",
                    "line_amount", "line_cost_total", "return_flag", "return_qty",
                    "is_service", "size"]
CANON_ORDERS_COLS = ["order_id", "order_date", "order_ts", "customer_key",
                     "customer_name", "status_raw", "channel", "pay_method",
                     "employee", "order_total", "shipping_fee", "vat_amount",
                     "vat_rate", "order_voucher", "order_debt_total", "order_paid"]
# Cột dẫn xuất luôn phải tồn tại, kể cả khi bảng rỗng — view v_orders_all
# chọn đủ các cột này nên thiếu một cột là toàn bộ v_* phía sau biến mất.
ORDER_BOOL_COLS = ["is_cancelled", "has_return", "is_returned",
                   "is_cod", "is_marketplace", "is_walkin"]
CANON_PRODUCTS_COLS = ["product_code", "product_name", "category", "unit", "unit_cost"]
CANON_CUSTOMERS_COLS = ["customer_key", "customer_name", "phone", "customer_group",
                        "customer_since", "is_walkin"]
CANON_PAYMENTS_COLS = ["order_id", "customer_key", "pay_date", "pay_amount", "pay_method"]
CANON_LOTS_COLS = ["lot_id", "product_code", "lot_date", "lot_qty", "lot_cost", "expiry_date"]
CANON_INVENTORY_COLS = ["product_code", "inv_date", "inv_qty", "lot_id"]
CANON_IMPORTS_COLS = ["import_id", "import_date", "product_code", "qty", "qty_base",
                      "unit_name", "amount", "is_cancelled", "supplier"]
CANON_UNITS_COLS = ["product_code", "unit_name", "unit_factor", "base_unit"]
CANON_PRICE_COLS = ["product_code", "ph_date", "ph_old", "ph_new"]
CANON_RETURNS_COLS = ["order_id", "product_code", "return_date", "return_qty"]
CANON_DELIVERIES_COLS = ["order_id", "del_date", "employee", "del_round"]


def _tables_by_name(tables: list[Any]) -> dict[str, Any]:
    return {str(t.name): t for t in tables}


def _pick(df: pd.DataFrame, cols: dict[str, str], role: str) -> pd.Series | None:
    col = cols.get(role)
    if col is None or col not in df.columns:
        return None
    return df[col]


def _num(df: pd.DataFrame, cols: dict[str, str], role: str) -> pd.Series | None:
    s = _pick(df, cols, role)
    if s is None:
        return None
    return parse_number_series(s)


_YEARLESS_RE = re.compile(r"^\s*(\d{1,2})\s*[/\-.]\s*(\d{1,2})\s*$")
_SHEET_YEAR_RE = re.compile(r"(\d{4})")


def _fill_yearless(out: pd.Series, raw: pd.Series, sheets: pd.Series) -> pd.Series:
    """Điền ngày thiếu năm bằng năm ghi trong tên sheet (rulebook §8)."""
    values = out.tolist()
    raws = raw.tolist()
    sheet_vals = sheets.tolist()
    for i, current in enumerate(values):
        if current is not None and current == current:
            continue
        m = _YEARLESS_RE.match(str(raws[i] or ""))
        if m is None:
            continue
        my = _SHEET_YEAR_RE.search(str(sheet_vals[i] or ""))
        if my is None:
            continue
        try:
            values[i] = date(int(my.group(1)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            continue
    return pd.Series(values, index=out.index, dtype="object")


def _date(df: pd.DataFrame, cols: dict[str, str], role: str) -> pd.Series | None:
    s = _pick(df, cols, role)
    if s is None:
        return None
    out = parse_date_series(s)
    if "__sheet" in df.columns:
        out = _fill_yearless(out, s, df["__sheet"])
    # chuẩn hoá Timestamp → date (tránh so sánh date/Timestamp)
    return out.map(lambda v: v.date() if isinstance(v, pd.Timestamp) else v)


def _datetime(df: pd.DataFrame, cols: dict[str, str], role: str) -> pd.Series | None:
    s = _pick(df, cols, role)
    if s is None:
        return None
    return parse_datetime_series(s)


def _text(df: pd.DataFrame, cols: dict[str, str], role: str) -> pd.Series | None:
    s = _pick(df, cols, role)
    if s is None:
        return None
    return s.astype("object").where(s.notna(), None).map(
        lambda v: v.strip() if isinstance(v, str) else v
    )


def _empty(n: int) -> pd.Series:
    return pd.Series([None] * n, dtype="object")


def canonicalize(tables: list[Any], mapping: dict[str, Any], archetype: str,
                 readme: str = "") -> dict[str, pd.DataFrame]:
    """Trả dict các bảng canonical ``c_*``."""
    by_name = _tables_by_name(tables)
    entities = mapping.get("entities", {})
    out: dict[str, pd.DataFrame] = {}

    lines_info = entities.get("lines")
    orders_info = entities.get("orders")

    c_units = _build_units(by_name, entities.get("units"), readme)
    c_lines = _build_lines(by_name, lines_info, orders_info, c_units)
    c_orders = _build_orders(by_name, orders_info, c_lines, lines_info)
    out["c_lines"] = c_lines
    out["c_orders"] = c_orders

    out["c_products"] = _build_products(by_name, entities.get("products"), c_lines, c_units)
    out["c_customers"] = _build_customers(by_name, entities.get("customers"), c_orders)
    out["c_payments"] = _build_payments(by_name, entities.get("payments"), c_orders)
    out["c_units"] = c_units
    out["c_imports"] = _build_imports(by_name, entities.get("imports"))
    out["c_inventory"] = _build_inventory(by_name, entities.get("inventory"))
    out["c_lots"] = _build_lots(by_name, entities.get("lots"))
    out["c_price_history"] = _build_price_history(by_name, entities.get("price_history"))
    out["c_deliveries"] = _build_deliveries(by_name, entities.get("deliveries"))
    return out


# ----------------------------------------------------------------- c_lines

def _build_lines(by_name: dict[str, Any], lines_info: dict[str, Any] | None,
                 orders_info: dict[str, Any] | None,
                 c_units: pd.DataFrame | None = None) -> pd.DataFrame:
    if not lines_info:
        return pd.DataFrame(columns=CANON_LINES_COLS)
    cols = dict(lines_info["cols"])
    order_cols = lines_info.get("order_cols") or {}
    # thuộc tính đơn nằm trong chính bảng dòng bán
    for role in ("order_date", "order_ts", "status_raw", "customer_name", "customer_key",
                 "channel", "pay_method", "employee", "order_total", "order_debt_total",
                 "order_paid"):
        if role in order_cols and role not in cols:
            cols[role] = order_cols[role]
    frames: list[pd.DataFrame] = []
    for tname in lines_info.get("tables", [lines_info["table"]]):
        t = by_name.get(tname)
        if t is None:
            continue
        df = t.df
        n = len(df)
        part = pd.DataFrame(index=range(n))
        oid = _text(df, cols, "order_id")
        part["order_id"] = oid.reset_index(drop=True) if oid is not None else _empty(n)
        part["line_no"] = _num(df, cols, "line_no").reset_index(drop=True) \
            if _num(df, cols, "line_no") is not None else _empty(n)
        pname = _text(df, cols, "product_name")
        part["product_name"] = pname.reset_index(drop=True) if pname is not None else _empty(n)
        pcode = _text(df, cols, "product_code")
        part["product_code"] = pcode.reset_index(drop=True) if pcode is not None else _empty(n)
        qty = _num(df, cols, "qty")
        part["qty"] = qty.reset_index(drop=True) if qty is not None else _empty(n)
        qb = _num(df, cols, "qty_base")
        part["qty_base"] = qb.reset_index(drop=True) if qb is not None else _empty(n)
        unit = _text(df, cols, "unit_name")
        part["unit_name"] = unit.reset_index(drop=True) if unit is not None else _empty(n)
        up = _num(df, cols, "unit_price")
        part["unit_price"] = up.reset_index(drop=True) if up is not None else _empty(n)
        disc = _num(df, cols, "line_discount")
        part["line_discount"] = disc.reset_index(drop=True) if disc is not None else _empty(n)
        amt = _num(df, cols, "line_amount")
        part["line_amount"] = amt.reset_index(drop=True) if amt is not None else _empty(n)
        cost = _num(df, cols, "line_cost_total")
        part["line_cost_total"] = cost.reset_index(drop=True) if cost is not None else _empty(n)
        uc = _num(df, cols, "unit_cost")
        part["unit_cost"] = uc.reset_index(drop=True) if uc is not None else _empty(n)
        rq = _num(df, cols, "return_qty")
        part["return_qty"] = rq.reset_index(drop=True) if rq is not None else _empty(n)
        size = _text(df, cols, "size")
        part["size"] = size.reset_index(drop=True) if size is not None else _empty(n)
        for role in ("order_date", "order_ts"):
            if role in cols:
                val = _date(df, cols, role)
                part[role] = val.reset_index(drop=True) if val is not None else _empty(n)
        frames.append(part)

    if not frames:
        return pd.DataFrame(columns=CANON_LINES_COLS)
    lines = pd.concat(frames, ignore_index=True)

    # --- bỏ dòng không có mã đơn (dòng tổng, dòng rác) — chỉ khi bảng có cột mã đơn
    if "order_id" in lines.columns and lines["order_id"].notna().any():
        lines = lines[lines["order_id"].notna()].reset_index(drop=True)

    # --- order_id: nếu thiếu ⇒ sinh mã ổn định 'R' + số thứ tự dòng
    if lines["order_id"].isna().all():
        lines["order_id"] = [f"R{i + 1}" for i in range(len(lines))]
    else:
        lines["order_id"] = lines["order_id"].map(
            lambda v: v if isinstance(v, str) and v.strip() else None)
        # điền cho dòng thiếu bằng mã của dòng trước (nhóm dòng của cùng đơn)
        lines["order_id"] = lines["order_id"].ffill()

    # --- line_no: số thứ tự dòng trong đơn
    if lines["line_no"].isna().all():
        lines["line_no"] = lines.groupby("order_id").cumcount() + 1

    # --- product_code: thiếu ⇒ dùng tên bỏ dấu
    lines["product_code"] = lines.apply(
        lambda r: r["product_code"] if isinstance(r["product_code"], str) and r["product_code"].strip()
        else (nd(str(r["product_name"])) if r["product_name"] else None),
        axis=1,
    )

    # --- is_service
    lines["is_service"] = lines["product_name"].map(
        lambda v: bool(isinstance(v, str) and SERVICE_RE.search(v)))

    # --- return_flag: số lượng âm hoặc cột cờ
    neg = lines["qty"].map(lambda v: bool(isinstance(v, (int, float)) and v < 0))
    lines["return_flag"] = neg

    # --- qty_base: nếu thiếu ⇒ qty × hệ số quy đổi (theo mã hàng + đơn vị)
    for col in ("qty", "qty_base", "unit_price", "line_amount", "line_discount",
                "line_cost_total", "unit_cost", "return_qty"):
        if col in lines.columns:
            lines[col] = pd.to_numeric(lines[col], errors="coerce")
    if c_units is not None and not c_units.empty:
        if lines["qty_base"].isna().all() or lines["qty_base"].notna().sum() == 0:
            units = c_units.copy()
            units["_key"] = (units["product_code"].astype(str) + "|" +
                             units["unit_name"].astype(str))
            fac = units.drop_duplicates(subset=["_key"]).set_index("_key")["unit_factor"]
            lines["_key"] = (lines["product_code"].astype(str) + "|" +
                             lines["unit_name"].astype(str))
            factor = pd.to_numeric(lines["_key"].map(fac), errors="coerce")
            qty_num = pd.to_numeric(lines["qty"], errors="coerce")
            lines["qty_base"] = (qty_num * factor).where(factor.notna())
            lines["_key"] = None
    # --- line_cost_total: nếu chỉ có giá vốn một đơn vị thì nhân với qty_base
    if "unit_cost" in lines.columns:
        unit_cost = pd.to_numeric(lines["unit_cost"], errors="coerce")
        qty_cost = pd.to_numeric(lines["qty_base"], errors="coerce")
        qty_cost = qty_cost.where(qty_cost.notna(), pd.to_numeric(lines["qty"], errors="coerce"))
        computed = unit_cost * qty_cost
        current = pd.to_numeric(lines["line_cost_total"], errors="coerce")
        lines["line_cost_total"] = current.where(current.notna(), computed)
    extra = [c for c in ("order_date", "order_ts") if c in lines.columns]
    for c in CANON_LINES_COLS:
        if c not in lines.columns:
            lines[c] = None
    return lines[CANON_LINES_COLS + extra].reset_index(drop=True)


# ---------------------------------------------------------------- c_orders

def _finalize_orders(orders: pd.DataFrame) -> pd.DataFrame:
    """Ép c_orders về schema cố định (kể cả khi rỗng) và bỏ cột trùng."""
    if orders.columns.duplicated().any():
        orders = orders.loc[:, ~orders.columns.duplicated()]
    for col in CANON_ORDERS_COLS:
        if col not in orders.columns:
            orders[col] = None
    for col in ORDER_BOOL_COLS:
        if col not in orders.columns:
            orders[col] = False
        else:
            orders[col] = orders[col].fillna(False).astype(bool)
    return orders[CANON_ORDERS_COLS + ORDER_BOOL_COLS].reset_index(drop=True)


def _build_orders(by_name: dict[str, Any], orders_info: dict[str, Any] | None,
                  c_lines: pd.DataFrame, lines_info: dict[str, Any] | None
                  ) -> pd.DataFrame:
    if not orders_info:
        # suy c_orders từ c_lines (bảng phẳng: không có bảng đơn riêng)
        if c_lines.empty:
            return _finalize_orders(pd.DataFrame())
        have_date = "order_date" in c_lines.columns and c_lines["order_date"].notna().any()
        if not have_date:
            return _finalize_orders(pd.DataFrame())
        agg = (c_lines.sort_values("order_date")
               .drop_duplicates(subset=["order_id"], keep="first"))
        orders = pd.DataFrame(index=range(len(agg)))
        orders["order_id"] = agg["order_id"].values
        orders["order_date"] = agg["order_date"].values
        orders["order_ts"] = agg["order_ts"].values if "order_ts" in agg.columns else None
        for col in ("customer_key", "customer_name", "status_raw", "channel",
                    "pay_method", "employee", "order_total", "order_debt_total",
                    "order_paid"):
            orders[col] = agg[col].values if col in agg.columns else None
        orders["is_cancelled"] = False
        orders["has_return"] = False
        orders["is_returned"] = False
        orders["is_cod"] = False
        orders["is_marketplace"] = False
        orders["is_walkin"] = orders["customer_name"].map(_is_walkin)
        for col in CANON_ORDERS_COLS:
            if col not in orders.columns:
                orders[col] = None
        return _finalize_orders(orders)

    cols = orders_info["cols"]
    frames: list[pd.DataFrame] = []
    for tname in orders_info.get("tables", [orders_info["table"]]):
        t = by_name.get(tname)
        if t is None:
            continue
        df = t.df
        n = len(df)
        part = pd.DataFrame(index=range(n))
        oid = _text(df, cols, "order_id")
        part["order_id"] = oid.reset_index(drop=True) if oid is not None else _empty(n)
        od = _date(df, cols, "order_date")
        part["order_date"] = od.reset_index(drop=True) if od is not None else _empty(n)
        ots = _datetime(df, cols, "order_ts")
        part["order_ts"] = ots.reset_index(drop=True) if ots is not None else _empty(n)
        for role in ("customer_key", "customer_name", "status_raw", "channel",
                     "pay_method", "employee"):
            s = _text(df, cols, role)
            part[role] = s.reset_index(drop=True) if s is not None else _empty(n)
        for role in ("order_total", "shipping_fee", "vat_amount", "vat_rate",
                     "order_voucher", "order_debt_total", "order_paid"):
            s = _num(df, cols, role)
            part[role] = s.reset_index(drop=True) if s is not None else _empty(n)
        frames.append(part)
    if not frames:
        return _finalize_orders(pd.DataFrame())
    orders = pd.concat(frames, ignore_index=True)

    # --- order_date: thiếu ⇒ lấy từ order_ts
    if orders["order_date"].isna().all() and "order_ts" in orders.columns:
        orders["order_date"] = orders["order_ts"].map(
            lambda v: v.date() if hasattr(v, "date") else v)
    if orders["order_ts"].isna().all() and "order_date" in orders.columns:
        orders["order_ts"] = orders["order_date"]

    # --- 1 dòng cho mỗi đơn
    orders = orders.drop_duplicates(subset=["order_id"], keep="first").reset_index(drop=True)

    # --- nối thuộc tính đơn còn thiếu từ bảng dòng bán (bảng phẳng)
    if not c_lines.empty and "order_id" in c_lines.columns:
        if "order_id" in lines_info.get("order_cols", {}) or lines_info:
            for role in ("order_date", "status_raw", "customer_name", "customer_key",
                         "channel", "pay_method", "employee"):
                if orders[role].isna().all() and role in lines_info.get("order_cols", {}):
                    src = by_name.get(lines_info["table"])
                    if src is not None:
                        col = lines_info["order_cols"][role]
                        if col in src.df.columns:
                            vals = src.df[col]
                            sub = pd.DataFrame({"order_id": lines_info["cols"].get("order_id", ""),
                                                role: vals})
                            sub = sub.drop_duplicates(subset=["order_id"], keep="first")
                            orders = orders.merge(sub, on="order_id", how="left", suffixes=("", "_l"))
                            if f"{role}_l" in orders.columns:
                                orders[role] = orders[role].fillna(orders[f"{role}_l"])
                                orders.drop(columns=[f"{role}_l"], inplace=True)

    # --- trạng thái
    status_nd = orders["status_raw"].map(lambda v: nd(str(v)) if isinstance(v, str) else "")
    orders["is_cancelled"] = status_nd.map(lambda s: any(w in s for w in CANCELLED_WORDS))
    returned_by_status = status_nd.map(
        lambda s: (not any(w in s for w in CANCELLED_WORDS))
        and any(w in s for w in RETURNED_WORDS))
    if not c_lines.empty:
        ret = c_lines.groupby("order_id")["return_flag"].max().rename("has_return")
        orders = orders.merge(ret, on="order_id", how="left")
        orders["has_return"] = orders["has_return"].fillna(False).astype(bool)
        orders["is_returned"] = orders["has_return"] | returned_by_status
    else:
        orders["has_return"] = False
        orders["is_returned"] = returned_by_status
    # đơn trả hàng (theo trạng thái **hoặc** dòng số lượng âm)
    orders["has_return"] = orders["has_return"].astype(bool) | orders["is_returned"].astype(bool)
    orders["is_cod"] = _pay_flag(orders, ("cod", "thu ho", "giao hang thu tien"))
    orders["is_marketplace"] = _pay_flag(orders, ("shopee", "lazada", "tiktok", "tmdt",
                                                   "san thuong mai", "s marketplace"))
    orders["is_walkin"] = orders["customer_name"].map(_is_walkin)
    return _finalize_orders(orders)


def _is_walkin(value: Any) -> bool:
    """Tên khách lẻ (không lưu tên khách thật)."""
    if not isinstance(value, str):
        return True
    key = nd(value)
    return key in WALKIN_NAMES or bool(WALKIN_RE.search(key))


def _pay_flag(orders: pd.DataFrame, words: tuple[str, ...]) -> pd.Series:
    out = pd.Series([False] * len(orders))
    for col in ("pay_method", "channel", "status_raw"):
        if col not in orders.columns:
            continue
        s = orders[col].map(lambda v: nd(str(v)) if isinstance(v, str) else "")
        out = out | s.map(lambda x: any(w in x for w in words))
    return out


# --------------------------------------------------------------- c_products

def _build_products(by_name: dict[str, Any], info: dict[str, Any] | None,
                    c_lines: pd.DataFrame,
                    c_units: pd.DataFrame | None = None) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    if info:
        t = by_name.get(info["table"])
        if t is not None:
            df = t.df
            cols = info["cols"]
            n = len(df)
            part = pd.DataFrame(index=range(n))
            for role in ("product_code", "product_name", "category"):
                s = _text(df, cols, role)
                part[role] = s.reset_index(drop=True) if s is not None else _empty(n)
            uc = _num(df, cols, "unit_cost")
            part["unit_cost"] = uc.reset_index(drop=True) if uc is not None else _empty(n)
            u = _text(df, cols, "unit")
            part["unit"] = u.reset_index(drop=True) if u is not None else _empty(n)
            frames.append(part)
    if not c_lines.empty:
        lines_prod = c_lines[["product_code", "product_name"]].drop_duplicates(
            subset=["product_code"], keep="first")
        frames.append(lines_prod.assign(category=None, unit=None, unit_cost=None))
    if not frames:
        return pd.DataFrame(columns=CANON_PRODUCTS_COLS)
    prod = pd.concat(frames, ignore_index=True)
    prod = prod.drop_duplicates(subset=["product_code"], keep="first").reset_index(drop=True)
    prod["product_code"] = prod["product_code"].map(
        lambda v: v if isinstance(v, str) and v.strip() else None)
    prod = prod[prod["product_code"].notna()].reset_index(drop=True)
    if c_units is not None and not c_units.empty and "base_unit" in c_units.columns:
        bu = (c_units.dropna(subset=["base_unit"])
              .drop_duplicates(subset=["product_code"])[["product_code", "base_unit"]])
        prod = prod.merge(bu, on="product_code", how="left")
        prod["unit"] = prod["unit"].fillna(prod["base_unit"])
        prod.drop(columns=["base_unit"], inplace=True)
    return prod[CANON_PRODUCTS_COLS]


# -------------------------------------------------------------- c_customers

def _build_customers(by_name: dict[str, Any], info: dict[str, Any] | None,
                     c_orders: pd.DataFrame) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    if info:
        t = by_name.get(info["table"])
        if t is not None:
            df = t.df
            cols = info["cols"]
            n = len(df)
            part = pd.DataFrame(index=range(n))
            for role in ("customer_key", "customer_name", "phone", "customer_group"):
                s = _text(df, cols, role)
                part[role] = s.reset_index(drop=True) if s is not None else _empty(n)
            cs = _date(df, cols, "customer_since")
            part["customer_since"] = cs.reset_index(drop=True) if cs is not None else _empty(n)
            frames.append(part)
    if not c_orders.empty:
        cust = c_orders[["customer_key", "customer_name"]].dropna(
            subset=["customer_key"]).drop_duplicates(subset=["customer_key"], keep="first")
        frames.append(cust.assign(phone=None, customer_group=None, customer_since=None))
    if not frames:
        return pd.DataFrame(columns=CANON_CUSTOMERS_COLS)
    cust = pd.concat(frames, ignore_index=True)
    cust["customer_key"] = cust["customer_key"].map(
        lambda v: v if isinstance(v, str) and v.strip() else None)
    cust = cust.drop_duplicates(subset=["customer_key"], keep="first").reset_index(drop=True)
    cust["is_walkin"] = cust["customer_name"].map(_is_walkin)
    return cust[CANON_CUSTOMERS_COLS]


# --------------------------------------------------------------- c_payments

def _build_payments(by_name: dict[str, Any], info: dict[str, Any] | None,
                    c_orders: pd.DataFrame) -> pd.DataFrame:
    if not info:
        return pd.DataFrame(columns=CANON_PAYMENTS_COLS)
    t = by_name.get(info["table"])
    if t is None:
        return pd.DataFrame(columns=CANON_PAYMENTS_COLS)
    df = t.df
    cols = info["cols"]
    n = len(df)
    pay = pd.DataFrame(index=range(n))
    oid = _text(df, cols, "order_id")
    pay["order_id"] = oid.reset_index(drop=True) if oid is not None else _empty(n)
    pd_ = _date(df, cols, "pay_date")
    pay["pay_date"] = pd_.reset_index(drop=True) if pd_ is not None else _empty(n)
    amt = _num(df, cols, "pay_amount")
    pay["pay_amount"] = amt.reset_index(drop=True) if amt is not None else _empty(n)
    pm = _text(df, cols, "pay_method")
    pay["pay_method"] = pm.reset_index(drop=True) if pm is not None else _empty(n)
    ck = _text(df, cols, "customer_key")
    pay["customer_key"] = ck.reset_index(drop=True) if ck is not None else _empty(n)
    if pay["customer_key"].isna().all() and not c_orders.empty:
        cmap = c_orders[["order_id", "customer_key"]].dropna(subset=["order_id"])
        mapping_ck = cmap.drop_duplicates(subset=["order_id"]).set_index("order_id")["customer_key"]
        pay["customer_key"] = pay["order_id"].map(mapping_ck)
    return pay[CANON_PAYMENTS_COLS].reset_index(drop=True)


# ------------------------------------------------------------------ c_units

def _build_units(by_name: dict[str, Any], info: dict[str, Any] | None,
                 readme: str) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    if info:
        t = by_name.get(info["table"])
        if t is not None:
            df = t.df
            cols = info["cols"]
            n = len(df)
            part = pd.DataFrame(index=range(n))
            pc = _text(df, cols, "product_code")
            pn = _text(df, cols, "product_name")
            # Một số danh mục quy đổi gọi mặt hàng đơn giản là "Hàng";
            # mapper có thể gán nó vào unit_name vì product_name thuộc
            # namespace lines. Khôi phục theo cấu trúc của bảng quy đổi.
            if pc is None and pn is None and "unit_name" in cols:
                pn = _text(df, {"product_name": cols["unit_name"]}, "product_name")
            part["product_code"] = pc.reset_index(drop=True) if pc is not None else (
                pn.reset_index(drop=True) if pn is not None else _empty(n))
            un = _text(df, cols, "unit_name")
            if "unit_name" in cols and nd(str(cols["unit_name"])) in ("hang", "san pham"):
                large = next((c for c in df.columns
                              if "dv lon" in nd(str(c)) or "don vi lon" in nd(str(c))), None)
                if large is not None:
                    un = _text(df, {"unit_name": large}, "unit_name")
            part["unit_name"] = un.reset_index(drop=True) if un is not None else _empty(n)
            uf = _num(df, cols, "unit_factor")
            part["unit_factor"] = uf.reset_index(drop=True) if uf is not None else _empty(n)
            bu = _text(df, cols, "base_unit")
            part["base_unit"] = bu.reset_index(drop=True) if bu is not None else _empty(n)
            frames.append(part)
    if not frames:
        # thử quy đổi trong README: "- Coca Cola 330ml: 1 lốc = 6 lon"
        rows = []
        for m in re.finditer(
                r"[-*]\s*(.+?):\s*1\s*([^\s=]+)\s*=\s*(\d+(?:[.,]\d+)?)\s*([^\s,.]+)",
                readme or ""):
            rows.append({"product_name": m.group(1).strip(), "unit_name": m.group(2).strip(),
                         "unit_factor": float(m.group(3).replace(",", ".")),
                         "base_unit": m.group(4).strip()})
        if rows:
            frames.append(pd.DataFrame(rows))
    if not frames:
        return pd.DataFrame(columns=CANON_UNITS_COLS)
    units = pd.concat(frames, ignore_index=True)
    if "product_code" not in units.columns or units["product_code"].isna().all():
        units["product_code"] = units.get("product_name")
    # mã hàng phải khớp c_lines.product_code (= tên bỏ dấu khi không có mã)
    if units["product_code"].notna().all():
        from text.normalize import column_key

        units["product_code"] = units["product_code"].map(column_key)
    units["product_code"] = units["product_code"].map(
        lambda v: v if isinstance(v, str) and v.strip() else None)
    units = units.dropna(subset=["product_code", "unit_factor"])
    units = units.drop_duplicates(subset=["product_code", "unit_name"], keep="first")
    if "base_unit" not in units.columns:
        units["base_unit"] = None
    return units[CANON_UNITS_COLS].reset_index(drop=True)


# ---------------------------------------------------------------- c_imports

def _build_imports(by_name: dict[str, Any], info: dict[str, Any] | None) -> pd.DataFrame:
    if not info:
        return pd.DataFrame(columns=CANON_IMPORTS_COLS)
    t = by_name.get(info["table"])
    if t is None:
        return pd.DataFrame(columns=CANON_IMPORTS_COLS)
    df = t.df
    cols = info["cols"]
    n = len(df)
    imp = pd.DataFrame(index=range(n))
    iid = _text(df, cols, "import_id")
    imp["import_id"] = iid.reset_index(drop=True) if iid is not None else _empty(n)
    idt = _date(df, cols, "import_date")
    imp["import_date"] = idt.reset_index(drop=True) if idt is not None else _empty(n)
    pc = _text(df, cols, "product_code")
    imp["product_code"] = pc.reset_index(drop=True) if pc is not None else _empty(n)
    q = _num(df, cols, "qty")
    imp["qty"] = q.reset_index(drop=True) if q is not None else _empty(n)
    qb = _num(df, cols, "qty_base")
    imp["qty_base"] = qb.reset_index(drop=True) if qb is not None else _empty(n)
    un = _text(df, cols, "unit_name")
    imp["unit_name"] = un.reset_index(drop=True) if un is not None else _empty(n)
    amt = _num(df, cols, "import_amount")
    if amt is None:
        amt = _num(df, cols, "line_amount")
    imp["amount"] = amt.reset_index(drop=True) if amt is not None else _empty(n)
    sup = _text(df, cols, "supplier")
    imp["supplier"] = sup.reset_index(drop=True) if sup is not None else _empty(n)
    st = _text(df, cols, "import_status")
    if st is not None:
        s_nd = st.map(lambda v: nd(str(v)) if isinstance(v, str) else "")
        imp["is_cancelled"] = s_nd.map(lambda x: any(w in x for w in CANCELLED_WORDS))
    else:
        imp["is_cancelled"] = False
    return imp[CANON_IMPORTS_COLS].reset_index(drop=True)


def _build_inventory(by_name: dict[str, Any], info: dict[str, Any] | None) -> pd.DataFrame:
    if not info:
        return pd.DataFrame(columns=CANON_INVENTORY_COLS)
    t = by_name.get(info["table"])
    if t is None:
        return pd.DataFrame(columns=CANON_INVENTORY_COLS)
    df = t.df
    cols = info["cols"]
    n = len(df)
    inv = pd.DataFrame(index=range(n))
    pc = _text(df, cols, "product_code")
    inv["product_code"] = pc.reset_index(drop=True) if pc is not None else _empty(n)
    idt = _date(df, cols, "inv_date")
    inv["inv_date"] = idt.reset_index(drop=True) if idt is not None else _empty(n)
    q = _num(df, cols, "inv_qty")
    inv["inv_qty"] = q.reset_index(drop=True) if q is not None else _empty(n)
    lot = _text(df, cols, "lot_id")
    inv["lot_id"] = lot.reset_index(drop=True) if lot is not None else _empty(n)
    return inv[CANON_INVENTORY_COLS].reset_index(drop=True)


def _build_lots(by_name: dict[str, Any], info: dict[str, Any] | None) -> pd.DataFrame:
    if not info:
        return pd.DataFrame(columns=CANON_LOTS_COLS)
    t = by_name.get(info["table"])
    if t is None:
        return pd.DataFrame(columns=CANON_LOTS_COLS)
    df = t.df
    cols = info["cols"]
    n = len(df)
    lots = pd.DataFrame(index=range(n))
    lid = _text(df, cols, "lot_id")
    lots["lot_id"] = lid.reset_index(drop=True) if lid is not None else _empty(n)
    pc = _text(df, cols, "product_code")
    lots["product_code"] = pc.reset_index(drop=True) if pc is not None else _empty(n)
    ld = _date(df, cols, "lot_date")
    lots["lot_date"] = ld.reset_index(drop=True) if ld is not None else _empty(n)
    lq = _num(df, cols, "lot_qty")
    lots["lot_qty"] = lq.reset_index(drop=True) if lq is not None else _empty(n)
    lc = _num(df, cols, "lot_cost")
    lots["lot_cost"] = lc.reset_index(drop=True) if lc is not None else _empty(n)
    ex = _date(df, cols, "expiry_date")
    lots["expiry_date"] = ex.reset_index(drop=True) if ex is not None else _empty(n)
    return lots[CANON_LOTS_COLS].reset_index(drop=True)


def _build_price_history(by_name: dict[str, Any], info: dict[str, Any] | None) -> pd.DataFrame:
    if not info:
        return pd.DataFrame(columns=CANON_PRICE_COLS)
    t = by_name.get(info["table"])
    if t is None:
        return pd.DataFrame(columns=CANON_PRICE_COLS)
    df = t.df
    cols = info["cols"]
    n = len(df)
    ph = pd.DataFrame(index=range(n))
    pc = _text(df, cols, "product_code")
    ph["product_code"] = pc.reset_index(drop=True) if pc is not None else _empty(n)
    pd_ = _date(df, cols, "ph_date")
    ph["ph_date"] = pd_.reset_index(drop=True) if pd_ is not None else _empty(n)
    po = _num(df, cols, "ph_old")
    ph["ph_old"] = po.reset_index(drop=True) if po is not None else _empty(n)
    pn = _num(df, cols, "ph_new")
    ph["ph_new"] = pn.reset_index(drop=True) if pn is not None else _empty(n)
    return ph[CANON_PRICE_COLS].reset_index(drop=True)


def _build_deliveries(by_name: dict[str, Any], info: dict[str, Any] | None) -> pd.DataFrame:
    if not info:
        return pd.DataFrame(columns=CANON_DELIVERIES_COLS)
    t = by_name.get(info["table"])
    if t is None:
        return pd.DataFrame(columns=CANON_DELIVERIES_COLS)
    df = t.df
    cols = info["cols"]
    n = len(df)
    d = pd.DataFrame(index=range(n))
    oid = _text(df, cols, "order_id")
    d["order_id"] = oid.reset_index(drop=True) if oid is not None else _empty(n)
    dd = _date(df, cols, "del_date")
    d["del_date"] = dd.reset_index(drop=True) if dd is not None else _empty(n)
    em = _text(df, cols, "employee")
    d["employee"] = em.reset_index(drop=True) if em is not None else _empty(n)
    dr = _text(df, cols, "del_round")
    d["del_round"] = dr.reset_index(drop=True) if dr is not None else _empty(n)
    return d[CANON_DELIVERIES_COLS].reset_index(drop=True)
