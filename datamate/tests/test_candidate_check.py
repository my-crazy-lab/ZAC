from types import SimpleNamespace

from decide.candidate_check import check_candidate


def test_rejects_nonempty_type_with_none_value():
    ok, reason = check_candidate("doanh thu hôm qua", SimpleNamespace(type="number", value=None))
    assert not ok and reason == "empty_candidate_value"


def test_rejects_empty_list_item():
    ok, reason = check_candidate("top 3 sản phẩm", SimpleNamespace(type="list", value=[""]))
    assert not ok and reason == "empty_list_item"
