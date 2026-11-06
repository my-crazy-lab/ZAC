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


def test_infer_output_concentration_is_not_percent():
    from engine.answer import infer_output
    q = nd("ngày 25/07/2025 cửa hàng bán otrivin 0,1% xịt mũi với đơn giá bnhiu một chai")
    assert infer_output(q, "aggregate_total", "price", "product") == "number"


def test_infer_output_real_percent_kept():
    from engine.answer import infer_output
    assert infer_output(nd("tỉ lệ huỷ đơn tháng 6 là nhiêu %"), "aggregate_total",
                        "revenue", "month") == "percent"
    assert infer_output(nd("doanh thu hơn hay kém cùng kỳ mấy %"), "compare_periods",
                        "revenue", "month") == "percent"


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


def _metrics(question: str) -> list[str]:
    from engine.answer import keyword_metrics
    from engine.semantics import preferred_metrics
    q = expand_abbrev(nd(question.lower()))
    pref = preferred_metrics(q)
    return pref + [m for m in keyword_metrics(q) if m not in pref]


def test_phieu_nhap_is_import_not_revenue():
    assert _metrics("tháng này tổng giá trị các phiếu nhập hàng là bao nhiêu")[0] == "import_amount"
    assert _metrics("coi gium thang 10/2025 nhap hang het bao nhieu tien")[0] == "import_amount"
    assert _metrics("thang 1/2025 cua hang bo ra bnhiu tien nhap hang")[0] == "import_amount"


def test_gia_nhap_binh_quan_thung_is_not_revenue():
    q = "Trong tháng 1/2025, Mì Omachi sườn hầm nhập vào giá bình quân một thùng là bao nhiêu"
    assert _metrics(q)[0] == "import_avg_price"


def test_doanh_thu_binh_quan_stays_aov():
    assert _metrics("Tuần trước doanh thu bình quân mỗi đơn là bao nhiêu")[0] == "aov"


def test_don_da_huy_is_cancelled_not_all_orders():
    assert _metrics("đếm số đơn đã huỷ trong tháng 12/2025")[0] == "cancelled_orders"
    assert _metrics("cửa hàng có mấy đơn ở trạng thái huỷ")[0] == "cancelled_orders"


def test_ranking_drops_time_subject():
    from engine.answer import subjects_for_intent
    subs = ["month", "product"]
    assert subjects_for_intent(subs, ["rank_top"]) == ["product"]
    assert subjects_for_intent(["month"], ["rank_top"]) == ["month"]
    assert subjects_for_intent(subs, ["aggregate_total"]) == subs


def test_ban_chay_maps_to_product_subject():
    subs = _subjects("tháng 3/2025 top 5 hàng bán chạy nhất là gì")
    assert "product" in subs


def test_cua_hang_is_not_product_subject():
    subs = _subjects("Tháng 12/2025 ngày nào cửa hàng bán được nhiều tiền nhất?")
    assert "product" not in subs
    assert subs[0] == "day"


def test_money_ranking_prefers_revenue_metric():
    from datetime import date
    from engine.answer import candidate_specs
    from dtypes import TimeWindow
    win = TimeWindow(label="main", start=date(2026, 1, 1), end=date(2026, 1, 31))
    q = expand_abbrev(nd("khách mua nhiều tiền nhất tháng 1/2026 là ai"))
    specs = candidate_specs(q, [win], [], None, {})
    assert specs and specs[0].metric == "revenue"
    assert specs[0].subject == "customer"


def test_formatter_maps_series_label_to_month():
    from datetime import date
    from fmt.formatter import _label_to_date
    from dtypes import TimeWindow
    wins = [TimeWindow(label="p2", start=date(2025, 12, 1), end=date(2025, 12, 31))]
    assert _label_to_date("p2", wins) == "2025-12"


def test_category_value_filter_from_dictionary():
    from engine.answer import filters_from
    vd = {"category": ["Thực phẩm", "Đồ uống", "Khác"]}
    f = filters_from([], vd, nd("nhóm thực phẩm tháng 7 bán được bao nhiêu tiền"))
    assert {"field": "category", "op": "=", "values": ["Thực phẩm"]} in f


def test_generic_category_value_not_filtered():
    from engine.answer import filters_from
    vd = {"category": ["Khác"]}
    f = filters_from([], vd, nd("các loại khác bán được bao nhiêu"))
    assert not any(x["field"] == "category" for x in f)


def test_matched_values_uses_mention_order_and_synonyms():
    from engine.answer import matched_values
    q = nd("doanh thu các đơn bán qua Zalo OA và doanh thu các đơn bán tại quầy")
    assert matched_values(q, ["phone", "store", "zalo_oa"]) == ["zalo_oa", "store"]


def test_multi_value_question_builds_list_spec():
    from datetime import date
    from engine.answer import candidate_specs
    from dtypes import TimeWindow
    win = TimeWindow(label="main", start=date(2026, 7, 1), end=date(2026, 7, 31))
    vd = {"channel": ["phone", "store", "zalo_oa"]}
    q = expand_abbrev(nd("doanh thu các đơn bán qua Zalo OA và tại quầy tháng 7/2025"))
    specs = candidate_specs(q, [win], [], None, vd)
    assert specs and specs[0].output == "list"
    assert specs[0].params.get("multi_field") == "channel"
    assert specs[0].params.get("multi_values") == ["zalo_oa", "store"]


def test_infer_check_direction():
    from engine.answer import infer_check
    assert infer_check(nd("doanh thu có tăng liên tục không")) == "series_increasing"
    assert infer_check(nd("doanh thu tháng sau có luôn cao hơn tháng trước không")) == "series_increasing"
    assert infer_check(nd("doanh thu có giảm liên tục không")) == "series_decreasing"
    assert infer_check(nd("tháng này có bán được hàng không")) == "exists"


def test_yes_no_question_expects_boolean():
    from decide.candidate_check import check_candidate, expect_kind
    from dtypes import Answer
    q = "doanh thu 3 tháng 4/2026, 5/2026, 6/2026 có tăng liên tục không"
    assert expect_kind(q) == "boolean"
    ok, reason = check_candidate(q, Answer(type="number", value=12345))
    assert not ok and reason == "boolean_q_badpred"
