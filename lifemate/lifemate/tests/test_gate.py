"""Test `gate.py` (EXECUTION-PLAN.md §8.15) — 13 ca bắt buộc."""
from lifemate import config
from lifemate.gate import gate
from lifemate.state_store import StateStore
from lifemate.datatypes import Call, Hint


class FakeEnv:
    def __init__(self, ok=True):
        self.ok = ok
        self.validated = []

    def validate(self, name, args=None):
        self.validated.append((name, args))
        return {"ok": self.ok, "error": None if self.ok else "sai tham số"}


class State:
    def __init__(self, nudges_used=0):
        self.nudges_used = nudges_used
        self.writes_done = 0
        self.executed = []


def _tools():
    return {
        "contacts.search": _tool("contacts.search", "read", props={}, required=[]),
        "contacts.get": _tool("contacts.get", "read", props={"id": {"type": "string"}}, required=["id"]),
        "banking.transfer": _tool(
            "banking.transfer", "write",
            props={
                "contact_id": {"type": "string", "x-ref": "contacts.contacts"},
                "amount": {"type": "integer"},
            },
            required=["contact_id", "amount"],
        ),
        "sms.send": _tool(
            "sms.send", "write",
            props={
                "contact_id": {"type": "string", "x-ref": "contacts.contacts"},
                "phone_number": {"type": "string", "enum": ["09", "08"]},
                "content": {"type": "string"},
                "mode": {"type": "string", "enum": ["fast", "slow"]},
            },
            required=["content"],
            one_of=[["contact_id"], ["phone_number"]],
        ),
        "music.play": _tool(
            "music.play", "write",
            props={"track_id": {"type": "string"}, "device": {"type": "string"}},
            required=[],
            one_of=[["track_id"], ["device"]],
        ),
        "unknown.app.tool": _tool("unknown.app.tool", "write", props={}, required=[]),
    }


def _tool(name, kind, props=None, required=None, one_of=None):
    from lifemate.datatypes import Tool
    return Tool(
        name=name, app=name.split(".")[0], kind=kind, description=f"tool {name}",
        app_name_vi="", app_description="", returns="", parameters={},
        required=required or [], props=props or {}, one_of=one_of or [],
    )


def _store_with_contacts():
    store = StateStore()
    store.ingest("contacts.search", {"query": "x"}, {
        "ok": True,
        "contacts": [
            {"id": "c_01", "name": "Hương"},
            {"id": "c_02", "name": "Lan"},
        ],
    })
    return store


def _gate(calls, store=None, hints=None, text="", state=None, tools=None):
    return gate(calls, text, {}, tools or _tools(), store or StateStore(), hints or [],
                FakeEnv(), state or State(), "chuyển tiền cho Lan")


def test_1_bogus_id_replaced_by_matching_entity():
    store = _store_with_contacts()
    res = _gate([Call("banking.transfer", {"contact_id": "Hương", "amount": 100})], store)
    assert res.calls
    assert res.calls[0]["arguments"]["contact_id"] == "c_01"


def test_2_bogus_id_without_candidate_is_dropped_and_becomes_ask():
    store = _store_with_contacts()
    res = _gate([Call("banking.transfer", {"contact_id": "Zzzzz", "amount": 100})], store)
    assert res.calls == []
    assert res.ask is not None
    assert res.ask.tool_name == "banking.transfer"
    assert res.ask.params == ["contact_id"]


def test_3_known_id_is_kept():
    store = _store_with_contacts()
    res = _gate([Call("banking.transfer", {"contact_id": "c_02", "amount": 100})], store)
    assert res.calls[0]["arguments"]["contact_id"] == "c_02"


