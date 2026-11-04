"""Client OpenAI-compatible + retry/backoff (EXECUTION-PLAN.md §8.3).

Hết số lần retry ⇒ trả `None` (chat) hoặc `""` (transcribe); **không ném lỗi ra ngoài**.
"""
import time


class ApiClient:
    def __init__(self, base_url: str, api_key: str, timeout: int = 60, max_retries: int = 5):
        self.base_url = base_url
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries
        self._client = None
        self._last_error = None
        if base_url:
            try:
                from openai import OpenAI
            except ImportError:  # pragma: no cover - thiếu phụ thuộc
                OpenAI = None
            if OpenAI is not None:
                self._client = OpenAI(
                    base_url=base_url,
                    api_key=api_key or "EMPTY",
                    timeout=timeout,
                    max_retries=0,
                )

    @property
    def available(self) -> bool:
        return self._client is not None

    @property
    def last_error(self):
        return self._last_error

    def _sleep_backoff(self, attempt: int):
        delay = min(2 ** attempt, 30)
        time.sleep(delay)

    def chat(self, model, messages, tools=None, temperature=0, max_tokens=512, extra_body=None, log=None):
        """Trả dict message của assistant, hoặc None nếu lỗi hết retry."""
        if self._client is None:
            self._last_error = "ApiClient chưa có base_url"
            if log is not None:
                log.append({"api_error": self._last_error})
            return None
        kwargs = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        if extra_body:
            kwargs["extra_body"] = extra_body
        last_err = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = self._client.chat.completions.create(**kwargs)
                return resp.choices[0].message
            except Exception as e:  # noqa: BLE001 - mọi lỗi đều phải được nuốt
                last_err = f"{type(e).__name__}: {e}"
                self._last_error = last_err
                if log is not None:
                    log.append({"api_error": last_err, "attempt": attempt})
                if attempt >= self.max_retries:
                    break
                self._sleep_backoff(attempt)
        return None

    def transcribe(self, model, wav_bytes, language="vi", temperature=0, prompt=None, log=None):
        """STT (không dùng ở MVP). Trả chuỗi rỗng nếu lỗi hết retry."""
        if self._client is None:
            self._last_error = "ApiClient chưa có base_url"
            return ""
        last_err = None
        for attempt in range(self.max_retries + 1):
            try:
                kwargs = {"model": model, "file": wav_bytes, "language": language, "temperature": temperature}
                if prompt:
                    kwargs["prompt"] = prompt
                resp = self._client.audio.transcriptions.create(**kwargs)
                return getattr(resp, "text", "") or ""
            except Exception as e:  # noqa: BLE001
                last_err = f"{type(e).__name__}: {e}"
                self._last_error = last_err
                if log is not None:
                    log.append({"asr_error": last_err, "attempt": attempt})
                if attempt >= self.max_retries:
                    break
                self._sleep_backoff(attempt)
        return ""
