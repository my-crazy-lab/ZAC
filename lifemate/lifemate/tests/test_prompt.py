"""Test `prompt.py` — câu ràng buộc dùng id trong Gợi ý."""
from lifemate.prompt import build_messages
from lifemate.state_store import StateStore
from lifemate.datatypes import Hint, Hyp


def test_entity_hints_carry_binding_directive():
    hints = [Hint(kind="entity", span="xếp dũng", value="c_05", conf=0.85,
                  extra={"collection": "contacts", "name": "Sếp Dũng",
                         "tier": 4, "partial": False})]
    messages = build_messages(
        {}, [Hyp(text="nhắn xếp dũng", score=1.0)], [], hints, StateStore(),
        tools={}, transcript="nhắn xếp dũng")
    user_text = messages[1]["content"]
    assert "Gợi ý:" in user_text
    assert "c_05" in user_text
    assert "không tự đặt ID" in user_text


def test_no_hints_no_directive():
    messages = build_messages(
        {}, [Hyp(text="xin chào", score=1.0)], [], [], StateStore(),
        tools={}, transcript="xin chào")
    assert "không tự đặt ID" not in messages[1]["content"]
