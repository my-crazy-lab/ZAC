"""Registry metric (EXECUTION-MVP.md §4.3).

Metric = công thức nghiệp vụ **đã được code**, không phải do LLM tự viết.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MetricDef:
    name: str
    caps: set[str]
    source: str
    date_col: str
    value_expr: str
    subjects: set[str]
    is_money: bool
    default_output: str
    template: str = "std"
    # Miền dữ liệu gốc của metric — dùng để so khớp với chủ đề câu hỏi.
    domain: str = "sales"  # sales | purchase | inventory | debt
    # Metric chỉ có nghĩa khi gắn với một đối tượng cụ thể (giá một mặt
    # hàng, tuổi nợ một khách). Không nhận ra đối tượng ⇒ không nên trả
    # con số tổng của cả shop.
    requires_entity: bool = False


ALL_SUBJECTS = {"product", "category", "customer", "day", "week", "month",
                "channel", "pay_method", "employee", "customer_group", "window", "none"}

REGISTRY: dict[str, MetricDef] = {
    "revenue": MetricDef(
        name="revenue", caps={"line_amount"}, source="v_lines", date_col="order_date",
        value_expr="SUM(s.line_amount_net)",
        subjects={"product", "category", "customer", "day", "week", "month", "channel",
                  "pay_method", "employee", "customer_group", "window"},
        is_money=True, default_output="number"),
    "qty": MetricDef(
        name="qty", caps={"qty"}, source="v_lines", date_col="order_date",
        value_expr="SUM(COALESCE(s.qty_base, s.qty))",
        subjects={"product", "category", "customer", "day", "week", "month", "window"},
        is_money=False, default_output="number"),
    "orders": MetricDef(
        name="orders", caps={"order_date"}, source="v_orders", date_col="order_date",
        value_expr="COUNT(DISTINCT s.order_id)",
        subjects={"customer", "day", "week", "month", "channel", "pay_method",
                  "employee", "window"},
        is_money=False, default_output="number"),
    "customers": MetricDef(
        name="customers", caps={"customer"}, source="v_orders", date_col="order_date",
        value_expr=("COUNT(DISTINCT COALESCE(NULLIF(s.customer_key, ''), "
                    "lower(s.customer_name))) FILTER (WHERE NOT s.is_walkin)"),
        subjects={"day", "week", "month", "channel", "window"},
        is_money=False, default_output="number"),
    "aov": MetricDef(
        name="aov", caps={"line_amount"}, source="v_lines", date_col="order_date",
        value_expr=("SUM(s.line_amount_net) / NULLIF(COUNT(DISTINCT s.order_id), 0)"),
        subjects={"day", "week", "month", "channel", "window"},
        is_money=True, default_output="number"),
    "cancel_rate": MetricDef(
        name="cancel_rate", caps={"order_date"}, source="v_orders_all", date_col="order_date",
        value_expr=("100.0 * SUM(CASE WHEN s.is_cancelled THEN 1 ELSE 0 END) "
                    "/ NULLIF(COUNT(*), 0)"),
        subjects={"day", "week", "month", "channel", "window"},
        is_money=False, default_output="percent", template="cancel_rate"),
    "cancelled_orders": MetricDef(
        name="cancelled_orders", caps={"order_date"}, source="v_orders_all",
        date_col="order_date",
        value_expr="COUNT(*) FILTER (WHERE s.is_cancelled)",
        subjects={"day", "week", "month", "channel", "window"},
        is_money=False, default_output="number", template="cancel_rate"),
    "profit": MetricDef(
        name="profit", caps={"line_amount", "cost_line"}, source="v_lines",
        date_col="order_date", value_expr="SUM(s.line_amount_net - s.line_cost_total)",
        subjects={"product", "category", "customer", "day", "week", "month", "window"},
        is_money=True, default_output="number"),
    "stock": MetricDef(
        name="stock", caps={"stock"}, source="v_inventory", date_col="inv_date",
        value_expr="SUM(s.inv_qty)",
        subjects={"product", "category"}, is_money=False, default_output="number",
        template="point_stock", domain="inventory"),
    "stock_value": MetricDef(
        name="stock_value", caps={"stock", "cost_catalog"}, source="v_inventory",
        date_col="inv_date", value_expr="SUM(s.inv_qty * p.unit_cost)",
        subjects={"category", "none"}, is_money=True, default_output="number",
        template="point_stock", domain="inventory"),
    "debt": MetricDef(
        name="debt", caps={"debt"}, source="v_debt_events", date_col="event_date",
        value_expr="SUM(s.delta)",
        subjects={"customer", "none"}, is_money=True, default_output="number",
        template="point_debt", domain="debt"),
    "debt_age": MetricDef(
        name="debt_age", caps={"debt", "payments"}, source="v_debt_events",
        date_col="event_date", value_expr="MAX(s.delta)",
        subjects={"customer"}, is_money=False, default_output="number",
        template="point_debt", domain="debt", requires_entity=True),
    "expiring": MetricDef(
        name="expiring", caps={"expiry", "stock"}, source="v_lots", date_col="expiry_date",
        value_expr="SUM(s.lot_qty)",
        subjects={"product"}, is_money=False, default_output="number",
        template="expiring", domain="inventory"),
    "stock_split_unit": MetricDef(
        name="stock_split_unit", caps={"stock", "units"}, source="v_inventory",
        date_col="inv_date", value_expr="SUM(s.inv_qty)",
        subjects={"product"}, is_money=False, default_output="list",
        template="point_stock", domain="inventory", requires_entity=True),
    "price": MetricDef(
        name="price", caps={"line_amount"}, source="v_lines_all", date_col="order_date",
        value_expr="AVG(s.unit_price)",
        subjects={"product", "none"}, is_money=True, default_output="number",
        requires_entity=True),
    "import_amount": MetricDef(
        name="import_amount", caps={"imports"}, source="v_imports", date_col="import_date",
        value_expr="SUM(s.amount)",
        subjects={"product", "day", "week", "month", "supplier", "window"},
        is_money=True, default_output="number", domain="purchase"),
    "import_avg_price": MetricDef(
        name="import_avg_price", caps={"imports"}, source="v_imports",
        date_col="import_date",
        value_expr=("SUM(s.amount) / NULLIF(SUM(COALESCE(s.qty_base, s.qty)), 0)"),
        subjects={"product"}, is_money=True, default_output="number",
        domain="purchase", requires_entity=True),
}


def get(metric: str | None) -> MetricDef | None:
    if not metric:
        return None
    return REGISTRY.get(metric)


def metric_names() -> list[str]:
    return sorted(REGISTRY)


def subjects_for(metric: str) -> set[str]:
    m = get(metric)
    return set(m.subjects) if m else set()
