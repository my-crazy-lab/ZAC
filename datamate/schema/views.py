"""Dựng view ``v_*`` (áp luật rulebook) và context của một shop (M4.F).

Quy tắc vàng: **view KHÔNG chứa ``as_of``** — mọi cắt theo ``as_of`` do
``compile_spec`` chèn vào SQL.
"""

from __future__ import annotations

import logging
import os
from datetime import date
from typing import Any

import pandas as pd

import config
from dtypes import BizContext, Knobs, RuleSpec
from ingest.reader import cache_key, load_business, readme_text
from schema.archetypes import detect_archetype
from schema.canon import canonicalize
from schema.invariants import compute_all
from schema.mapper import map_business, parse_readme_facts
from schema.business_graph import (build_business_graph, render_graph_card,
                                   validate_business_graph)
from schema.context import build_snapshot, compile_context
from engine.catalog import build_catalog
from text.entity_linker import build_entity_index

log = logging.getLogger(__name__)


def _safe_exec(con: Any, sql: str, label: str = "") -> None:
    """Tạo view; bỏ qua nếu bảng gốc không tồn tại."""
    try:
        con.execute(sql)
    except Exception as exc:  # noqa: BLE001
        log.debug("bỏ qua view %s: %s", label, exc)


def _tables(con: Any) -> set[str]:
    return {r[0] for r in con.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='main'"
    ).fetchall()}


