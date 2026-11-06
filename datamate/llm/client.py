"""Client HTTP cho API LLM OpenAI-compatible (phase 1: MiniMax).

Quy tắc (EXECUTION-MVP.md M0):
- ``temperature=0``, ``seed=0``, ``top_p=1`` — mọi lời gọi đều greedy, tái lập được.
- Nhiều endpoint ⇒ chia vòng theo chỉ số prompt (``i % n_urls``) — xác định.
- Retry backoff luỹ thừa khi 429/5xx; lỗi cuối cùng ⇒ trả ``""`` cho prompt đó.
- Kết quả **đúng thứ tự input**.
- Không có endpoint cấu hình ⇒ trả ``""`` cho mọi prompt (chạy offline được).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from typing import Any

import httpx

import config

log = logging.getLogger(__name__)


class LLM:
    """Bọc API chat/completions. Không bao giờ ném lỗi ra ngoài cho lô lệnh."""

    def __init__(self, cfg: Any = config) -> None:
        self.cfg = cfg
        urls = tuple(getattr(cfg, "LLM_BASE_URLS", ()) or ())
        if not urls:
            base = getattr(cfg, "LLM_BASE_URL", "") or ""
            urls = (base,) if base else ()
        self.urls: tuple[str, ...] = urls
        self.api_key = getattr(cfg, "LLM_API_KEY", "") or ""
        self.model = getattr(cfg, "LLM_MODEL", "")
        self.concurrency = int(getattr(cfg, "LLM_CONCURRENCY", 16))
        self.max_retries = int(getattr(cfg, "LLM_MAX_RETRIES", 4))
        self.timeout_s = float(getattr(cfg, "LLM_TIMEOUT_S", 120))
        self._client: httpx.AsyncClient | None = None
        self._schema_mode: str = "json_schema"  # json_schema | json_object
        self._schema_supported: bool | None = None

    # ------------------------------------------------------------------ util
    @property
    def available(self) -> bool:
        return bool(self.urls)

    def _url_for(self, index: int) -> str:
        base = self.urls[index % len(self.urls)]
        if base.endswith("/chat/completions"):
            return base
        return base.rstrip("/") + "/chat/completions"

    @staticmethod
    def _hash(prompt: str) -> str:
        return hashlib.sha256(prompt.encode("utf-8")).hexdigest()

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout_s)
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _payload(self, prompt: str, json_schema: dict | None, max_tokens: int,
                 thinking: bool) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "seed": 0,
            "top_p": 1,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if json_schema is not None and self._schema_mode == "json_schema":
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "response",
                    "schema": json_schema,
                    "strict": True,
                },
            }
        elif json_schema is not None:
            body["response_format"] = {"type": "json_object"}
        # Qwen3-style: tắt suy luận mặc định
        body["extra_body"] = {
            "chat_template_kwargs": {"enable_thinking": bool(thinking)}
        }
        return body

    @staticmethod
    def _extract(content: str) -> str:
        content = (content or "").strip()
        if content.startswith("```"):
            content = content.strip("`")
            if content.lower().startswith("json"):
                content = content[4:]
            content = content.strip()
        return content

    @staticmethod
    def _is_valid_json(text: str) -> bool:
        try:
            json.loads(text)
            return True
        except (json.JSONDecodeError, TypeError):
            return False

    async def _one(self, index: int, prompt: str, json_schema: dict | None,
                   max_tokens: int, thinking: bool,
                   sem: asyncio.Semaphore) -> str:
        if not self.available:
            return ""
        async with sem:
            client = await self._get_client()
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            body = self._payload(prompt, json_schema, max_tokens, thinking)
            url = self._url_for(index)
            last_err = ""
            for attempt in range(self.max_retries):
                try:
                    resp = await client.post(url, headers=headers, json=body)
                except (httpx.HTTPError, OSError) as exc:  # lỗi mạng
                    last_err = f"{type(exc).__name__}: {exc}"
                    await asyncio.sleep(min(2 ** attempt, 8))
                    continue
                if resp.status_code == 429 or resp.status_code >= 500:
                    last_err = f"HTTP {resp.status_code}"
                    await asyncio.sleep(min(2 ** attempt, 8))
                    continue
                if resp.status_code >= 400:
                    last_err = f"HTTP {resp.status_code}: {resp.text[:200]}"
                    # endpoint có thể không hỗ trợ json_schema ⇒ hạ xuống json_object
                    if resp.status_code == 400 and json_schema and self._schema_mode == "json_schema":
                        self._schema_mode = "json_object"
                        body = self._payload(prompt, json_schema, max_tokens, thinking)
                        continue
                    break
                try:
                    data = resp.json()
                except ValueError:
                    last_err = "response không phải JSON"
                    break
                choices = data.get("choices") or []
                if not choices:
                    last_err = "response rỗng"
                    break
                content = (choices[0].get("message") or {}).get("content") or ""
                text = self._extract(content)
                if json_schema is not None:
                    if not self._is_valid_json(text):
                        # hỏi lại tối đa 1 lần
                        retry_prompt = (
                            prompt
                            + "\n\nCâu trả lời trước không hợp lệ về JSON. "
                            "Chỉ trả về MỘT đối tượng JSON đúng schema."
                        )
                        body = self._payload(retry_prompt, json_schema, max_tokens, thinking)
                        for attempt2 in range(1):
                            try:
                                resp2 = await client.post(url, headers=headers, json=body)
                                data2 = resp2.json()
                                ch2 = data2.get("choices") or []
                                if ch2:
                                    text = self._extract(
                                        (ch2[0].get("message") or {}).get("content") or ""
                                    )
                            except (httpx.HTTPError, OSError, ValueError):
                                pass
                        if not self._is_valid_json(text):
                            last_err = "JSON không hợp lệ"
                            break
                return text
            log.warning("LLM lỗi (prompt %s): %s", self._hash(prompt)[:8], last_err)
            return ""

    async def agenerate(self, prompts: list[str], *, json_schema: dict | None = None,
                        max_tokens: int = 512, thinking: bool = False) -> list[str]:
        """Sinh cho nhiều prompt, trả kết quả **đúng thứ tự input**.

        Client HTTP chỉ sống trong một lượt gọi: giữ ``AsyncClient`` qua
        nhiều ``asyncio.run`` khiến pool dính loop đã đóng ("Event loop is
        closed") — lỗi chập chờn đã làm sập đường path1 ở benchmark.
        """
        if not prompts:
            return []
        client = httpx.AsyncClient(timeout=self.timeout_s)
        prev, self._client = self._client, client
        try:
            sem = asyncio.Semaphore(self.concurrency)
            tasks = [
                self._one(i, p, json_schema, max_tokens, thinking, sem)
                for i, p in enumerate(prompts)
            ]
            return list(await asyncio.gather(*tasks))
        finally:
            self._client = prev
            try:
                await client.aclose()
            except Exception:  # noqa: BLE001 - dọn dẹp, không che lỗi chính
                pass

    def generate(self, prompts: list[str], **kw: Any) -> list[str]:
        """Bọc đồng bộ quanh ``asyncio.run``."""
        return asyncio.run(self.agenerate(prompts, **kw))


class AsyncLLM(LLM):
    """Biến thể cho tình huống đã có event loop."""

    async def generate_async(self, prompts: list[str], **kw: Any) -> list[str]:
        return await self.agenerate(prompts, **kw)


def build_client(cfg: Any = config) -> LLM:
    """Trả về client thật nếu có cấu hình, không thì client offline (trả '')."""
    llm = LLM(cfg)
    if not llm.available:
        log.warning(
            "Không có DATAMATE_LLM_BASE_URL — LLM sẽ trả chuỗi rỗng cho mọi prompt."
        )
    return llm


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def env_flag(name: str) -> bool:
    return os.environ.get(name, "").lower() in ("1", "true", "yes")


def now() -> float:
    return time.time()


__all__ = ["LLM", "AsyncLLM", "build_client", "sha256_text", "env_flag", "now"]
