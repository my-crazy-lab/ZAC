"""Test cho ánh xạ chủ thể từ từ hỏi (ai / hàng nào)."""

from __future__ import annotations

from engine.answer import keyword_subjects
from text.normalize import expand_abbrev, nd


def _subjects(question: str) -> list[str]:
    return keyword_subjects(expand_abbrev(nd(question.lower())), False, False)


def test_ai_maps_to_customer_not_month():
    subs = _subjects("Tháng 6/2025 ai mua hàng nhiều tiền nhất?")
    assert subs[0] == "customer"


def test_hang_nao_maps_to_product_not_month():
    subs = _subjects("thang 6/2025 hang nao chay nhat")
    assert subs[0] == "product"


def test_thang_nao_does_not_trigger_product():
    subs = _subjects("thang nao doanh thu cao nhat trong ba thang?")
    assert "product" not in subs
    assert "month" in subs


def test_ngay_mai_does_not_trigger_customer():
    subs = _subjects("ngay mai cua hang co mo cua khong?")
    assert "customer" not in subs
