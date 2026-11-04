"""Test `llm.py` (EXECUTION-PLAN.md §8.10)."""
from lifemate.llm import parse_tool_calls, parse_tool_calls_text


def test_parse_structured_tool_calls():
    message = {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {"id": "call_1", "type": "function",
             "function": {"name": "sms.send", "arguments": '{"content": "hi", "contact_id": "c_01"}'}},
        ],
    }
    calls = parse_tool_calls(message)
    assert len(calls) == 1
    assert calls[0].name == "sms.send"
    assert calls[0].args == {"content": "hi", "contact_id": "c_01"}
    assert calls[0].call_id == "call_1"


def test_parse_text_tool_call():
    text = '<tool_call>{"name": "sms.send", "arguments": {"content": "hi"}}</tool_call>'
    calls = parse_tool_calls_text(text)
    assert len(calls) == 1
    assert calls[0].name == "sms.send"
    assert calls[0].args == {"content": "hi"}


def test_broken_json_gives_empty():
    text = '<tool_call>{"name": "sms.send", "arguments": {oops}}</tool_call>'
    assert parse_tool_calls_text(text) == []
    message = {"tool_calls": [{"id": "x", "function": {"name": "a.b", "arguments": "{oops"}}]}
    assert parse_tool_calls(message) == []
