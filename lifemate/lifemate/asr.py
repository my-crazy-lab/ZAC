"""ASR qua STT shim OpenAI-compatible (M2).

Shim nhận `POST /v1/audio/transcriptions` (multipart) và forward tới
Whisper Turbo. Dùng chung `ApiClient.transcribe` (đã kiểm chứng với
đường SDK của `openai`).
"""
from pathlib import Path

from lifemate import config
from lifemate.apiclient import ApiClient


def transcribe_file(wav_path, model=None, language=None, log=None) -> str:
    """Trả transcript (chuỗi có thể rỗng khi lỗi — không ném lỗi ra ngoài)."""
    client = ApiClient(config.STT_BASE_URL, config.STT_API_KEY,
                       timeout=config.STT_TIMEOUT, max_retries=2)
    if not client.available:
        return ""
    try:
        with open(wav_path, "rb") as f:
            text = client.transcribe(model or config.STT_MODEL, f,
                                     language=language or config.STT_LANGUAGE,
                                     log=log)
    except OSError:
        return ""
    return text or ""


def wav_of(split: str, item) -> Path:
    """Đường dẫn file audio lượt cuối của mẫu."""
    rel = (item or {}).get("audio") or ""
    return config.split_dir(split) / rel
