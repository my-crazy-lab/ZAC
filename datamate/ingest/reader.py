"""Đọc file thô của một shop: CSV / XLSX / SQLite → ``RawTable`` (EXECUTION-MVP.md M1)."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd

from dtypes import Question
from ingest.clean import clean_table, find_header_row

log = logging.getLogger(__name__)

ENCODINGS = ("utf-8-sig", "utf-8", "cp1258", "latin-1")
DELIMS = (",", ";", "\t", "|")


@dataclass
class RawTable:
    name: str
    source: str
    sheet: str | None
    df: pd.DataFrame

    @property
    def columns(self) -> list[str]:
        return [str(c) for c in self.df.columns]


def slugify(name: str) -> str:
    s = re.sub(r"[^0-9a-zA-Z]+", "_", name).strip("_").lower()
    return s or "t"


def _read_csv_raw(path: str) -> pd.DataFrame:
    raw_bytes = open(path, "rb").read()
    text = None
    for enc in ENCODINGS:
        try:
            text = raw_bytes.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
        if "\ufffd" not in text:
            break
    if text is None:
        text = raw_bytes.decode("latin-1", errors="replace")
    head = text[:20000]
    sep = ","
    try:
        import csv as _csv

        dialect = _csv.Sniffer().sniff(head, delimiters="".join(DELIMS))
        sep = dialect.delimiter
    except Exception:
        best, best_score = ",", -1
        for cand in DELIMS:
            counts = [line.count(cand) for line in head.splitlines()[:50] if line.strip()]
            if not counts:
                continue
            mode = max(set(counts), key=counts.count)
            if mode > 0:
                score = counts.count(mode)
                if score > best_score:
                    best, best_score = cand, score
        sep = best
    return pd.read_csv(
        pd.io.common.StringIO(text),
        header=None,
        dtype=object,
        sep=sep,
        engine="python",
        skip_blank_lines=False,
    )


def _read_excel_raw(path: str) -> dict[str, pd.DataFrame]:
    sheets = pd.read_excel(path, sheet_name=None, header=None, dtype=object)
    out: dict[str, pd.DataFrame] = {}
    for name, df in sheets.items():
        if df is None or df.empty:
            continue
        out[str(name)] = df
    return out


def _read_sqlite_raw(path: str) -> dict[str, pd.DataFrame]:
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        names: list[str] = []
        for (nm, typ) in con.execute(
            "SELECT name, type FROM sqlite_master WHERE type IN ('table','view')"
        ).fetchall():
            if str(nm).lower().startswith("sqlite_"):
                continue
            names.append(str(nm))
        out: dict[str, pd.DataFrame] = {}
        for nm in sorted(names):
            try:
                df = pd.read_sql_query(f'SELECT * FROM "{nm}"', con)
            except Exception as exc:  # noqa: BLE001
                log.warning("bỏ bảng sqlite %s: %s", nm, exc)
                continue
            if df is None or df.empty:
                continue
            out[nm] = df
        return out
    finally:
        con.close()


def _table_from_df(name: str, source: str, sheet: str | None,
                    df_raw: pd.DataFrame, detect_header: bool = True) -> RawTable | None:
    header_row = find_header_row(df_raw) if detect_header else None
    df = clean_table(df_raw, header_row)
    if df is None or df.empty:
        return None
    return RawTable(name=name, source=source, sheet=sheet, df=df)


def load_business(path: str) -> list[RawTable]:
    """Đọc toàn bộ file của một shop, trả về danh sách bảng đã làm sạch."""
    if not os.path.isdir(path):
        raise FileNotFoundError(path)
    tables: list[RawTable] = []
    files = sorted(os.listdir(path))
    for fn in files:
        full = os.path.join(path, fn)
        if fn.startswith("."):
            continue
        low = fn.lower()
        if low.endswith(".csv") or low.endswith(".tsv"):
            try:
                df_raw = _read_csv_raw(full)
            except Exception as exc:  # noqa: BLE001
                log.warning("đọc csv lỗi %s: %s", fn, exc)
                continue
            t = _table_from_df(slugify(os.path.splitext(fn)[0]), fn, None, df_raw)
            if t:
                tables.append(t)
        elif low.endswith(".xlsx") or low.endswith(".xlsm") or low.endswith(".xls"):
            try:
                sheets = _read_excel_raw(full)
            except Exception as exc:  # noqa: BLE001
                log.warning("đọc xlsx lỗi %s: %s", fn, exc)
                continue
            base = slugify(os.path.splitext(fn)[0])
            multi = len(sheets) > 1
            for sheet_name, df_raw in sheets.items():
                # Nhiều sheet trong một file phải có **tên bảng khác nhau**;
                # nếu không, bảng cuối cùng sẽ đè bảng đầu trong canonicalize
                # (một file báo cáo có cả sổ bán hàng và bảng giao hàng).
                name = f"{base}__{slugify(str(sheet_name))}" if multi else base
                t = _table_from_df(name, fn, sheet_name, df_raw)
                if t:
                    tables.append(t)
        elif low.endswith(".sqlite") or low.endswith(".db"):
            try:
                raw_tabs = _read_sqlite_raw(full)
            except Exception as exc:  # noqa: BLE001
                log.warning("đọc sqlite lỗi %s: %s", fn, exc)
                continue
            for tab_name, df_raw in raw_tabs.items():
                # SQLite: DataFrame đã có tên cột thật ⇒ không dò header, không bỏ dòng đầu
                t = _table_from_df(f"{slugify(os.path.splitext(fn)[0])}_{slugify(tab_name)}",
                                   fn, tab_name, df_raw, detect_header=False)
                if t:
                    tables.append(t)
        elif low.endswith(".md") or low.endswith(".txt"):
            continue
    return union_monthly_sheets(tables)


def union_monthly_sheets(tables: list[RawTable]) -> list[RawTable]:
    """Gộp các sheet cùng tập cột trong **cùng một file** thành một bảng logic."""
    by_source: dict[str, list[RawTable]] = {}
    for t in tables:
        by_source.setdefault(t.source, []).append(t)

    out: list[RawTable] = []
    for source, group in by_source.items():
        buckets: dict[tuple[str, ...], list[RawTable]] = {}
        for t in group:
            key = tuple(sorted(c for c in t.columns if not c.endswith("__nd")))
            buckets.setdefault(key, []).append(t)
        for key, members in buckets.items():
            if len(members) == 1:
                out.append(members[0])
                continue
            frames = []
            for m in members:
                df = m.df.copy()
                df["__sheet"] = m.sheet or ""
                frames.append(df)
            merged = pd.concat(frames, ignore_index=True)
            name = members[0].name
            out.append(RawTable(name=name, source=source, sheet="|".join(
                str(m.sheet) for m in members), df=merged))
    out.sort(key=lambda t: (t.source, t.name, str(t.sheet)))
    return out


def load_questions(path: str) -> list[Question]:
    """Đọc ``questions.jsonl``."""
    qs: list[Question] = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            qs.append(Question.from_jsonl(obj))
    return qs


def load_answers(path: str) -> dict[str, dict[str, Any]]:
    """Đọc ``answers.jsonl`` thành dict ``{id: {...}}``."""
    out: dict[str, dict[str, Any]] = {}
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            out[str(obj["id"])] = obj
    return out


def data_files(path: str) -> list[str]:
    """Danh sách file dữ liệu (bỏ README, file ẩn) của một shop."""
    out = []
    for fn in sorted(os.listdir(path)):
        if fn.startswith("."):
            continue
        low = fn.lower()
        if low.endswith(".md") or low.endswith(".txt") or low.endswith(".pdf"):
            continue
        out.append(os.path.join(path, fn))
    return out


def cache_key(path: str, schema_version: str) -> str:
    """sha256 nội dung các file dữ liệu (đã sắp theo tên) + SCHEMA_VERSION."""
    h = hashlib.sha256()
    h.update(schema_version.encode("utf-8"))
    for f in data_files(path):
        h.update(os.path.basename(f).encode("utf-8"))
        with open(f, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
    return h.hexdigest()


def to_duckdb(tables: list[RawTable], cache_path: str,
              schema_version: str | None = None) -> str:
    """Ghi các bảng sạch ``t_*`` vào file DuckDB cache (ghi một lần)."""
    import duckdb

    os.makedirs(os.path.dirname(os.path.abspath(cache_path)), exist_ok=True)
    if os.path.exists(cache_path):
        os.remove(cache_path)
    con = duckdb.connect(cache_path)
    try:
        for t in tables:
            name = f"t_{slugify(t.name)}"
            con.register("_df", t.df)
            try:
                con.execute(f'CREATE OR REPLACE TABLE "{name}" AS SELECT * FROM _df')
            finally:
                con.unregister("_df")
    finally:
        con.close()
    return cache_path


def readme_text(path: str) -> str:
    """Đọc README.md của shop (input hợp lệ cho agent)."""
    p = os.path.join(path, "README.md")
    if not os.path.exists(p):
        return ""
    try:
        return open(p, "r", encoding="utf-8", errors="replace").read()
    except OSError:
        return ""


def business_dirs(root: str) -> list[str]:
    """Các thư mục shop trong ``root`` (thường là ``<split>/data``)."""
    if not os.path.isdir(root):
        return []
    out = []
    for name in sorted(os.listdir(root)):
        full = os.path.join(root, name)
        if os.path.isdir(full) and not name.startswith("."):
            out.append(full)
    return out


def parse_iso_date(s: str) -> date:
    return date.fromisoformat(str(s)[:10])