def build_views(con: Any, knobs: Knobs, flags: dict[str, Any]) -> None:
    """Tạo các view ``v_*`` trong connection (KHÔNG có ``as_of``)."""
    tables = _tables(con)

    # --- v_orders_all: mọi trạng thái
    if "c_orders" in tables:
        _safe_exec(con, """
            CREATE OR REPLACE VIEW v_orders_all AS
            SELECT order_id, order_date, order_ts, customer_key, customer_name,
                   status_raw, channel, pay_method, employee,
                   is_cancelled, is_returned, has_return, is_cod, is_marketplace,
                   is_walkin, order_total, order_debt_total, order_paid,
                   shipping_fee, vat_amount, order_voucher
            FROM c_orders
        """)
        conds = []
        if knobs.exclude_cancelled:
            conds.append("NOT is_cancelled")
        if knobs.returned_policy == "exclude_order":
            conds.append("NOT has_return")
        where = (" WHERE " + " AND ".join(conds)) if conds else ""
        _safe_exec(con, """
            CREATE OR REPLACE VIEW v_orders AS
            SELECT * FROM v_orders_all""" + where)

    # --- v_lines
    tables = _tables(con)
    if "c_lines" in tables and "c_orders" in tables:
        net = "COALESCE(l.line_amount, 0)"
        if flags.get("line_amount_includes_vat"):
            net = ("(COALESCE(l.line_amount, 0) / "
                   "NULLIF(1 + COALESCE(o.vat_rate, 0), 0))")
        if knobs.revenue_deduct_order_voucher:
            net = (f"({net} - COALESCE(o.order_voucher, 0) * "
                   f"CASE WHEN SUM(COALESCE(l.line_amount, 0)) OVER (PARTITION BY l.order_id) > 0 "
                   f"THEN COALESCE(l.line_amount, 0) / "
                   f"SUM(COALESCE(l.line_amount, 0)) OVER (PARTITION BY l.order_id) "
                   f"ELSE 0 END)")
        if knobs.revenue_include_shipping:
            net = f"({net} + COALESCE(o.shipping_fee, 0))"
        _safe_exec(con, f"""
            CREATE OR REPLACE VIEW v_lines AS
            SELECT l.order_id, o.order_date, o.order_ts, l.line_no,
                   l.product_code, l.product_name, p.category,
                   o.customer_key, o.customer_name, o.is_walkin,
                   o.channel, o.pay_method, o.employee, c.customer_group,
                   l.qty, l.qty_base, l.unit_name, p.unit AS base_unit,
                   {net} AS line_amount_net,
                   l.line_cost_total, l.is_service, l.size,
                   l.return_flag
            FROM c_lines l
            JOIN v_orders o ON l.order_id = o.order_id
            LEFT JOIN c_products p ON l.product_code = p.product_code
            LEFT JOIN c_customers c ON o.customer_key = c.customer_key
        """)

    # --- fallback: shop chỉ có đơn (không có dòng hàng) ⇒ v_lines giả lấy từ đơn
    tables = _tables(con)
    if "c_lines" not in tables and "c_orders" in tables:
        _safe_exec(con, """
            CREATE OR REPLACE VIEW v_lines AS
            SELECT o.order_id, o.order_date, o.order_ts, 1 AS line_no,
                   NULL AS product_code, NULL AS product_name, NULL AS category,
                   o.customer_key, o.customer_name, o.is_walkin,
                   o.channel, o.pay_method, o.employee, NULL AS customer_group,
                   NULL AS qty, NULL AS qty_base, NULL AS unit_name, NULL AS base_unit,
                   COALESCE(o.order_total, 0) AS line_amount_net,
                   NULL AS line_cost_total, FALSE AS is_service, NULL AS size,
                   FALSE AS return_flag
            FROM v_orders o
        """)

    # --- v_lines_all: mọi dòng (kể cả đơn huỷ / trả hàng) — dùng cho "giá bán"
    tables = _tables(con)
    if "c_lines" in tables and "c_orders" in tables:
        _safe_exec(con, """
            CREATE OR REPLACE VIEW v_lines_all AS
            SELECT l.order_id, o.order_date, o.order_ts, l.line_no,
                   l.product_code, l.product_name, p.category,
                   o.customer_key, o.customer_name, o.is_walkin,
                   o.channel, o.pay_method, o.employee, c.customer_group,
                   l.qty, l.qty_base, l.unit_name, p.unit AS base_unit,
                   COALESCE(l.line_amount, 0) AS line_amount_net,
                   l.unit_price, l.line_cost_total, l.is_service, l.size,
                   l.return_flag
            FROM c_lines l
            JOIN v_orders_all o ON l.order_id = o.order_id
            LEFT JOIN c_products p ON l.product_code = p.product_code
            LEFT JOIN c_customers c ON o.customer_key = c.customer_key
        """)

    # --- v_products: tên master = tên xuất hiện nhiều nhất theo product_code
    tables = _tables(con)
    if "c_lines" in tables:
        _safe_exec(con, """
            CREATE OR REPLACE VIEW v_products AS
            WITH cnt AS (
                SELECT product_code, product_name, COUNT(*) AS n,
                       ROW_NUMBER() OVER (PARTITION BY product_code
                                          ORDER BY COUNT(*) DESC, product_name ASC) AS rn
                FROM c_lines WHERE product_name IS NOT NULL
                GROUP BY product_code, product_name
            ), base AS (
                SELECT product_code, ANY_VALUE(product_name) AS product_name,
                       ANY_VALUE(category) AS category, ANY_VALUE(unit) AS unit,
                       ANY_VALUE(unit_cost) AS unit_cost
                FROM c_products GROUP BY product_code
            )
            SELECT b.product_code, COALESCE(cnt.product_name, b.product_name) AS product_name,
                   b.category, b.unit, b.unit_cost
            FROM base b LEFT JOIN cnt ON cnt.product_code = b.product_code AND cnt.rn = 1
        """)

    # --- v_customers
    tables = _tables(con)
    if "c_customers" in tables:
        _safe_exec(con, """
            CREATE OR REPLACE VIEW v_customers AS
            SELECT customer_key, customer_name, lower(customer_name) AS customer_name_nd,
                   customer_group, customer_since, is_walkin
            FROM c_customers
        """)

    # --- v_payments
    tables = _tables(con)
    if "c_payments" in tables:
        _safe_exec(con, """
            CREATE OR REPLACE VIEW v_payments AS
            SELECT order_id, customer_key, pay_date, pay_amount, pay_method
            FROM c_payments
        """)

    # --- v_debt_events: nợ phát sinh (đơn ghi nợ +, trả nợ −)
    tables = _tables(con)
    if "c_orders" in tables and "c_payments" in tables:
        _safe_exec(con, """
            CREATE OR REPLACE VIEW v_debt_events AS
            SELECT o.customer_key, o.order_id, o.order_date AS event_date,
                   COALESCE(o.order_debt_total, 0) AS delta, 'order' AS kind
            FROM v_orders o
            WHERE NOT o.is_cancelled AND NOT o.is_cod AND NOT o.is_marketplace
              AND COALESCE(o.order_debt_total, 0) > 0
            UNION ALL
            SELECT p.customer_key, p.order_id, p.pay_date AS event_date,
                   -COALESCE(p.pay_amount, 0) AS delta, 'payment' AS kind
            FROM v_payments p
            JOIN v_orders o ON p.order_id = o.order_id
            WHERE NOT o.is_cancelled AND NOT o.is_cod AND NOT o.is_marketplace
        """)

    tables = _tables(con)
    for c_name, v_name in (("c_imports", "v_imports"), ("c_inventory", "v_inventory"),
                           ("c_lots", "v_lots"), ("c_units", "v_units"),
                           ("c_price_history", "v_price_history"),
                           ("c_deliveries", "v_deliveries")):
        if c_name in tables:
            _safe_exec(con, f"CREATE OR REPLACE VIEW {v_name} AS SELECT * FROM {c_name}")


