"""Test tích hợp `agent.py` (luồng: scope → prefetch → prompt → plan → gate → execute)."""
import json
import os
import tempfile

from lifemate import config
from lifemate.agent import Agent
from lifemate.catalog import Catalog
from lifemate.datatypes import Call, Deadline, Hyp

CATALOG = {
    "apps": [
        {
            "id": "contacts",
            "name_vi": "Danh bạ",
            "description": "Tìm danh bạ",
            "tools": [
                {"name": "contacts.search", "kind": "read", "description": "Tìm liên hệ theo tên",
                 "parameters": {"type": "object",
                                "properties": {"query": {"type": "string", "x-match": "fuzzy"}},
                                "required": ["query"]},
                 "returns": "contacts[]", "app": "contacts"},
            ],
        },
        {
            "id": "sms",
            "name_vi": "Tin nhắn",
            "description": "Gửi tin nhắn",
            "tools": [
                {"name": "sms.send", "kind": "write", "description": "Gửi tin nhắn cho liên hệ",
                 "parameters": {"type": "object",
                                "properties": {
                                    "contact_id": {"type": "string", "x-ref": "contacts.contacts"},
                                    "content": {"type": "string", "x-match": "fuzzy"}},
                                "required": ["content"],
                                "x-one-of": [["contact_id"], ["phone_number"]]},
                 "returns": "message", "app": "sms"},
            ],
        },
        {
            "id": "sys",
            "name_vi": "Hệ thống",
            "description": "",
            "tools": [
                {"name": "sys.ask_missing_info", "kind": "meta", "description": "Hỏi tham số thiếu",
                 "parameters": {"type": "object",
                                "properties": {"tool_name": {"type": "string"},
                                               "params": {"type": "array", "items": {"type": "string"}}},
                                "required": ["tool_name", "params"]},
                 "returns": "", "app": "sys"},
            ],
        },
    ]
}


class FakeEnv:
    def __init__(self):
        self.calls = []

    def validate(self, name, args=None):
        return {"ok": True, "error": None}

    def call(self, name, args=None):
        self.calls.append({"name": name, "arguments": dict(args or {})})
        if name == "contacts.search":
            return {"ok": True, "contacts": [{"id": "c_01", "name": "Lan"}]}
        return {"ok": True, "message": {"id": "msg_01"}}


class FakeLLM:
    def __init__(self, script, answer="CO"):
        self.script = list(script)
        self.answer = answer
        self.turn = 0
        self.messages = []

    @property
    def available(self):
        return True

    def generate(self, messages, tools=None, max_tokens=512, log=None):
        self.messages = messages
        if self.answer:
            return [], self.answer, {}
        idx = min(self.turn, len(self.script) - 1)
        self.turn += 1
        calls, text = self.script[idx]
        return list(calls), text, {}


def _catalog():
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(CATALOG, f, ensure_ascii=False)
    return Catalog(path)


def _item(text="gửi tin cho Lan"):
    return {
        "id": "train_0001",
        "audio_text": text,
        "label": {"audio_text": text, "tool_calls": []},
        "context": {
            "current_time": "2026-11-16T17:00:00+07:00",
            "timezone": "Asia/Ho_Chi_Minh",
            "location": {"lat": 16.0544, "lng": 108.2022},
            "user_profile": {"name": "Linh", "home_address": "88 Nguyễn Văn Linh"},
            "installed_apps": {"contacts": {"tools": ["contacts.search"]},
                               "sms": {"tools": ["sms.send"]}},
        },
        "history": [],
    }


def test_agent_reads_then_writes():
    llm = FakeLLM([
        ([Call("contacts.search", {"query": "Lan"})], ""),
        ([Call("sms.send", {"contact_id": "c_01", "content": "chào Lan"})], "XONG"),
    ], answer=None)
    agent = Agent(_catalog(), llm)
    env = FakeEnv()
    debug = agent.run(_item(), env, None, Deadline(30), [])
    assert [c["name"] for c in env.calls] == ["contacts.search", "sms.send"]
    assert env.calls[1]["arguments"]["contact_id"] == "c_01"
    assert debug["scope"]["decision"].startswith("in_scope")
    assert debug["executed"]


def test_agent_out_of_scope_calls_nothing():
    llm = FakeLLM([], answer="KHONG")
    agent = Agent(_catalog(), llm)
    env = FakeEnv()
    debug = agent.run(_item("mua vé máy bay đi hà nội"), env, None, Deadline(30), [])
    assert env.calls == []
    assert debug["scope"]["decision"] == "out_of_scope"


def test_agent_prompt_contains_required_sections():
    llm = FakeLLM([([], "XONG")], answer=None)
    agent = Agent(_catalog(), llm)
    env = FakeEnv()
    agent.run(_item("gửi tin cho Lan lúc 5 giờ chiều mai"), env, None, Deadline(30), [])
    text = llm.messages[-1]["content"]
    assert "Thời gian hiện tại" in text
    assert "Hồ sơ" in text
    assert "Yêu cầu" in text
    assert "Gợi ý" in text
    assert "GIỜ" in text
