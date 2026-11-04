"""Test cho M0: chấm điểm theo rulebook §9."""

from __future__ import annotations

from decimal import Decimal

from dtypes import Answer
from fmt.compare import canon_key, is_correct, norm_number, norm_text


def test_norm_text_keeps_diacritics():
    assert norm_text("Cà phê  Sữa!") == "cà phê sữa"
    assert norm_text("Bàn chải") != norm_text("Ban chai")


def test_norm_number_money_rounds_half_up():
    assert norm_number(1000.5, is_money=True) == Decimal("1001")
    assert norm_number(1000.4, is_money=True) == Decimal("1000")
    assert norm_number(12.345, is_money=False) == Decimal("12.35")


def test_number_money_rounds_to_dong():
    """Tiền làm tròn từng đồng (nửa đồng làm tròn lên) — 4820000.4 ⇒ 4820000."""
    ref = {"type": "number", "answer": 4820000, "alias": []}
    assert is_correct(Answer(type="number", value=4820000), ref)
    assert is_correct(Answer(type="number", value=4820000.0), ref)
    assert is_correct(Answer(type="number", value=4820000.4), ref)
    assert not is_correct(Answer(type="number", value=4820001), ref)


def test_number_string_is_wrong():
    ref = {"type": "number", "answer": 4820000, "alias": []}
    assert not is_correct(Answer(type="number", value="4.820.000"), ref)


def test_percent_exact():
    ref = {"type": "percent", "answer": 12.34, "alias": []}
    assert is_correct(Answer(type="percent", value=12.34), ref)
    assert not is_correct(Answer(type="percent", value=12.35), ref)


def test_string_alias():
    ref = {"type": "string", "answer": "Cà phê sữa", "alias": ["ca phe sua"]}
    assert is_correct(Answer(type="string", value="ca phe sua"), ref)
    assert is_correct(Answer(type="string", value="Cà phê sữa"), ref)


def test_list_order_matters():
    ref = {"type": "list", "answer": ["a", "b"], "alias": []}
    assert is_correct(Answer(type="list", value=["a", "b"]), ref)
    assert not is_correct(Answer(type="list", value=["b", "a"]), ref)


def test_unanswerable_only_when_null():
    ref = {"type": "unanswerable", "answer": None, "alias": []}
    assert is_correct(Answer(type="unanswerable"), ref)
    assert not is_correct(Answer(type="number", value=1), ref)


def test_abstain_never_correct():
    ref = {"type": "number", "answer": 5, "alias": []}
    assert not is_correct(Answer(type="abstain"), ref)


def test_table_ignores_column_names():
    ref = {"type": "table", "answer": {"columns": ["a"], "rows": [[1]]}, "alias": []}
    pred = Answer(type="table", value={"columns": ["x"], "rows": [[1]]})
    assert is_correct(pred, ref)


def test_canon_key_groups_equivalent():
    a = Answer(type="number", value=4820000)
    b = Answer(type="number", value=4820000.0)
    assert canon_key(a) == canon_key(b)
