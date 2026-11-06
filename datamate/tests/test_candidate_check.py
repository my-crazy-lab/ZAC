"""Test luật kiểm kiểu đáp án (decide/candidate_check)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from decide.candidate_check import check_candidate, expect_kind
from dtypes import Answer


def _ans(ptype, value):
    return Answer(type=ptype, value=value)


def test_percent_question_rejects_money():
    ok, reason = check_candidate("tỉ lệ huỷ đơn tháng 6 là nhiêu %", _ans("number", 397641500.0))
    assert not ok and reason == "percent_q_badpred"


def test_percent_question_accepts_rate():
    assert check_candidate("tỉ lệ huỷ đơn tháng 6 là nhiêu %", _ans("percent", 2.08))[0]
    assert check_candidate("tỉ lệ huỷ đơn tháng 6 là nhiêu %", _ans("number", 2.08))[0]


def test_concentration_is_not_percent_question():
    # "otrivin 0,1%" là nồng độ trong tên hàng; câu hỏi đơn giá (tiền)
    assert check_candidate(
        "ngày 25/07/2025 cửa hàng bán otrivin 0,1% xịt mũi với đơn giá bnhiu một chai",
        _ans("number", 58000))[0]


def test_percent_label_with_money_value_rejected():
    # engine gắn nhãn percent nhưng value là số tiền thô → phải chặn
    ok, reason = check_candidate(
        "nhóm tiêu hóa đóng góp bnhiu % doanh thu cả cửa hàng",
        _ans("percent", 360000.0))
    assert not ok and reason == "percent_q_badpred"
    ok, _ = check_candidate(
        "dthu đơn bán qua điện thoại bằng bnhiu % tổng doanh thu",
        _ans("percent", 397641500.0))
    assert not ok


def test_count_question_rejects_revenue():
    ok, reason = check_candidate("tháng 7 có bao nhiu đơn", _ans("number", 334591000.0))
    assert not ok and reason == "count_q_badpred"


def test_count_question_accepts_count():
    assert check_candidate("đếm số đơn đã huỷ trong tháng 12", _ans("number", 64.0))[0]


def test_money_question_not_treated_as_count():
    # "giá trị trung bình một đơn" là tiền, không phải đếm — không được chặn
    assert check_candidate(
        "giá trị trung bình một đơn tháng 4 là bao nhiêu", _ans("number", 1368446))[0]


def test_who_question_not_treated_as_count():
    assert check_candidate(
        "Tuần rồi khách nào mua nhiều tiền nhất?", _ans("string", "Lâm Hoa Long"))[0]


def test_date_question_rejects_name():
    ok, reason = check_candidate(
        "xem giúp ngày nào trong tháng 2 dthu cao nhất", _ans("string", "Cao Hạnh Thu"))
    assert not ok and reason == "date_q_badpred"


def test_date_pred_on_number_question_rejected():
    ok, _ = check_candidate("cho tôi biết dthu 30 ngày gần nhất", _ans("date", "2025-02-08"))
    assert not ok


def test_list_question_rejects_single_number():
    ok, reason = check_candidate(
        "dthu 3 tháng liền nhau kết thúc ở tháng 12 là bao nhiêu mỗi tháng?",
        _ans("number", 158205600))
    assert not ok and reason == "list_q_badpred"


def test_single_best_is_not_list():
    # "hàng nào bán chạy nhất" đáp 1 món (string) — không phải list
    assert expect_kind("tháng 5 hàng nào bán chạy nhất") == "other"


def test_count_with_revenue_filter():
    # "đơn có dthu từ 55k trở lên" là đếm đơn, đáp tổng tiền phải chặn
    ok, reason = check_candidate(
        "tháng 7 có bao nhiu đơn có dthu từ 55.000 trở lên", _ans("number", 334591000.0))
    assert not ok and reason == "count_q_badpred"


def test_count_days_with_revenue():
    ok, _ = check_candidate(
        "Tháng 6 có mấy ngày doanh thu đạt 9.800.000 trở lên?", _ans("number", 298394000.0))
    assert not ok


def test_count_units_ly_dia_cuc():
    assert not check_candidate("bán được mấy ly Cà phê sữa (L)?", _ans("number", 4441000))[0]
    assert not check_candidate("bán được mấy đĩa rau cần xào tỏi", _ans("number", 6809000))[0]
    assert not check_candidate("bán ra bao nhiu cục xà bông", _ans("number", 2735000))[0]
    assert check_candidate("bán được mấy ly Cà phê sữa (L)?", _ans("number", 176.0))[0]


def test_count_slow_items():
    ok, _ = check_candidate(
        "từ 20/10 đến hết 26/10, bao nhiêu mặt hàng bị ế nhỉ?", _ans("number", 16560222900))
    assert not ok


def test_money_weak_form_not_count():
    # "mặt hàng X thu về bao nhiêu tiền" là tiền — không được chặn
    assert check_candidate(
        "mặt hàng Thuốc lá Vinataba thu về bao nhiêu tiền",
        _ans("number", 10006000))[0]


def test_money_total_today_not_count():
    assert check_candidate(
        "tổng dthu trong ngày hôm nay là bao nhiêu", _ans("number", 39793500))[0]
    assert check_candidate("Doanh thu tháng 4/2026 bao nhiêu?", _ans("number", 1380833500))[0]
    assert check_candidate("revenue hôm nay là bao nhiêu", _ans("number", 11111900))[0]


def test_unanswerable_string_not_blocked():
    ok, _ = check_candidate("cửa hàng có mấy khách ở đường Hai Bà Trưng",
                            _ans("number", 28021155100))
    assert not ok  # count-kind + số khổng lồ = chặn đúng
