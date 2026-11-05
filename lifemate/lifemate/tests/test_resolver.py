"""Test `resolver.py` — phần thực thể (EXECUTION-PLAN.md §8.8)."""
from datetime import datetime, timedelta, timezone

from lifemate.resolver import build_hints, format_hints, match_entities
from lifemate.state_store import StateStore
from lifemate.datatypes import Entity, Hyp


def _entities(*specs):
    out = []
    for eid, coll, names in specs:
        out.append(Entity(id=eid, collection=coll, fields={}, names=list(names), source_tool="contacts.search"))
    return out


def _tokens(text):
    from lifemate.vi_norm import tokenize_vi
    return tokenize_vi(text)


def test_unique_tier1_wins():
    entities = _entities(
        ("c_01", "contacts", ["Thư"]),
        ("c_02", "contacts", ["Thu"]),
        ("c_03", "contacts", ["Hương"]),
    )
    hints = match_entities(_tokens("chuyển cho chị thư năm trăm nghìn"), entities, 0.80)
    values = [h.value for h in hints]
    assert values == ["c_01"]


def test_tier1_exact_spelling_wins():
    entities = _entities(
        ("c_01", "contacts", ["Thư"]),
        ("c_02", "contacts", ["Thu"]),
    )
    hints = match_entities(_tokens("chuyển cho chị thu"), entities, 0.80)
    assert [h.value for h in hints] == ["c_02"]


def test_tone_difference_is_tier2():
    entities = _entities(("c_03", "contacts", ["Hương"]))
    hints = match_entities(_tokens("chị hướng"), entities, 0.80)
    assert [h.value for h in hints] == ["c_03"]
    assert hints[0].extra["tier"] == 2


def test_partial_match_last_name():
    entities = _entities(("c_05", "contacts", ["Nguyễn Thị Lan"]))
    hints = match_entities(_tokens("gọi cho Lan"), entities, 0.80)
    assert hints and hints[0].value == "c_05"
    assert hints[0].extra["partial"] is True


def test_ambiguous_same_name_gives_two_hints():
    entities = _entities(
        ("c_05", "contacts", ["Lan"]),
        ("c_06", "contacts", ["Lan"]),
    )
    hints = match_entities(_tokens("gọi cho Lan"), entities, 0.80)
    assert len(hints) == 2
    assert {h.value for h in hints} == {"c_05", "c_06"}


def test_stopwords_never_match():
    entities = _entities(("c_07", "contacts", ["cho"]), ("c_08", "contacts", ["chị"]))
    hints = match_entities(_tokens("cho chị nhé"), entities, 0.80)
    assert hints == []


def test_tier4_phonetic_single_token_matches_asr_confusion():
    # ASR hay lẫn phụ âm đầu vùng miền (giữ → dữ): khớp bậc-4 vẫn phải gợi ý.
    entities = _entities(("c_09", "contacts", ["giữ"]))
    hints = match_entities(_tokens("đặt dữ luôn cái phòng ấy"), entities, 0.80)
    assert [h.value for h in hints] == ["c_09"]
    assert hints[0].extra["tier"] == 4


def test_build_hints_and_format():
    store = StateStore()
    store.ingest("contacts.search", {"query": "Lan"}, {
        "ok": True,
        "contacts": [{"id": "c_05", "name": "Nguyễn Thị Lan"}],
    })
    now = datetime(2026, 11, 16, 17, 0, tzinfo=timezone(timedelta(hours=7)))
    hyps = [Hyp(text="chuyển cho Lan năm trăm nghìn", score=1.0)]
    hints = build_hints(hyps, store, now)
    kinds = {h.kind for h in hints}
    assert "entity" in kinds and "number" in kinds
    text = format_hints(hints)
    assert "TÊN" in text and "SỐ" in text
    assert "500000" in text
