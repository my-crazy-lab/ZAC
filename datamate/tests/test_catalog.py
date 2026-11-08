from datetime import date
from types import SimpleNamespace

from dtypes import TimeWindow
from engine.catalog import build_catalog, retrieve_templates


def _ctx(views, caps):
    return SimpleNamespace(views=set(views), data_caps=set(caps))


WINDOWS = [TimeWindow("main", date(2026, 1, 1), date(2026, 1, 31)),
           TimeWindow("base", date(2025, 12, 1), date(2025, 12, 31))]


def test_catalog_has_total_and_rank_templates():
    cat = build_catalog(_ctx({"v_lines", "v_orders"},
                             {"line_amount", "qty", "order_date"}))
    ids = {t.id for t in cat}
    assert "revenue.total" in ids
    assert "revenue.product.rank" in ids
    assert "qty.product.rank" in ids


def test_catalog_respects_missing_capability():
    cat = build_catalog(_ctx({"v_lines"}, {"qty"}))
    ids = {t.id for t in cat}
    assert "qty.total" in ids
    assert not any(i.startswith("revenue") for i in ids)


def test_retrieve_prefers_revenue_for_revenue_question():
    cat = build_catalog(_ctx({"v_lines", "v_orders"},
                             {"line_amount", "qty", "order_date"}))
    got = retrieve_templates("doanh thu theo từng sản phẩm tháng này", cat,
                             k=5, windows=WINDOWS)
    assert got
    assert got[0].metric == "revenue"


def test_template_to_spec_uses_plan_params():
    cat = build_catalog(_ctx({"v_lines", "v_orders"},
                             {"line_amount", "qty", "order_date"}))
    tpl = next(t for t in cat if t.id == "revenue.product.rank")
    spec, errs = tpl.to_spec({"params": {"limit": 3}, "filters": [], "time": []},
                             WINDOWS)
    assert not errs
    assert spec is not None
    assert spec.intent == "rank_top"
    assert spec.subject == "product"
    assert spec.limit == 3


def test_unknown_param_is_rejected():
    cat = build_catalog(_ctx({"v_lines", "v_orders"},
                             {"line_amount", "qty", "order_date"}))
    tpl = next(t for t in cat if t.id == "revenue.total")
    spec, errs = tpl.to_spec({"params": {"sql": "DROP TABLE x"}, "filters": [],
                              "time": []}, WINDOWS)
    assert spec is None
    assert any("param_unknown" in e for e in errs)


def test_compare_template_requires_base_window():
    cat = build_catalog(_ctx({"v_lines", "v_orders"},
                             {"line_amount", "qty", "order_date"}))
    tpl = next(t for t in cat if t.id == "revenue.window.compare")
    spec, errs = tpl.to_spec({"params": {}, "filters": [], "time": []},
                             [WINDOWS[0]])
    assert spec is None
    assert any("base_window" in e for e in errs)
