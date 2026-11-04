"""Test `state_store.py` và `lexicon.py` (EXECUTION-PLAN.md §8.6)."""
from lifemate.lexicon import trim_snapshot
from lifemate.state_store import StateStore


def test_ingest_list_of_entities():
    store = StateStore()
    store.ingest("contacts.search", {"query": "Lan"}, {
        "ok": True,
        "contacts": [{"id": "c_01", "name": "Hương"}, {"id": "c_02", "name": "Lan"}],
    })
    assert store.ids["contacts"] == {"c_01", "c_02"}
    assert "contacts" in store.collections_read
    assert len(store.entity_list()) == 2


def test_ingest_empty_list_still_marks_collection():
    store = StateStore()
    store.ingest("contacts.search", {"query": "zzz"}, {"ok": True, "contacts": []})
    assert "contacts" in store.collections_read
    assert store.ids.get("contacts", set()) == set()


def test_ingest_write_result_id_goes_to_star():
    store = StateStore()
    store.ingest("alarm.create", {"time": "t"}, {"ok": True, "alarm": {"id": "alm_02"}})
    assert "alm_02" in store.ids["*"]
    assert "alm_02" in store.ids["alarm"]


def test_has_called_ignores_key_order():
    store = StateStore()
    store.ingest("contacts.get", {"id": "c_01", "fields": ["name"]}, {"ok": True})
    assert store.has_called("contacts.get", {"fields": ["name"], "id": "c_01"})
    assert not store.has_called("contacts.get", {"id": "c_02"})


def test_trim_snapshot_keeps_matching_item():
    store = StateStore()
    store.ingest("contacts.search", {"query": "Lan"}, {
        "ok": True,
        "contacts": [
            {"id": "c_01", "name": "Hương"},
            {"id": "c_02", "name": "Lan"},
            {"id": "c_03", "name": "Minh"},
        ],
    })
    out = trim_snapshot(store, "gửi cho Lan", 100000)
    assert "Lan" in out
    text = trim_snapshot(store, "gửi cho Lan", 400)
    assert "Lan" in text
    small = trim_snapshot(store, "gửi cho Lan", 60)
    assert len(small) <= 60
