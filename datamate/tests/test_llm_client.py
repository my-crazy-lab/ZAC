"""Test cho llm/client.py: client HTTP không sống qua nhiều asyncio.run."""

from __future__ import annotations

from types import SimpleNamespace

import llm.client as client_mod
from llm.client import LLM


def _llm():
    cfg = SimpleNamespace(LLM_BASE_URL="http://127.0.0.1:9/v1",
                          LLM_API_KEY="", LLM_MODEL="m", LLM_CONCURRENCY=2,
                          LLM_MAX_RETRIES=0, LLM_TIMEOUT_S=5)
    return LLM(cfg)


def test_generate_closes_client_after_each_call(monkeypatch):
    seen: list[int] = []
    created: list[object] = []
    closed: list[object] = []

    class FakeClient:
        def __init__(self, *args, **kwargs):
            created.append(self)

        async def aclose(self):
            closed.append(self)

    async def fake_one(self, index, prompt, *args, **kwargs):
        seen.append(id(self._client))
        return "{}"

    monkeypatch.setattr(client_mod.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(LLM, "_one", fake_one)
    llm = _llm()
    llm.generate(["a"])
    llm.generate(["b"])

    assert llm._client is None
    assert len(created) == 2 and created[0] is not created[1]
    assert closed == created
    assert seen[0] != seen[1]


def test_openrouter_disables_reasoning_at_top_level():
    cfg = SimpleNamespace(LLM_BASE_URL="https://openrouter.ai/api/v1",
                          LLM_API_KEY="", LLM_MODEL="qwen/qwen3-14b",
                          LLM_CONCURRENCY=2)
    llm = LLM(cfg)
    body = llm._payload("q", None, 128, False)
    assert body["reasoning"] == {"effort": "none"}
    assert "extra_body" not in body
