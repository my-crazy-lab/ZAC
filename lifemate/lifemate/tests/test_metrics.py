"""Test `eval/metrics.py` (EXECUTION-PLAN.md §9.1)."""
from lifemate.eval import metrics as M


def test_f1_multiset_same_name_different_args():
    gold = [{"name": "sms.send", "arguments": {"content": "a", "contact_id": "c_01"}}]
    pred = [{"name": "sms.send", "arguments": {"content": "b", "contact_id": "c_02"}}]
    res = M.f1_call(pred, gold, "strict")
    assert res["tp"] == 0
    assert res["f1"] == 0.0
    res_soft = M.f1_call(pred, gold, "soft")
    assert res_soft["f1"] == 1.0


def test_both_empty_is_one():
    assert M.f1_call([], [], "strict")["f1"] == 1.0


def test_ask_matched_by_param_set():
    gold = [{"name": "sys.ask_missing_info", "arguments": {"tool_name": "sms.send", "params": ["contact_id", "content"]}}]
    pred = [{"name": "sys.ask_missing_info", "arguments": {"tool_name": "sms.send", "params": ["content", "contact_id"]}}]
    assert M.f1_call(pred, gold, "strict")["f1"] == 1.0
    other = [{"name": "sys.ask_missing_info", "arguments": {"tool_name": "sms.send", "params": ["content"]}}]
    assert M.f1_call(other, gold, "strict")["f1"] == 0.0


def test_fuzzy_token_f1():
    fuzzy = {"sms.send": {"content"}}
    gold = [{"name": "sms.send", "arguments": {"content": "mai chạy bộ dời sang 09:00 nhé"}}]
    pred = [{"name": "sms.send", "arguments": {"content": "mai chạy bộ dời sang 09:00 nhé với Lan"}}]
    assert M.f1_call(pred, gold, "fuzzy-aware", fuzzy)["f1"] > 0.8
    strict = M.f1_call(pred, gold, "strict", fuzzy)
    assert strict["f1"] == 0.0


def test_number_equals_float():
    gold = [{"name": "banking.transfer", "arguments": {"amount": 500000}}]
    pred = [{"name": "banking.transfer", "arguments": {"amount": 500000.0}}]
    assert M.f1_call(pred, gold, "strict")["f1"] == 1.0
