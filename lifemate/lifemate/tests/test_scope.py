"""Test `scope.py` (EXECUTION-PLAN.md §8.13)."""
import json
import os
import tempfile

from lifemate import config
from lifemate.catalog import Catalog
from lifemate.scope import in_scope
from lifemate.datatypes import Hyp

FAKE = {
    "apps": [
        {
            "id": "ride",
            "name_vi": "Đặt xe",
            "description": "Đặt xe máy và xe ô tô, đón trả khách",
            "tools": [
                {"name": "ride.book", "kind": "write", "description": "Đặt xe đón khách tại địa chỉ",
                 "parameters": {"type": "object", "properties": {"to": {"type": "string"}},
                                "required": ["to"]},
                 "returns": "", "app": "ride"},
            ],
        },
        {
            "id": "weather",
            "name_vi": "Thời tiết",
            "description": "Xem thời tiết dự báo hôm nay và ngày mai",
            "tools": [
                {"name": "weather.get_forecast", "kind": "read",
                 "description": "Dự báo thời tiết theo ngày",
                 "parameters": {"type": "object", "properties": {}, "required": []},
                 "returns": "forecast[]", "app": "weather"},
            ],
        },
    ]
}


class FakeLLM:
    def __init__(self, answer):
        self.answer = answer
        self.called = 0

    @property
    def available(self):
        return True

    def generate(self, messages, tools=None, max_tokens=512, log=None):
        self.called += 1
        return [], self.answer, {}


def _catalog():
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(FAKE, f, ensure_ascii=False)
    return Catalog(path)


def test_in_scope_without_llm():
    cat = _catalog()
    installed = {"ride": {"tools": ["ride.book"]}}
    tools = cat.tools_for(installed)
    llm = FakeLLM("KHONG")
    ok, dbg = in_scope(llm, [Hyp("đặt xe về nhà cho tôi", 1.0)], tools, cat.all_tools(), {}, None)
    assert ok is True
    assert llm.called == 0          # ratio cao ⇒ bỏ qua LLM


def test_out_of_scope_ratio_is_low():
    cat = _catalog()
    installed = {"ride": {"tools": ["ride.book"]}}
    tools = cat.tools_for(installed)
    llm = FakeLLM("KHONG")
    ok, dbg = in_scope(llm, [Hyp("thời tiết ngày mai thế nào", 1.0)], tools, cat.all_tools(), {}, None)
    assert dbg["ratio"] < config.SCOPE_RATIO_THRESHOLD
    assert ok is False


def test_llm_says_khong_and_ratio_low_is_out_of_scope():
    cat = _catalog()
    installed = {"ride": {"tools": ["ride.book"]}}
    tools = cat.tools_for(installed)
    llm = FakeLLM("KHONG")
    ok, dbg = in_scope(llm, [Hyp("kể cho tôi nghe câu chuyện vui hôm nay", 1.0)], tools,
                       cat.all_tools(), {}, None)
    assert dbg["ratio"] < config.SCOPE_RATIO_THRESHOLD
    assert ok is False


def test_llm_says_co_is_in_scope():
    cat = _catalog()
    installed = {"ride": {"tools": ["ride.book"]}}
    tools = cat.tools_for(installed)
    ok, dbg = in_scope(FakeLLM("CO"), [Hyp("mua vé máy bay đi hà nội", 1.0)], tools,
                       cat.all_tools(), {}, None)
    assert ok is True
