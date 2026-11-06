"""Test cho llm/client.py: client HTTP không sống qua nhiều asyncio.run."""

from __future__ import annotations

from types import SimpleNamespace

from llm.client import LLM


def _llm():
    cfg = SimpleNamespace(LLM_BASE_URL="http://127.0.0.1:9/v1",
                          LLM_API_KEY="", LLM_MODEL="m", LLM_CONCURRENCY=2,
                          LLM_MAX_RETRIES=0, LLM_TIMEOUT_S=5)
    return LLM(cfg)


def test_generate_closes_client_after_each_call(monkeypatch):
    seen: list[int] = []

    async def fake_one(self, index, prompt, *args, **kwargs):
        seen.append(id(self._client))
        return "{}"

    monkeypatch.setattr(LLM, "_one", fake_one)
    llm = _llm()
    llm.generate(["a"])
    llm.generate(["b"])
    assert llm._client is None
    # hai lượt gọi dùng hai client khác nhau (không tái dùng pool cũ)
    assert seen[0] != seen[1]