def test_4_unread_collection_defers_write_then_keeps_when_no_nudges_left():
    tools = _tools()
    tools["contacts.list"] = _tool("contacts.list", "read", props={}, required=[])
    store = StateStore()
    res = gate([Call("banking.transfer", {"contact_id": "c_01", "amount": 100})], "", {}, tools,
               store, [], FakeEnv(), State(), "chuyển tiền")
    assert res.calls == []
    assert res.deferred
    assert res.needs_read and res.needs_read[0][1] == "contact_id"
    assert res.needs_read[0][2] == "contacts"

    state = State(nudges_used=config.MAX_NUDGES)
    res2 = gate([Call("banking.transfer", {"contact_id": "c_01", "amount": 100})], "", {}, tools,
                StateStore(), [], FakeEnv(), state, "chuyển tiền")
    assert res2.calls
    assert res2.calls[0]["arguments"]["contact_id"] == "c_01"


def test_5_missing_required_becomes_ask():
    res = _gate([Call("banking.transfer", {"amount": 100})])
    assert res.ask is not None
    assert res.ask.tool_name == "banking.transfer"
    assert res.ask.params == ["contact_id"]


def test_6_one_of_missing_asks_exactly_one_param_of_intended_group():
    # phone_number="77" không hợp lệ ⇒ bị bỏ ⇒ nhóm ["phone_number"] thiếu,
    # nhưng raw_args cho thấy LLM định dùng nhóm đó ⇒ hỏi đúng 1 tham số của nhóm đó.
    res = _gate([Call("sms.send", {"content": "hello", "phone_number": "77"})])
    assert res.ask is not None
    assert res.ask.tool_name == "sms.send"
    assert res.ask.params == ["phone_number"]
    assert len(res.ask.params) == 1

    # không có nhóm nào thỏa và không có raw_args ⇒ hỏi nhóm đầu tiên
    res2 = _gate([Call("sms.send", {"content": "hello"})])
    assert res2.ask is not None
    assert res2.ask.params == ["contact_id"]


def test_7_tool_outside_installed_apps_is_dropped():
    tools = {k: v for k, v in _tools().items() if k != "unknown.app.tool"}
    res = gate([Call("unknown.app.tool", {})], "", {}, tools, StateStore(), [], FakeEnv(), State(), "")
    assert res.calls == []
    assert res.ask is None


def test_8_enum_case_is_fixed():
    res = _gate([Call("sms.send", {"content": "hi", "phone_number": "09", "mode": "FAST"})])
    assert res.calls
    assert res.calls[0]["arguments"]["mode"] == "fast"


def test_9_duplicate_calls_are_removed():
    res = _gate([Call("contacts.get", {"id": "c_01"}), Call("contacts.get", {"id": "c_01"})])
    assert len(res.calls) == 1


def test_10_duplicate_read_dropped_but_different_args_kept():
    store = _store_with_contacts()
    store.ingest("contacts.get", {"id": "c_01"}, {"ok": True, "contact": {"id": "c_01"}})
    res = _gate([Call("contacts.get", {"id": "c_01"}), Call("contacts.get", {"id": "c_02"})], store)
    assert len(res.calls) == 1
    assert res.calls[0]["arguments"]["id"] == "c_02"


def test_11_missing_param_does_not_stop_later_calls():
    res = _gate([Call("banking.transfer", {"amount": 100}),
                 Call("contacts.get", {"id": "c_01"})])
    assert res.ask is not None
    assert any(c["name"] == "contacts.get" for c in res.calls)


def test_12_autofill_refs():
    store = _store_with_contacts()
    hint = Hint(kind="entity", span="lan", value="c_02", conf=0.95,
                extra={"collection": "contacts", "name": "Lan", "tier": 1, "partial": False})
    res = _gate([Call("banking.transfer", {"amount": 100})], store, [hint])
    assert res.calls
    assert res.calls[0]["arguments"]["contact_id"] == "c_02"

    hint2 = Hint(kind="entity", span="lan", value="c_01", conf=0.95,
                 extra={"collection": "contacts", "name": "Lan", "tier": 1, "partial": False})
    res2 = _gate([Call("banking.transfer", {"amount": 100})], store, [hint, hint2])
    assert res2.calls == []
    assert res2.ask is not None


def test_13_empty_list_with_khong_ho_tro_is_refuse():
    res = _gate([], text="KHONG_HO_TRO")
    assert res.refuse is True
    assert res.ask is None
