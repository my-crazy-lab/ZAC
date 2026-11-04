"""Test `catalog.py` (EXECUTION-PLAN.md §8.4)."""
import json
import os
import tempfile

from lifemate.catalog import Catalog, readers_for, resolve_tool_name, to_llm_tools

FAKE = {
    "schema_version": "1.0",
    "apps": [
        {
            "id": "contacts",
            "name_vi": "Danh bạ",
            "description": "Quản lý danh bạ",
            "tools": [
                {
                    "name": "contacts.search",
                    "kind": "read",
                    "description": "Tìm liên hệ theo tên",
                    "parameters": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"],
                    },
                    "returns": "contacts[]",
                    "app": "contacts",
                },
                {
                    "name": "contacts.get",
                    "kind": "read",
                    "description": "Lấy một liên hệ",
                    "parameters": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]},
                    "returns": "contact",
                    "app": "contacts",
                },
                {
                    "name": "sms.send",
                    "kind": "write",
                    "description": "Gửi tin nhắn",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "contact_id": {"type": "string", "x-ref": "contacts.contacts"},
                            "content": {"type": "string", "x-match": "fuzzy"},
                        },
                        "required": ["content"],
                        "x-one-of": [["contact_id"], ["phone_number"]],
                    },
                    "returns": "message",
                    "app": "sms",
                },
            ],
        },
        {
            "id": "sms",
            "name_vi": "Tin nhắn",
            "description": "Gửi/nhận tin",
            "tools": [
                {
                    "name": "sms.read_recent",
                    "kind": "read",
                    "description": "Đọc tin gần đây",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                    "returns": "messages[]",
                    "app": "sms",
                }
            ],
        },
        {
            "id": "sys",
            "name_vi": "Hệ thống",
            "description": "Tool hệ thống",
            "tools": [
                {
                    "name": "sys.ask_missing_info",
                    "kind": "meta",
                    "description": "Hỏi tham số thiếu",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "tool_name": {"type": "string"},
                            "params": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["tool_name", "params"],
                    },
                    "returns": "",
                    "app": "sys",
                }
            ],
        },
    ],
}


def _make_catalog():
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(FAKE, f, ensure_ascii=False)
    return Catalog(path)


def test_tools_for_filters_app_and_tool_list():
    cat = _make_catalog()
    tools = cat.tools_for({"contacts": {"tools": ["contacts.search"]}, "sms": {"tools": []}})
    assert "contacts.search" in tools
    assert "contacts.get" not in tools
    assert "sms.read_recent" in tools          # danh sách rỗng ⇒ mọi tool của app
    assert "sys.ask_missing_info" in tools     # luôn có


def test_one_of_normalized():
    cat = _make_catalog()
    tool = cat.all_tools()["sms.send"]
    assert tool.one_of == [["contact_id"], ["phone_number"]]


def test_to_llm_tools_strips_x_keys_and_annotates():
    cat = _make_catalog()
    tools = cat.tools_for({"sms": {"tools": []}})
    out = to_llm_tools(tools)
    sms = [t for t in out if t["function"]["name"] == "sms.send"][0]
    props = sms["function"]["parameters"]["properties"]
    assert "x-ref" not in props["contact_id"]
    assert "x-match" not in props["content"]
    assert "ID phải lấy từ dữ liệu" in props["contact_id"]["description"]
    assert "văn bản tự do" in props["content"]["description"]
    assert "x-one-of" not in sms["function"]["parameters"]
    assert "Cần ít nhất một trong" in sms["function"]["description"]


def test_resolve_tool_name_variants():
    cat = _make_catalog()
    tools = cat.all_tools()
    assert resolve_tool_name("sms.send", tools) == "sms.send"
    assert resolve_tool_name("sms__send", tools) == "sms.send"
    assert resolve_tool_name("sms/send", tools) == "sms.send"
    assert resolve_tool_name("sms.sen", tools) == "sms.send"
    assert resolve_tool_name("khong.co.tool", tools) is None


def test_readers_for_contacts():
    cat = _make_catalog()
    tools = cat.all_tools()
    readers = readers_for("contacts", tools, None)
    names = [t.name for t in readers]
    assert "contacts.search" in names
    assert "contacts.get" in names
