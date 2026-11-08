from types import SimpleNamespace

import pandas as pd

from schema.business_graph import (build_business_graph, render_graph_card,
                                   semantic_graph_issues, validate_business_graph)


def _table(name, columns):
    return SimpleNamespace(name=name, source=f"{name}.xlsx",
                           df=pd.DataFrame({c: [1] for c in columns}))


def test_graph_keeps_real_tables_roles_and_readme_rules():
    tables = [_table("orders", ["Mã đơn", "Ngày bán", "Tổng tiền"])]
    mapping = {"entities": {"orders": {"table": "orders", "tables": ["orders"],
                                        "cols": {"order_id": "Mã đơn", "order_date": "Ngày bán"}}}}
    readme = "## Quy ước\n- Ghi chú=hủy → cancelled_order\n- Phí ship → shipping_fee"
    graph = build_business_graph(tables, readme, mapping)
    assert not validate_business_graph(graph, mapping)
    card = render_graph_card(graph)
    assert "entity orders: tables=orders" in card
    assert "Ghi chú=hủy" in card


def test_graph_reports_mapping_reference_not_in_source_table():
    tables = [_table("orders", ["Mã đơn"])]
    mapping = {"entities": {"orders": {"table": "orders", "tables": ["orders"],
                                        "cols": {"order_date": "Ngày bán"}}}}
    graph = build_business_graph(tables, "", mapping)
    errors = validate_business_graph(graph, mapping)
    assert errors and "missing column orders.Ngày bán" in errors[0]


def test_graph_card_selects_question_relevant_entity():
    tables = [_table("orders", ["Mã đơn"]), _table("khach", ["Mã khách"])]
    mapping = {"entities": {
        "orders": {"table": "orders", "tables": ["orders"], "cols": {"order_id": "Mã đơn"}},
        "customers": {"table": "khach", "tables": ["khach"], "cols": {"customer_key": "Mã khách"}},
    }}
    graph = build_business_graph(tables, "", mapping)
    card = render_graph_card(graph, "doanh thu tháng trước")
    assert "entity orders" in card
    assert "entity customers" not in card


def test_semantic_graph_rejects_revenue_without_money_source():
    graph = build_business_graph([_table("orders", ["Mã đơn"])], "", {
        "entities": {"orders": {"table": "orders", "tables": ["orders"],
                                  "cols": {"order_id": "Mã đơn"}}}})
    issues = semantic_graph_issues("doanh thu tháng trước", graph)
    assert any("revenue" in issue for issue in issues)


def test_semantic_graph_accepts_qty_with_line_source():
    graph = build_business_graph([_table("lines", ["SL", "Tên hàng"])], "", {
        "entities": {"lines": {"table": "lines", "tables": ["lines"],
                                 "cols": {"qty": "SL", "product_name": "Tên hàng"}}}})
    assert not any("qty" in issue for issue in semantic_graph_issues("số lượng bán", graph))