def compute_data_caps(con: Any) -> set[str]:
    """Capability **dữ liệu** (EXECUTION-MVP.md §3.2)."""
    caps: set[str] = set()
    tables = _tables(con)

    def has(table: str, col: str) -> bool:
        if table not in tables:
            return False
        try:
            rows = con.execute(
                f'SELECT 1 FROM "{table}" WHERE "{col}" IS NOT NULL LIMIT 1').fetchall()
            return bool(rows)
        except Exception:  # noqa: BLE001
            return False

    if has("v_lines", "line_amount_net"):
        caps.add("line_amount")
    if has("v_lines", "qty"):
        caps.add("qty")
    if has("v_lines", "qty_base"):
        caps.add("qty_base")
    if has("v_orders", "order_date"):
        caps.add("order_date")
    if has("v_orders", "order_ts"):
        caps.add("order_ts")
    if has("v_orders", "customer_key") or has("v_orders", "customer_name"):
        caps.add("customer")
    if has("v_lines", "category"):
        caps.add("category")
    if has("v_lines", "line_cost_total"):
        caps.add("cost_line")
    if has("v_products", "unit_cost"):
        caps.add("cost_catalog")
    if "cost_line" in caps or "cost_catalog" in caps:
        caps.add("cost")
    if has("c_lots", "lot_qty") and has("c_lots", "lot_cost"):
        caps.add("lots")
    if has("c_lots", "expiry_date"):
        caps.add("expiry")
    if "c_inventory" in tables:
        caps.add("inventory_snapshot")
    if "inventory_snapshot" in caps or ("lots" in caps and "line_amount" in caps):
        caps.add("stock")
    if "v_payments" in tables:
        caps.add("payments")
    if has("v_orders", "order_debt_total"):
        caps.add("order_debt")
        caps.add("debt")
    if has("v_imports", "amount") or has("v_imports", "import_amount"):
        caps.add("imports")
    if has("v_price_history", "ph_new"):
        caps.add("price_history")
    if has("v_units", "unit_factor"):
        caps.add("units")
    for col, cap in (("channel", "channel"), ("pay_method", "pay_method"),
                     ("employee", "employee"), ("customer_group", "customer_group"),
                     ("customer_since", "customer_since")):
        if has("v_orders", col) or has("v_customers", col):
            caps.add(cap)
    if has("v_lines", "size"):
        caps.add("size")
    if has("v_lines", "return_flag"):
        caps.add("returns")
    if has("v_deliveries", "del_date"):
        caps.add("deliveries")
    return caps


