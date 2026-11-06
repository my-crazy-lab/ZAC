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


def test_infer_limit_explicit_count_beats_nhat():
    from engine.answer import infer_limit
    assert infer_limit("3 mat hang ban chay nhat tuan nay la nhung mat hang nao") == 3
    assert infer_limit("liet ke 3 khach chi tieu nhieu nhat") == 3
    assert infer_limit("cho tooi 5 khach mua nhiu tien nhat") == 5
    assert infer_limit("top 5 hang ban chay") == 5


def test_infer_limit_ignores_time_and_thresholds():
    from engine.answer import infer_limit
    assert infer_limit("dthu 3 thang lien nhau ket thuc o thang 12/2025") is None
    assert infer_limit("khach mua tu 3 don tro len chiem bao nhieu %") is None
    assert infer_limit("thang nao ban dat nhat") == 1


def test_thang_nao_does_not_trigger_product():
    subs = _subjects("thang nao doanh thu cao nhat trong ba thang?")
    assert "product" not in subs
    assert "month" in subs


def test_ngay_mai_does_not_trigger_customer():
    subs = _subjects("ngay mai cua hang co mo cua khong?")
    assert "customer" not in subs
