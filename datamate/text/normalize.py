"""Chuẩn hoá văn bản tiếng Việt (M6): bỏ dấu, viết tắt, khoảng trắng."""

from __future__ import annotations

import json
import os
import re
import unicodedata
from functools import lru_cache

_ABBREV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "abbrev_vi.json")

_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
_WS_RE = re.compile(r"\s+")


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", str(s))


def strip_diacritics(s: str) -> str:
    out = "".join(
        ch for ch in unicodedata.normalize("NFD", str(s))
        if unicodedata.category(ch) != "Mn"
    )
    return out.replace("đ", "d").replace("Đ", "D")


def nd(s: str) -> str:
    """NFC → bỏ dấu → lower → gộp khoảng trắng."""
    s = strip_diacritics(nfc(s)).lower()
    return _WS_RE.sub(" ", s).strip()


def keep_diacritics(s: str) -> str:
    """Chuẩn hoá giữ dấu (dùng khi ghi đáp án)."""
    return _WS_RE.sub(" ", nfc(str(s))).strip()


@lru_cache(maxsize=1)
def _abbrev_table() -> dict[str, str]:
    try:
        with open(_ABBREV_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    out: dict[str, str] = {}
    for k, v in data.items():
        key = nd(k)
        if not key:
            continue
        out[key] = nd(v)
    return out


def expand_abbrev(s_nd: str) -> str:
    """Mở rộng viết tắt trên chuỗi **đã bỏ dấu**.

    Quy tắc: chỉ thay token đứng riêng; token 1 ký tự (``k``) không thay khi
    đứng ngay sau một số (ví dụ ``3k`` là đơn vị nghìn, không phải "không").
    """
    table = _abbrev_table()
    if not table or not s_nd:
        return s_nd
    tokens = s_nd.split()
    out: list[str] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        prev = out[-1] if out else ""
        # bỏ dấu câu ở cuối token ("hqua." → "hqua") khi tra cứu
        clean = tok.strip(".,;:!?()[]\"'")
        repl = None
        # cụm 2 từ ("bua nay" → "hom nay")
        if i + 1 < len(tokens):
            two = f"{clean} {tokens[i + 1].strip('.,;:!?()[]\"')}"
            repl = table.get(two)
            if repl is not None:
                out.append(repl)
                i += 2
                continue
        if repl is None:
            repl = table.get(clean) or table.get(tok)
        if repl is None and len(clean) > 2 and clean.endswith("s"):
            repl = table.get(clean[:-1])
        if repl is None:
            # viết tắt gắn liền ký tự: "dthusp" không xử lý; chỉ "dthu" đã có
            out.append(tok)
            i += 1
            continue
        if len(clean) == 1 and (prev and prev[-1].isdigit()):
            out.append(tok)
            i += 1
            continue
        out.append(repl)
        i += 1
    return " ".join(out)


def tokens_of(s_nd: str) -> list[str]:
    return [t for t in _WS_RE.split(str(s_nd).strip()) if t]


_CAMEL_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_CAMEL_RE2 = re.compile(r"(?<=[A-Z])(?=[A-Z][a-z])")


def split_camel(name: str) -> str:
    """Tách CamelCase: ``MaHoaDon`` → ``Ma Hoa Don`` (dùng cho tên cột SQLite/POS).

    Chỉ dùng quy tắc ASCII để không cắt nhầm tiếng Việt có dấu (``tiền``).
    """
    s = str(name)
    s = _CAMEL_RE.sub(" ", s)
    s = _CAMEL_RE2.sub(" ", s)
    return s


def column_key(name: str) -> str:
    """Chuẩn hoá tên cột để so khớp: bỏ dấu + tách CamelCase."""
    return nd(split_camel(name))


def strip_punct(s: str) -> str:
    return _WS_RE.sub(" ", _PUNCT_RE.sub(" ", nfc(str(s)))).strip()