def build_value_dict(con: Any) -> dict[str, list[str]]:
    """Danh mục từ điển giá trị (4.2)."""
    out: dict[str, list[str]] = {}
    specs = [
        ("channel", "v_orders", "channel"),
        ("pay_method", "v_orders", "pay_method"),
        ("customer_group", "v_customers", "customer_group"),
        ("employee", "v_orders", "employee"),
        ("size", "v_lines", "size"),
        ("category", "v_lines", "category"),
    ]
    for name, table, col in specs:
        try:
            rows = con.execute(
                f'SELECT DISTINCT "{col}" FROM "{table}" WHERE "{col}" IS NOT NULL LIMIT 51'
            ).fetchall()
        except Exception:  # noqa: BLE001
            continue
        vals = sorted({str(r[0]).strip() for r in rows if str(r[0]).strip()})
        if 0 < len(vals) <= 50:
            out[name] = vals
    return out


def _write_cache(cache_path: str, canon: dict[str, pd.DataFrame]) -> None:
    import duckdb

    os.makedirs(os.path.dirname(os.path.abspath(cache_path)), exist_ok=True)
    if os.path.exists(cache_path):
        os.remove(cache_path)
    con = duckdb.connect(cache_path)
    try:
        for name, df in canon.items():
            if df is None:
                continue
            con.register("_df", df)
            try:
                con.execute(f'CREATE OR REPLACE TABLE "{name}" AS SELECT * FROM _df')
            finally:
                con.unregister("_df")
    finally:
        con.close()


def build_context(biz_dir: str, knobs: Knobs, rules: RuleSpec, llm: Any = None,
                  archetype: str | None = None) -> BizContext:
    """Dựng context đầy đủ cho một shop (M4.F)."""
    import duckdb

    business_id = os.path.basename(os.path.normpath(biz_dir))
    tables = load_business(biz_dir)
    readme = readme_text(biz_dir)
    code = archetype or detect_archetype(tables)[0]

    candidates = map_business(tables, readme, llm)
    mapping_cand = candidates[0]
    mapping = mapping_cand.mapping
    business_graph = build_business_graph(tables, readme, mapping)
    graph_issues = validate_business_graph(business_graph, mapping)

    canon = canonicalize(tables, mapping, code, readme)
    inv_results, inv_penalties = compute_all(
        canon.get("c_lines", pd.DataFrame()), canon.get("c_orders", pd.DataFrame()),
        canon.get("c_units", pd.DataFrame()), canon.get("c_payments", pd.DataFrame()),
    )

    flags: dict[str, Any] = {}
    c_lines = canon.get("c_lines")
    if c_lines is not None and not c_lines.empty and "qty_base" in c_lines.columns:
        flags["qty_base_assumed"] = bool(c_lines["qty_base"].notna().sum() == 0)
    status_invalid: dict[str, Any] = {}
    c_orders = canon.get("c_orders", pd.DataFrame())
    if not c_orders.empty and "status_raw" in c_orders.columns:
        vals = [str(v) for v in c_orders["status_raw"].dropna().unique().tolist()]
        status_invalid = {"statuses": sorted(vals)[:50]}

    total_pen = min(1.0, sum(mapping_cand.penalties.values()) + sum(inv_penalties.values()))
    schema_conf = max(0.0, min(1.0, 1.0 - total_pen))

    # --- cache c_*
    key = cache_key(biz_dir, config.SCHEMA_VERSION)
    cache_path = os.path.join(config.cache_dir(), f"{key}.duckdb")
    if not os.path.exists(cache_path):
        _write_cache(cache_path, canon)

    con = duckdb.connect(":memory:")
    con.execute(f"ATTACH '{cache_path}' AS cache (READ_ONLY)")
    for name in canon:
        try:
            con.execute(f'CREATE VIEW "{name}" AS SELECT * FROM cache."{name}"')
        except Exception as exc:  # noqa: BLE001
            log.warning("không tạo view %s: %s", name, exc)
    build_views(con, knobs, flags)

    data_caps = compute_data_caps(con)
    value_dict = build_value_dict(con)
    entity_index = build_entity_index(con, value_dict)

    date_min, date_max = _date_range(con)
    card = build_card(con, code, data_caps, date_min, date_max, schema_conf, knobs,
                      value_dict, readme)
    flags["graph_issues"] = graph_issues

    views = {r[0] for r in con.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='main'"
    ).fetchall()}

    ctx = BizContext(
        con=con, archetype=code, data_caps=data_caps, views=views,
        date_min=date_min, date_max=date_max,
        schema_conf=schema_conf, flags=flags, status_invalid=status_invalid,
        value_dict=value_dict, card=card, entity_index=entity_index, rules=rules,
        invariants=inv_results, verified=True, business_id=business_id, biz_dir=biz_dir,
        graph=business_graph,
    )
    ctx.context = compile_context(readme, mapping, business_graph, knobs, views,
                                  data_caps, archetype=code, schema_conf=schema_conf,
                                  graph_issues=graph_issues,
                                  snapshot=build_snapshot(con, views))
    ctx.catalog = build_catalog(ctx)
    return ctx


