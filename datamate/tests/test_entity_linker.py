"""Test độ chính xác của khớp thực thể (schema/entity linking)."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from text.entity_linker import EntityIndex, link_entities
from text.normalize import nd


def _index() -> EntityIndex:
    idx = EntityIndex()
    idx.add("customer", "Đào Bích Huy", "KH0004")
    idx.add("customer", "Kiều Long Đức", "KH0001")
    idx.add("product", "Mì Omachi sườn hầm", "SP001")
    idx.add("product", "Sting dâu 330ml", "SP002")
    return idx


def _links(question: str) -> list:
    return link_entities(nd(question), _index())


def test_business_phrase_not_linked_to_customer_name():
    # "đã huỷ" không phải khách "Đào Bích Huy"
    assert _links("Đếm số đơn đã huỷ trong tháng 9/2025.") == []


def test_single_business_word_not_linked_as_name():
    assert _links("tháng 9 có bao nhiêu đơn huỷ") == []


def test_exact_customer_name_still_links():
    links = _links("tháng 9 khách Đào Bích Huy mua bao nhiêu")
    assert any(e.kind == "customer" and e.code == "KH0004" for e in links)


def test_exact_product_name_still_links():
    links = _links("tháng 9 bán được bao nhiêu Mì Omachi sườn hầm")
    assert any(e.kind == "product" and e.code == "SP001" for e in links)


def test_partial_short_tokens_do_not_link():
    # "omachi" một token không đủ phủ tên 4 token
    links = _links("tháng 9 bán được bao nhiêu omachi")
    assert not any(e.kind == "product" for e in links)
