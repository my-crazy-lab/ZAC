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


def test_unanswerable_string_not_blocked():
    ok, _ = check_candidate("cửa hàng có mấy khách ở đường Hai Bà Trưng",
                            _ans("number", 28021155100))
    assert not ok  # count-kind + số khổng lồ = chặn đúng