def _date_range(con: Any) -> tuple[date, date]:
    try:
        row = con.execute(
            "SELECT MIN(order_date), MAX(order_date) FROM v_orders").fetchone()
    except Exception:  # noqa: BLE001
        row = (None, None)
    dmin, dmax = row if row else (None, None)
    if dmin is None:
        return date(2000, 1, 1), date(2100, 1, 1)
    if isinstance(dmin, pd.Timestamp):
        dmin = dmin.date()
    if isinstance(dmax, pd.Timestamp):
        dmax = dmax.date()
    return dmin, dmax


def build_card(con: Any, archetype: str, data_caps: set[str], date_min: date,
               date_max: date, schema_conf: float, knobs: Knobs,
               value_dict: dict[str, list[str]], readme: str) -> str:
    """Schema card (4.11) — ≤ 1500 token."""
    lines: list[str] = []
    lines.append(f"[DỮ LIỆU] archetype={archetype} | ngày: {date_min}..{date_max} | "
                 f"schema_conf={schema_conf:.2f}")
    lines.append("[NĂNG LỰC] " + ", ".join(sorted(data_caps)))
    lines.append("[VIEW]")
    try:
        rows = con.execute(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema='main' AND table_name LIKE 'v_%' ORDER BY table_name"
        ).fetchall()
    except Exception:  # noqa: BLE001
        rows = []
    by_view: dict[str, list[str]] = {}
    for t, c in rows:
        by_view.setdefault(str(t), []).append(str(c))
    for v in ("v_lines", "v_orders", "v_products", "v_customers", "v_debt_events"):
        if v in by_view:
            cols = by_view[v]
            head = ", ".join(cols[:14])
            more = ", …" if len(cols) > 14 else ""
            lines.append(f"{v}({head}{more})")
    if value_dict:
        parts = []
        for k in ("channel", "pay_method", "customer_group", "employee", "category", "size"):
            vals = value_dict.get(k)
            if vals:
                parts.append(f"{k}={{{', '.join(vals[:12])}}}")
        if parts:
            lines.append("[GIÁ TRỊ] " + " | ".join(parts))
    diff = knobs.diff_from_default()
    if diff:
        lines.append("[QUY TẮC KHÁC MẶC ĐỊNH] " +
                     ", ".join(f"{k}={v}" for k, v in sorted(diff.items())))
    facts = parse_readme_facts(readme)
    if facts["conventions"]:
        lines.append("[QUY ƯỚC README] " + " | ".join(facts["conventions"][:8])[:1400])
    if facts["unit_rules"]:
        lines.append("[QUY ĐỔI README] " + " | ".join(facts["unit_rules"][:6])[:800])
    return "\n".join(lines)
