"""LLM giả cho test (không cần mạng) — EXECUTION-MVP.md M0.

Dùng cho test M3, M4, M9: trả đúng nội dung đã định nghĩa trước, theo
bảng tra ``{sha256(prompt): output}`` hoặc hàm callback.
"""

from __future__ import annotations

import asyncio
from typing import Callable

from llm.client import LLM


class FakeLLM(LLM):
    """Trả đáp án theo bảng tra hoặc callback; không bao giờ gọi mạng."""

    def __init__(self, table: dict[str, str] | None = None,
                 callback: Callable[[str], str] | None = None,
                 default: str = "") -> None:
        super().__init__()
        self.table = dict(table or {})
        self.callback = callback
        self.default = default
        self.calls: list[str] = []

    async def agenerate(self, prompts: list[str], *, json_schema: dict | None = None,
                        max_tokens: int = 512, thinking: bool = False) -> list[str]:
        out: list[str] = []
        for p in prompts:
            self.calls.append(p)
            if self.callback is not None:
                out.append(self.callback(p))
                continue
            key = self._hash(p)
            out.append(self.table.get(key, self.table.get(p, self.default)))
        return out

    def generate(self, prompts: list[str], **kw: object) -> list[str]:
        return asyncio.run(self.agenerate(prompts, **kw))  # type: ignore[arg-type]


__all__ = ["FakeLLM"]
