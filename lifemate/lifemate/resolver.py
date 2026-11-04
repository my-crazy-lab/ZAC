"""Giải thực thể, số, giờ (EXECUTION-PLAN.md §8.8 và §8.11).

Hints chỉ là **gợi ý** cho LLM; gate chỉ ghi đè khi tự tin cao.
"""
from datetime import datetime

from lifemate.datatypes import Entity, Hint
from lifemate.vi_norm import (
    STOPWORDS_VI,
    parse_numbers,
    parse_times,
    token_sim,
    tokenize_vi,
)


def _best_window(text_tokens, name_tokens, threshold):
    """Khớp toàn tên: cửa sổ độ dài len(name_tokens); mọi cặp ≥ threshold."""
    n = len(name_tokens)
    if n == 0 or len(text_tokens) < n:
        return None
    best = None
    for i in range(len(text_tokens) - n + 1):
        window = text_tokens[i:i + n]
        pairs = [token_sim(a, b) for a, b in zip(window, name_tokens)]
        if any(score < threshold for score, _ in pairs):
            continue
        score = sum(p[0] for p in pairs) / n
        tier = min(p[1] for p in pairs)
        if best is None or score > best[0]:
            best = (score, tier, i, window)
    return best


def match_entities(text_tokens, entities, threshold: float) -> list:
    """Ứng viên thực thể cho transcript."""
    text_tokens = [t.lower() for t in (text_tokens or [])]
    hints = []
    for entity in entities or []:
        for name in entity.names or []:
            name_tokens = tokenize_vi(name)
            if not name_tokens:
                continue
            matched = None
            if len(name_tokens) == 1:
                for tok in text_tokens:
                    if tok in STOPWORDS_VI:
                        continue
                    score, tier = token_sim(name_tokens[0], tok)
                    if score >= 0.88 and (matched is None or score > matched[0]):
                        matched = (score, tier, tok, False)
            else:
                full = _best_window(text_tokens, name_tokens, threshold)
                if full:
                    matched = (full[0], full[1], " ".join(full[3]), False)
                else:
                    last = name_tokens[-1]
                    for tok in text_tokens:
                        if tok in STOPWORDS_VI:
                            continue
                        score, tier = token_sim(last, tok)
                        if score >= 0.88 and tier <= 3 and (matched is None or score > matched[0]):
                            matched = (score, tier, tok, True)
            if not matched:
                continue
            score, tier, span, partial = matched
            hints.append(Hint(
                kind="entity",
                span=span,
                value=entity.id,
                conf=round(score, 4),
                extra={
                    "collection": entity.collection,
                    "name": name,
                    "tier": tier,
                    "partial": partial,
                },
            ))

    # ưu tiên bậc: cùng span có đúng một ứng viên bậc 1 ⇒ chỉ giữ ứng viên đó
    by_span = {}
    for hint in hints:
        by_span.setdefault(hint.span, []).append(hint)
    out = []
    for span, group in by_span.items():
        tier1 = [h for h in group if h.extra.get("tier") == 1]
        if len(tier1) == 1:
            out.append(tier1[0])
        else:
            out.extend(group)
    out.sort(key=lambda h: (-h.conf, h.span))
    return out


def build_hints(hyps, store, now: datetime, with_numbers: bool = True) -> list:
    """Gợi ý từ n-best + snapshot hiện tại."""
    entities = store.entity_list() if store is not None else []
    merged = {}
    for hyp in hyps or []:
        text = getattr(hyp, "text", "") or ""
        tokens = tokenize_vi(text)
        for hint in match_entities(tokens, entities, 0.80):
            key = (hint.span, hint.value)
            if key not in merged or hint.conf > merged[key].conf:
                merged[key] = hint
    hints = list(merged.values())

    if with_numbers and hyps:
        top = hyps[0]
        text = getattr(top, "text", "") or ""
        numbers = parse_numbers(text)
        times = parse_times(text, now) if now is not None else []
        # ứng viên thay thế từ n-best 2/3
        alt_numbers = []
        for hyp in hyps[1:3]:
            alt = parse_numbers(getattr(hyp, "text", "") or "")
            alt_numbers.append([h.value for h in alt])
        for hint in numbers:
            alts = []
            for values in alt_numbers:
                for value in values:
                    if value != hint.value and value not in alts:
                        alts.append(value)
            if alts:
                hint.extra["alt_values"] = alts
            hints.append(hint)
        hints.extend(times)

    order = {"entity": 0, "number": 1, "time": 2, "digits": 3}
    hints.sort(key=lambda h: (order.get(h.kind, 9), -h.conf))
    return hints


def format_hints(hints) -> str:
    lines = []
    for hint in hints or []:
        if hint.kind == "entity":
            name = hint.extra.get("name", "")
            coll = hint.extra.get("collection", "")
            suffix = ""
            if hint.extra.get("partial"):
                suffix = ", khớp tên gọi"
            lines.append(
                f'TÊN "{hint.span}" ≈ {name} (id {hint.value}, tin cậy {hint.conf:.2f}{suffix})'
            )
        elif hint.kind == "number":
            lines.append(f'SỐ "{hint.span}" = {hint.value}')
        elif hint.kind == "digits":
            lines.append(f'SỐ "{hint.span}" = {hint.value} (chuỗi chữ số)')
        elif hint.kind == "time":
            alts = hint.extra.get("alternatives") or []
            if alts:
                lines.append(f'GIỜ "{hint.span}" = {hint.value} hoặc {" | ".join(alts)}')
            else:
                lines.append(f'GIỜ "{hint.span}" = {hint.value}')
    return "\n".join(lines)
