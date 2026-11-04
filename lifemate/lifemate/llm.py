"""Client LLM OpenAI-compatible (EXECUTION-PLAN.md §8.10).

Hai nhánh: structured tool-calls (ưu tiên) và fallback text-JSON.
"""
import json
import re

from lifemate.apiclient import ApiClient
from lifemate.datatypes import Call

# <tool_call> {json} </tool_call> (chấp nhận cả biến thể có space hoặc thuộc tính)
_TOOL_CALL_RE = re.compile(
    r"<\s*tool_call\s*>?\s*(\{.*?\})\s*<\s*/\s*tool_call\s*>", re.S | re.I
)
_TEXT_CALL_RE = re.compile(r"(\{[^{}]*\"name\"\s*:[^{}]*\"arguments\"\s*:.*?\})", re.S)


def parse_tool_calls(message: dict) -> list:
    """Structured: `message.tool_calls` → list[Call]."""
    out = []
    if not isinstance(message, dict):
        return out
    raw_calls = message.get("tool_calls") or []
    for i, tc in enumerate(raw_calls):
        try:
            fn = tc.get("function") or {}
            name = fn.get("name")
            if not isinstance(name, str) or not name:
                continue
            args_raw = fn.get("arguments")
            if isinstance(args_raw, str):
                try:
                    args = json.loads(args_raw) if args_raw.strip() else {}
                except Exception:  # noqa: BLE001 - JSON hỏng ⇒ bỏ qua call đó
                    continue
            elif isinstance(args_raw, dict):
                args = args_raw
            else:
                args = {}
            if not isinstance(args, dict):
                continue
            call_id = tc.get("id") or f"call_{i + 1}"
            out.append(Call(name=name, args=args, call_id=call_id))
        except Exception:  # noqa: BLE001
            continue
    return out


def parse_tool_calls_text(text: str) -> list:
    """Fallback: `<tool_call>{...}</tool_call>` hoặc JSON có name+arguments."""
    out = []
    if not isinstance(text, str) or not text:
        return out
    chunks = _TOOL_CALL_RE.findall(text)
    if not chunks:
        chunks = _TEXT_CALL_RE.findall(text)
    for i, chunk in enumerate(chunks):
        try:
            obj = json.loads(chunk)
        except Exception:  # noqa: BLE001 - JSON hỏng ⇒ []
            continue
        if not isinstance(obj, dict):
            continue
        name = obj.get("name")
        args = obj.get("arguments")
        if not isinstance(name, str) or not name:
            continue
        if isinstance(args, str):
            try:
                args = json.loads(args) if args.strip() else {}
            except Exception:  # noqa: BLE001
                continue
        if not isinstance(args, dict):
            args = {}
        out.append(Call(name=name, args=args, call_id=f"call_{i + 1}"))
    return out


def extract_text(message: dict) -> str:
    """Nội dung text của assistant, bỏ các khối tool call."""
    if not isinstance(message, dict):
        return ""
    content = message.get("content") or ""
    if not isinstance(content, str):
        content = str(content)
    return _TOOL_CALL_RE.sub("", content).strip()


class LLM:
    def __init__(self, base_url, api_key, model, extra_body=None, temperature=0, timeout=60, max_retries=5):
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.extra_body = extra_body or {}
        self.temperature = temperature
        self.client = ApiClient(base_url, api_key, timeout=timeout, max_retries=max_retries)

    @property
    def available(self) -> bool:
        return self.client.available and bool(self.model)

    def generate(self, messages, tools=None, max_tokens=512, log=None):
        """Trả (calls, text, assistant_message). Lỗi API ⇒ ([], "", {})."""
        message = self.client.chat(
            model=self.model,
            messages=messages,
            tools=tools,
            temperature=self.temperature,
            max_tokens=max_tokens,
            extra_body=self.extra_body or None,
            log=log,
        )
        if message is None:
            return [], "", {}
        raw = message if isinstance(message, dict) else message.model_dump()
        calls = parse_tool_calls(raw)
        text = extract_text(raw)
        if not calls and text:
            calls = parse_tool_calls_text(text)
        return calls, text, raw
