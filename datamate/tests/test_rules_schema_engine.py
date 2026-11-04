"""Test cho M3/M4/M5: rulebook parser, mapper, sandbox, compiler."""

from __future__ import annotations

from datetime import date

import pytest

from dtypes import Spec
from engine.sandbox import SqlRejected, check_sql
from rules.rulebook_parser import parse_rulebook
from schema.mapper import parse_readme

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


def test_sandbox_rejects_write():
    with pytest.raises(SqlRejected):
        check_sql("DELETE FROM v_orders")
    with pytest.raises(SqlRejected):
        check_sql("SELECT 1; DROP TABLE v_orders")


def test_sandbox_allows_select():
    check_sql("SELECT 1 FROM v_orders WHERE order_date <= DATE '2026-01-01'")


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
