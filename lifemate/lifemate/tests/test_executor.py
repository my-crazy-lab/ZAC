"""Test `executor.py` (EXECUTION-PLAN.md §9.3) — 6 ca bắt buộc."""
import json

from lifemate import config
from lifemate.executor import ExecState, run_plan
from lifemate.state_store import StateStore
from lifemate.datatypes import Call, Deadline


class FakeEnv:
    def __init__(self):
        self.calls = []

    def validate(self, name, args=None):
        return {"ok": True, "error": None}

    def call(self, name, args=None):
        self.calls.append({"name": name, "arguments": dict(args or {})})
        if name == "contacts.search":
            return {"ok": True, "contacts": [{"id": "c_01", "name": "Lan"}]}
        return {"ok": True}


class FakeLLM:
    """Kịch bản theo lượt: mỗi phần tử là (calls, text)."""

    def __init__(self, script):
        self.script = list(script)
        self.turn = 0

    @property
    def available(self):
        return True

    def generate(self, messages, tools=None, max_tokens=512, log=None):
        idx = min(self.turn, len(self.script) - 1)
        self.turn += 1
        entry = self.script[idx]
        if callable(entry):
            calls, text = entry(self.turn)
        else:
            calls, text = entry
        return list(calls), text, {}


def _tools():
    from lifemate.datatypes import Tool
    return {
        "contacts.search": Tool(name="contacts.search", app="contacts", kind="read", description="tìm",
                                app_name_vi="", app_description="", returns="contacts[]", parameters={},
                                required=[], props={}, one_of=[]),
        "banking.transfer": Tool(
            name="banking.transfer", app="banking", kind="write", description="chuyển",
            app_name_vi="", app_description="", returns="", parameters={},
            required=["contact_id", "amount"],
            props={"contact_id": {"type": "string", "x-ref": "contacts.contacts"},
                   "amount": {"type": "integer"}},
            one_of=[]),
        "alarm.create": Tool(name="alarm.create", app="alarm", kind="write", description="tạo",
                              app_name_vi="", app_description="", returns="", parameters={},
                              required=["time"], props={"time": {"type": "string"}}, one_of=[]),
        "sys.ask_missing_info": Tool(name="sys.ask_missing_info", app="sys", kind="meta",
                                      description="hỏi", app_name_vi="", app_description="",
                                      returns="", parameters={}, required=["tool_name", "params"],
                                      props={"tool_name": {"type": "string"},
                                             "params": {"type": "array", "items": {"type": "string"}}},
                                      one_of=[]),
    }


def _run(env, llm, tools=None, transcript="chuyển tiền cho Lan", store=None, state=None):
    tools = tools or _tools()
    store = store or StateStore()
    messages = [{"role": "user", "content": transcript}]
    state = state or ExecState()
    run_plan(env, llm, tools, messages, store, {}, transcript, lambda: [],
             Deadline(60), None, state=state, ref_sources={})
    return env.calls, state


def test_1_read_then_write_both_executed():
    llm = FakeLLM([
        ([Call("contacts.search", {"query": "Lan"})], ""),
        ([Call("banking.transfer", {"contact_id": "c_01", "amount": 100})], "XONG"),
    ])
    env = FakeEnv()
    calls, _ = _run(env, llm)
    assert [c["name"] for c in calls] == ["contacts.search", "banking.transfer"]
    assert calls[1]["arguments"]["contact_id"] == "c_01"


def test_2_write_with_unverified_id_is_deferred_then_nudged():
    llm = FakeLLM([
        ([Call("banking.transfer", {"contact_id": "c_99", "amount": 100})], ""),
        ([Call("contacts.search", {"query": "Lan"}),
          Call("banking.transfer", {"contact_id": "c_01", "amount": 100})], "XONG"),
    ])
    env = FakeEnv()
    calls, state = _run(env, llm)
    assert state.nudges_used == 1
    assert [c["name"] for c in calls] == ["contacts.search", "banking.transfer"]


def test_3_write_then_ask_order():
    tools = _tools()
    llm = FakeLLM([
        ([Call("alarm.create", {"time": "2026-11-17T07:00:00+07:00"})], ""),
        ([Call("sys.ask_missing_info", {"tool_name": "banking.transfer", "params": ["contact_id"]})], ""),
    ])
    env = FakeEnv()
    calls, _ = _run(env, llm, tools=tools)
    assert [c["name"] for c in calls] == ["alarm.create", "sys.ask_missing_info"]


def test_4_silent_is_nudged_once_then_empty():
    llm = FakeLLM([([], "")])
    env = FakeEnv()
    calls, _ = _run(env, llm)
    assert calls == []
    assert llm.turn == 2  # 1 lượt im lặng + 1 lần nhắc


def test_5_max_turns_stops_the_loop():
    old = config.MAX_TURNS
    config.MAX_TURNS = 2
    try:
        def script(turn):
            return ([Call("alarm.create", {"time": f"2026-11-17T0{turn}:00:00+07:00"})], "")

        llm = FakeLLM([script])
        env = FakeEnv()
        calls, _ = _run(env, llm)
        assert len(calls) == 2
        assert llm.turn == 2
    finally:
        config.MAX_TURNS = old


def test_7_turn2_messages_carry_fresh_entity_hints():
    from datetime import datetime
    from lifemate.resolver import build_hints
    from lifemate.datatypes import Hyp

    transcript = "chuyển tiền cho Lan"
    seen = []

    class RecLLM(FakeLLM):
        def generate(self, messages, tools=None, max_tokens=512, log=None):
            seen.append(list(messages))
            return super().generate(messages, tools, max_tokens, log=log)

    llm = RecLLM([
        ([Call("contacts.search", {"query": "Lan"})], ""),
        ([], "XONG"),
    ])
    env = FakeEnv()
    store = StateStore()
    hints_fn = lambda: build_hints([Hyp(text=transcript, score=1.0)], store, datetime.now())
    run_plan(env, llm, _tools(), [{"role": "user", "content": transcript}],
             store, {}, transcript, hints_fn, Deadline(60), None,
             state=ExecState(), ref_sources={})
    turn2_user_texts = [m.get("content", "") for m in seen[1] if m.get("role") == "user"]
    assert any("Gợi ý (cập nhật)" in t and "c_01" in t for t in turn2_user_texts)


def test_6_repeated_write_dropped_unless_repeat_marker():
    tools = _tools()
    llm = FakeLLM([
        ([Call("alarm.create", {"time": "2026-11-17T07:00:00+07:00"})], ""),
        ([Call("alarm.create", {"time": "2026-11-17T07:00:00+07:00"})], ""),
    ])
    env = FakeEnv()
    calls, _ = _run(env, llm, tools=tools, transcript="đặt báo thức")
    assert len(calls) == 1

    llm2 = FakeLLM([
        ([Call("alarm.create", {"time": "2026-11-17T07:00:00+07:00"})], ""),
        ([Call("alarm.create", {"time": "2026-11-17T07:00:00+07:00"})], ""),
    ])
    env2 = FakeEnv()
    calls2, _ = _run(env2, llm2, tools=tools, transcript="đặt thêm một báo thức nữa")
    # có từ "thêm" ⇒ lệnh ghi lặp không bị bỏ
    assert len(calls2) >= 2
