"""Từ vựng thực thể trong môi trường + cắt gọn snapshot (EXECUTION-PLAN.md §8.6)."""
import json

from lifemate.vi_norm import STOPWORDS_VI, strip_accents


def _tokens(text: str) -> set:
    return {t for t in strip_accents(text or "").split() if t and t not in STOPWORDS_VI}


def build_snapshot(store) -> dict:
    """Dựng dict gọn từ `store.snapshot`, nhóm theo tool, bỏ `ok`."""
    grouped = {}
    for key, result in (store.snapshot or {}).items():
        tool = key.split("|", 1)[0]
        payload = result
        if isinstance(result, dict):
            payload = {k: v for k, v in result.items() if k != "ok"}
            if not payload:
                payload = {}
        grouped.setdefault(tool, []).append(payload)
    return grouped


def _trim_list(items: list, transcript_tokens: set) -> tuple:
    """Giữ phần tử khớp transcript + 10 phần tử đầu; trả (list, số bị lược)."""
    kept = []
    dropped = 0
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            kept.append(item)
            continue
        text = json.dumps(item, ensure_ascii=False)
        toks = _tokens(text)
        if idx < 10 or (toks & transcript_tokens):
            kept.append(item)
        else:
            dropped += 1
    if dropped:
        kept.append({"_note": f"đã lược {dropped} mục"})
    return kept, dropped


def trim_snapshot(store, transcript: str, max_chars: int) -> str:
    """Snapshot dạng text, ≤ `max_chars` nếu có thể."""
    grouped = build_snapshot(store)
    transcript_tokens = _tokens(transcript)
    text = json.dumps(grouped, ensure_ascii=False)
    if len(text) <= max_chars:
        return text

    # 1) lược từng list dài
    changed = True
    while changed and len(json.dumps(grouped, ensure_ascii=False)) > max_chars:
        changed = False
        for tool, items in list(grouped.items()):
            if not isinstance(items, list):
                continue
            new_items = []
            dropped = 0
            for item in items:
                if isinstance(item, list) and len(item) > 15:
                    trimmed, n = _trim_list(item, transcript_tokens)
                    if n:
                        dropped += n
                        changed = True
                    new_items.append(trimmed)
                else:
                    new_items.append(item)
            grouped[tool] = new_items

    # 2) cắt từng tool theo độ khớp transcript (ngược) cho tới khi vừa
    while len(json.dumps(grouped, ensure_ascii=False)) > max_chars and grouped:
        scored = []
        for tool, items in grouped.items():
            text = json.dumps(items, ensure_ascii=False)
            toks = _tokens(text)
            scored.append((len(toks & transcript_tokens) / (1 + len(toks)), tool))
        scored.sort()
        worst = scored[0][1]
        del grouped[worst]
    return json.dumps(grouped, ensure_ascii=False)
