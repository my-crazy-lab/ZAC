"""Few-shot theo BM25 (EXECUTION-PLAN.md §8.9), bật bằng `ENABLE_FEWSHOT`.

Chỉ mục dựng từ các mẫu train trong `tune_ids` (không gồm heldout).
ID trong ví dụ được che để mô hình không chép ID của người dùng khác.
"""
import json

from lifemate.bm25 import BM25, tokenize
from lifemate.vi_norm import STOPWORDS_VI

ID_PLACEHOLDER = "<id lấy từ dữ liệu>"


def _is_id_like(value) -> bool:
    """Giá trị trông giống ID của app (kèm tiền tố/số), không phải tên người."""
    if not isinstance(value, str) or not value:
        return False
    if " " in value.strip():
        return False
    if value.strip().isdigit():
        return True
    head = value.split("_")[0]
    return bool(head) and head.isalpha() and any(ch.isdigit() for ch in value)


def mask_ids(args: dict) -> dict:
    """Thay giá trị giống ID bằng placeholder."""
    out = {}
    for key, value in (args or {}).items():
        if _is_id_like(value):
            out[key] = ID_PLACEHOLDER
        else:
            out[key] = value
    return out


def format_call(name: str, args: dict) -> str:
    if not args:
        return f"{name}()"
    parts = []
    for key, value in args.items():
        if isinstance(value, str):
            parts.append(f'{key}="{value}"')
        elif isinstance(value, list):
            parts.append(f'{key}=[{", ".join(str(v) for v in value)}]')
        else:
            parts.append(f"{key}={value}")
    return f"{name}({', '.join(parts)})"


class FewShotIndex:
    """Chỉ mục BM25 trên `audio_text` của các mẫu train."""

    def __init__(self, samples: list, catalog=None):
        self.samples = []
        for sample in samples or []:
            transcript = (sample.get("audio_text") or "").strip()
            if not transcript:
                continue
            self.samples.append(sample)
        self.docs = [
            " ".join(t for t in tokenize(s.get("audio_text") or "") if t not in STOPWORDS_VI)
            for s in self.samples
        ]
        self.index = BM25(self.docs) if self.docs else None
        self.catalog = catalog

    def query(self, transcript: str, installed_tools: set, k: int) -> list:
        """Top-k ví dụ mà mọi tool trong gold đều nằm trong `installed_tools`."""
        if not self.index:
            return []
        query = [t for t in tokenize(transcript or "") if t not in STOPWORDS_VI]
        ranked = self.index.rank(query)
        out = []
        for i, _score in ranked:
            sample = self.samples[i]
            gold_calls = (sample.get("label") or {}).get("tool_calls") or []
            names = [c.get("name") for c in gold_calls if isinstance(c, dict)]
            if any(name not in installed_tools for name in names):
                continue
            out.append(sample)
            if len(out) >= max(1, k) * 3:
                break
        return out


def format_fewshot(examples: list, catalog=None) -> str:
    """Định dạng ví dụ theo §8.9 (ID được che)."""
    lines = []
    for sample in examples or []:
        transcript = (sample.get("audio_text") or "").strip()
        gold_calls = (sample.get("label") or {}).get("tool_calls") or []
        lines.append(f'Yêu cầu: "{transcript}"')
        if not gold_calls:
            lines.append("Gọi: (không gọi công cụ nào)")
        else:
            rendered = []
            for call in gold_calls:
                if not isinstance(call, dict):
                    continue
                rendered.append(format_call(call.get("name", ""), mask_ids(call.get("arguments") or {})))
            lines.append("Gọi: " + "; ".join(rendered))
        lines.append("---")
    if lines:
        lines.append('Các ID trong ví dụ thuộc người dùng khác; chỉ dùng ID từ "Dữ liệu ứng dụng".')
    return "\n".join(lines)


def select_examples(index, transcript: str, installed_tools: set, k: int) -> list:
    """Top-k; nếu top-10 có ví dụ ask/refuse mà top-K chưa có loại đó ⇒ thay thế (mỗi loại tối đa 1)."""
    if index is None or not getattr(index, "samples", None):
        return []
    candidates = index.query(transcript, installed_tools, max(k, 10))
    if not candidates:
        return []
    top = candidates[:k]
    top_types = {_example_type(s) for s in top}
    for candidate in candidates[k:]:
        ctype = _example_type(candidate)
        if ctype in ("ask", "refuse") and ctype not in top_types:
            top[-1] = candidate
            top_types.add(ctype)
            break
    return top


def _example_type(sample) -> str:
    gold_calls = (sample.get("label") or {}).get("tool_calls") or []
    if not gold_calls:
        return "refuse"
    if any(isinstance(c, dict) and c.get("name") == "sys.ask_missing_info" for c in gold_calls):
        return "ask"
    return "act"


def dump_json(value) -> str:
    return json.dumps(value, ensure_ascii=False)
