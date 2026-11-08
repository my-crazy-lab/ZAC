"""Test cho M3/M4/M5: rulebook parser, mapper, sandbox, compiler."""

from __future__ import annotations

from datetime import date

import pytest

from dtypes import Spec
from engine.sandbox import SqlRejected, check_sql
from rules.rulebook_parser import parse_rulebook
from schema.mapper import parse_readme, parse_readme_facts
from ingest.reader import cache_key

def _rulebook() -> str:
    return open("train/rulebook.md", encoding="utf-8").read()


def test_parse_rulebook_defaults():
    spec = parse_rulebook(_rulebook(), _rulebook(), None)
    assert spec.knobs.revenue_include_vat is False
    assert spec.knobs.revenue_include_shipping is False
    assert spec.knobs.revenue_deduct_order_voucher is False
    assert spec.knobs.exclude_cancelled is True
    assert spec.knobs.returned_policy == "exclude_order"
    assert spec.knobs.bestseller_metric == "qty"
    assert spec.knobs.week_start == 0


def test_parse_rulebook_domains():
    spec = parse_rulebook(_rulebook(), _rulebook(), None)
    assert {"cafe", "pharmacy", "construction"} <= spec.domains


def test_parse_readme_columns():
    readme = open("train/data/biz_101/README.md", encoding="utf-8").read()
    cols = parse_readme(readme)
    key = [k for k in cols if "ban_hang" in k]
    assert key
    assert "ngay thang" in cols[key[0]]


def test_parse_readme_facts_keeps_conventions():
    readme = """## Cột trong `x.csv`\n- **Ngày**: ngày bán\n## Quy ước\n- Voucher là dòng giảm giá.\n- Quy đổi đơn vị: 1 thùng = 6 lon."""
    facts = parse_readme_facts(readme)
    assert any("Voucher" in x for x in facts["conventions"])
    assert facts["unit_rules"]
    assert "voucher" in facts["special_rows"]


def test_cache_key_changes_when_readme_changes(tmp_path):
    (tmp_path / "data.csv").write_text("a,b\n1,2\n", encoding="utf8")
    (tmp_path / "README.md").write_text("## Quy ước\n- A", encoding="utf8")
    before = cache_key(str(tmp_path), "v1")
    (tmp_path / "README.md").write_text("## Quy ước\n- B", encoding="utf8")
    assert cache_key(str(tmp_path), "v1") != before


def test_sandbox_rejects_write():
    with pytest.raises(SqlRejected):
        check_sql("DELETE FROM v_orders")
    with pytest.raises(SqlRejected):
        check_sql("SELECT 1; DROP TABLE v_orders")


def test_sandbox_allows_select():
    check_sql("SELECT 1 FROM v_orders WHERE order_date <= DATE '2026-01-01'")


def _ctx():
    from dtypes import BizContext
    return BizContext(con=None, archetype="A_flat", data_caps={"line_amount"},
                      views={"v_lines"}, date_min=date(2025, 1, 1),
                      date_max=date(2026, 1, 1), schema_conf=1.0, flags={},
                      status_invalid={}, value_dict={}, card="", entity_index=None,
                      rules=None, invariants={})


def _win(label, start, end):
    from dtypes import TimeWindow
    return TimeWindow(label=label, start=start, end=end)


def test_validate_spec_rejects_single_window_compare_series():
    from engine.compile import validate_spec
    spec = Spec(intent="compare_series", metric="revenue", subject="day",
                filters=[], time=["main"], output="date")
    errs = validate_spec(spec, _ctx(), [_win("main", date(2025, 4, 1), date(2025, 4, 30))])
    assert any("compare_series_needs_two_windows" in e for e in errs)


def test_cancel_rate_keywords_map_to_intent_and_metric():
    from engine.answer import keyword_intents, keyword_metrics
    assert "cancel_rate" in keyword_intents("ti le huy don thang 6/2025 la nhieu %")
    assert "cancelled_orders" in keyword_metrics("thang 5/2025 co bao nhieu % don bi huy")
    assert "cancel_rate" not in keyword_metrics("ti le huy don")


def test_cancel_rate_compiles_to_ratio():
    from dtypes import Knobs
    from engine.compile import compile_spec
    ctx = _ctx()
    ctx.views = {"v_orders_all"}
    ctx.data_caps = {"order_date"}
    spec = Spec(intent="cancel_rate", metric="cancelled_orders", subject="month",
                filters=[], time=["main"], output="percent")
    plan = compile_spec(spec, ctx, Knobs(),
                        [_win("main", date(2025, 6, 1), date(2025, 6, 30))],
                        date(2025, 6, 30))
    assert "100.0" in plan.sql and "NULLIF(COUNT(*), 0)" in plan.sql


def test_validate_spec_accepts_two_window_compare_series():
    from engine.compile import validate_spec
    spec = Spec(intent="compare_series", metric="revenue", subject="month",
                filters=[], time=["p1", "p2"], output="string")
    errs = validate_spec(spec, _ctx(), [_win("p1", date(2025, 3, 1), date(2025, 3, 31)),
                                        _win("p2", date(2025, 4, 1), date(2025, 4, 30))])
    assert not any("compare_series_needs_two_windows" in e for e in errs)


def test_validate_spec_resolves_raw_month_label_to_window():
    from engine.compile import validate_spec
    spec = Spec(intent="compare_periods", metric="revenue", subject="none",
                filters=[], time=["2026-05", "2026-04"], output="percent")
    windows = [_win("main", date(2026, 5, 1), date(2026, 5, 31)),
               _win("base", date(2026, 4, 1), date(2026, 4, 30))]
    errs = validate_spec(spec, _ctx(), windows)
    assert not any("time_label_unknown" in e for e in errs)
    assert spec.time == ["main", "base"]


def test_validate_spec_keeps_error_for_outside_label():
    from engine.compile import validate_spec
    spec = Spec(intent="compare_periods", metric="revenue", subject="none",
                filters=[], time=["2030-01"], output="percent")
    errs = validate_spec(spec, _ctx(), [_win("main", date(2026, 5, 1), date(2026, 5, 31))])
    assert any("time_label_unknown" in e for e in errs)


def test_validate_spec_rejects_unknown_time_label():
    from dtypes import BizContext
    from engine.compile import validate_spec

    class FakeCtx(BizContext):
        pass

    ctx = BizContext(con=None, archetype="A_flat", data_caps={"line_amount"},
                     views={"v_lines"}, date_min=date(2025, 1, 1),
                     date_max=date(2026, 1, 1), schema_conf=1.0, flags={},
                     status_invalid={}, value_dict={}, card="", entity_index=None,
                     rules=None, invariants={})
    spec = Spec(intent="aggregate_total", metric="revenue", subject="none",
                filters=[], time=["nope"], output="number")
    errs = validate_spec(spec, ctx, [])
    assert any("time_label_unknown" in e for e in errs)
