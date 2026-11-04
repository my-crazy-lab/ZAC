"""Sandbox SQL: chặn lệnh ghi/xoá và giới hạn thời gian (M5)."""

from __future__ import annotations

import re

FORBIDDEN = re.compile(
    r"\b(attach|copy|install|load|pragma|create|insert|update|delete|drop|alter|"
    r"truncate|replace|export|import)\b",
    re.IGNORECASE,
)
FORBIDDEN_FUNCS = re.compile(r"\b(read_csv|read_parquet|copy_to)\b", re.IGNORECASE)


class SqlRejected(Exception):
    """SQL bị từ chối bởi sandbox."""


def check_sql(sql: str) -> None:
    """Ném ``SqlRejected`` nếu SQL không an toàn."""
    if not sql or not sql.strip():
        raise SqlRejected("SQL rỗng")
    stripped = _strip_comments(sql).strip()
    if not (stripped.upper().startswith("SELECT") or stripped.upper().startswith("WITH")):
        raise SqlRejected("chỉ cho phép SELECT/WITH")
    if FORBIDDEN.search(stripped):
        raise SqlRejected("SQL chứa lệnh bị cấm")
    if FORBIDDEN_FUNCS.search(stripped):
        raise SqlRejected("SQL chứa hàm đọc file bị cấm")
    if ";" in stripped.rstrip(";"):
        raise SqlRejected("không cho phép nhiều câu")


def _strip_comments(sql: str) -> str:
    out = re.sub(r"--[^\n]*", " ", sql)
    out = re.sub(r"/\*.*?\*/", " ", out, flags=re.S)
    return out
