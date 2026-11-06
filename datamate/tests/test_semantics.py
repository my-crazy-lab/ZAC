"""Test so khớp ngữ nghĩa câu hỏi ↔ metric."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.semantics import metric_compatible, preferred_metrics, topic_domains
from text.normalize import expand_abbrev, nd


def _q(question: str) -> str:
    return expand_abbrev(nd(question))


def test_purchase_topic_detected():
    assert topic_domains(_q("tháng này tổng giá trị các phiếu nhập hàng là bao nhiêu")) == {"purchase"}
    assert topic_domains(_q("tháng 3/2026 nhập hàng hết bao nhiêu tiền")) == {"purchase"}


def test_inventory_topic_detected():
    assert topic_domains(_q("tồn kho của mặt hàng này là bao nhiêu")) == {"inventory"}


def test_debt_topic_detected():
    assert topic_domains(_q("tổng công nợ của khách hàng tháng này")) == {"debt"}


def test_purchase_question_rejects_revenue():
    q = _q("tổng giá trị các phiếu nhập hàng tháng này là bao nhiêu")
    ok, reason = metric_compatible(q, "revenue")
    assert not ok and reason.startswith("domain_mismatch")
    assert metric_compatible(q, "import_amount")[0]


def test_inventory_question_rejects_revenue():
    q = _q("giá trị hàng tồn kho hiện tại là bao nhiêu")
    assert not metric_compatible(q, "revenue")[0]
    assert metric_compatible(q, "stock_value")[0]


def test_debt_question_rejects_revenue():
    q = _q("còn nợ của khách hàng này là bao nhiêu")
    assert not metric_compatible(q, "revenue")[0]
    assert metric_compatible(q, "debt")[0]


def test_cancel_count_question_requires_cancel_metric():
    q = _q("đếm số đơn đã huỷ trong tháng 9/2025")
    assert not metric_compatible(q, "orders")[0]
    assert metric_compatible(q, "cancelled_orders")[0]


def test_cancel_rate_question_requires_rate_metric():
    q = _q("tỉ lệ đơn huỷ trong tháng 7 là bao nhiêu %")
    assert not metric_compatible(q, "cancelled_orders", "number")[0]
    assert metric_compatible(q, "cancelled_orders", "percent")[0]
    assert metric_compatible(q, "cancel_rate", "percent")[0]


def test_metric_needing_entity_rejected_without_entity():
    q = _q("giá bán của mặt hàng này hôm nay là bao nhiêu")
    assert not metric_compatible(q, "price", has_entity=False)[0]
    assert metric_compatible(q, "price", has_entity=True)[0]
    q2 = _q("giá nhập bình quân một thùng là bao nhiêu")
    assert not metric_compatible(q2, "import_avg_price", has_entity=False)[0]


def test_plain_sales_question_unaffected():
    q = _q("doanh thu tháng 6 là bao nhiêu")
    assert metric_compatible(q, "revenue")[0]
    assert preferred_metrics(q) == []


def test_sales_only_question_stays_sales():
    q = _q("tháng này bán được bao nhiêu tiền")
    assert topic_domains(q) == set()
    assert metric_compatible(q, "revenue")[0]
