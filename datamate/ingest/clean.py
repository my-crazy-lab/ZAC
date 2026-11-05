"""Làm sạch dữ liệu thô (EXECUTION-MVP.md M1).

Các hàm ở đây thuần theo kiểu dữ liệu: nhận Series/DataFrame, trả Series/DataFrame.
Không biết gì về nghiệp vụ — việc đó thuộc tầng M4.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from datetime import date, datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

EXCEL_EPOCH = date(1899, 12, 30)

# --------------------------------------------------------------------- chuỗi

def nfc(s: str) -> str:
    """Chuẩn hoá Unicode NFC."""
    return unicodedata.normalize("NFC", s)


def strip_diacritics(s: str) -> str:
    """Bỏ dấu tiếng Việt (đ → d), giữ ASCII gốc."""
    out = "".join(
        ch for ch in unicodedata.normalize("NFD", s)
        if unicodedata.category(ch) != "Mn"
    )
    return out.replace("đ", "d").replace("Đ", "D")


def nd(s: str) -> str:
    """Chuẩn hoá so khớp: NFC → bỏ dấu → lower → gộp khoảng trắng."""
    s = strip_diacritics(nfc(str(s))).lower()
    return " ".join(s.split())


# ------------------------------------------------------------------- số học

_NUM_CLEAN_RE = re.compile(r"[đ₫\s]|\bvnd\b", re.IGNORECASE)
_SUFFIX_RE = re.compile(r"^\s*(-?[\d.,]+)\s*([a-zA-Zàáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơớợỡợùúủũụưừứửữựỳýỷỹỵ]*)\s*$")
_THOUSANDS_DOT_RE = re.compile(r"^\d{1,3}(\.\d{3})+(,\d+)?$")
_THOUSANDS_COMMA_RE = re.compile(r"^\d{1,3}(,\d{3})+(\.\d+)?$")

_SUFFIX_MULT = {
    "k": 1e3,
    "ng": 1e3,
    "nghin": 1e3,
    "tr": 1e6,
    "trieu": 1e6,
    "t": 1e6,
    "ty": 1e9,
    "tỷ": 1e9,
    "b": 1e9,
    "m": 1e6,
    "l": 1e3,
}


def _strip_suffix(txt: str) -> tuple[str, float]:
    m = _SUFFIX_RE.match(txt)
    if not m:
        return txt, 1.0
    num, suf = m.group(1), nd(m.group(2))
    mult = 1.0
    for key, val in _SUFFIX_MULT.items():
        if suf.startswith(key):
            mult = val
            break
    return num, mult


def parse_number_series(s: pd.Series) -> pd.Series:
    """Parse cột số theo quy ước tiền Việt; quyết định theo **cả cột**."""
    if s is None:
        return pd.Series(dtype="float64")
    if pd.api.types.is_bool_dtype(s):
        return s.astype("float64")
    if pd.api.types.is_numeric_dtype(s):
        return pd.to_numeric(s, errors="coerce")

    raw = s.astype("object").where(s.notna(), None)
    cleaned = raw.map(lambda v: _NUM_CLEAN_RE.sub("", str(v)) if v is not None else None)
    nonnull = [str(v) for v in cleaned if v is not None and str(v).strip() != ""]
    if not nonnull:
        return pd.Series([np.nan] * len(s), index=s.index, dtype="float64")


    def _one(v: Any) -> float:
        if v is None:
            return np.nan
        txt = str(v).strip()
        if txt == "" or txt.lower() in ("nan", "none", "null", "-"):
            return np.nan
        num_txt, mult = _strip_suffix(txt)
        num_txt = num_txt.replace(" ", "")
        # 1) dấu chấm là dấu phân cách nghìn (1.500 / 1.500,5)
        if _THOUSANDS_DOT_RE.match(num_txt):
            num_txt = num_txt.replace(".", "")
            num_txt = num_txt.replace(",", ".")
        # 2) dấu phẩy là dấu phân cách nghìn (1,500 / 1,500.5)
        elif _THOUSANDS_COMMA_RE.match(num_txt):
            num_txt = num_txt.replace(",", "")
        # 3) có cả hai dấu ⇒ dấu cuối cùng là dấu thập phân
        elif "." in num_txt and "," in num_txt:
            if num_txt.rfind(",") > num_txt.rfind("."):
                num_txt = num_txt.replace(".", "").replace(",", ".")
            else:
                num_txt = num_txt.replace(",", "")
        # 4) chỉ có dấu phẩy ⇒ thập phân (1,5)
        elif "," in num_txt:
            num_txt = num_txt.replace(",", ".")
        try:
            return float(num_txt) * mult
        except ValueError:
            return np.nan

    return pd.Series([_one(v) for v in cleaned], index=s.index, dtype="float64")


# ------------------------------------------------------------------- ngày

_NUMERIC_ONLY_RE = re.compile(r"^\s*[\d.]+\s*$")
_ISO_RE = re.compile(r"^\s*(\d{4})-(\d{1,2})-(\d{1,2})(?:[ T](\d{1,2}):(\d{2})(?::(\d{2}))?)?")
_VN_RE = re.compile(r"^\s*(\d{1,2})\s*(?:thg|thang)\s*(\d{1,2})\s*(\d{4})(?:[ T](\d{1,2}):(\d{2})(?::(\d{2}))?)?", re.IGNORECASE)
_DMY_RE = re.compile(r"^\s*(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})(?:[ T](\d{1,2}):(\d{2})(?::(\d{2}))?)?")
_MDY_RE = re.compile(r"^\s*(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})(?:[ T](\d{1,2}):(\d{2})(?::(\d{2}))?)?")


def _two_digit_year(y: int) -> int:
    return 2000 + y if y < 100 else y


def _excel_serial_to_date(v: float) -> date:
    return EXCEL_EPOCH + timedelta(days=float(v))


def parse_date_series(s: pd.Series) -> pd.Series:
    """Parse cột ngày; quyết định dd/mm vs mm/dd theo **cả cột**."""
    if s is None:
        return pd.Series(dtype="object")
    vals = [v for v in s.tolist() if v is not None and str(v).strip() != ""]
    if not vals:
        return pd.Series([None] * len(s), index=s.index, dtype="object")

    # Excel serial: cột thuần số trong khoảng 20000..60000
    numeric_vals = [v for v in vals if isinstance(v, (int, float, np.integer, np.floating))
                     and not isinstance(v, bool)]
    if numeric_vals and len(numeric_vals) >= 0.9 * len(vals):
        in_range = [v for v in numeric_vals if 20000 <= float(v) <= 60000]
        if len(in_range) >= 0.9 * len(numeric_vals):
            out = []
            for v in s.tolist():
                if v is None or str(v).strip() == "":
                    out.append(None)
                    continue
                if isinstance(v, (int, float, np.integer, np.floating)) and not isinstance(v, bool):
                    out.append(_excel_serial_to_date(float(v)))
                else:
                    out.append(None)
            return pd.Series(out, index=s.index, dtype="object")

    def _parse_one(v: Any) -> tuple[date | None, bool, int | None, int | None]:
        """Trả (ngày, có_giờ, phần_tử_1, phần_tử_2)."""
        if v is None:
            return None, False, None, None
        if isinstance(v, (pd.Timestamp, datetime, date)):
            d = v.date() if isinstance(v, (pd.Timestamp, datetime)) else v
            return d, isinstance(v, (pd.Timestamp, datetime)), None, None
        txt = str(v).strip()
        if txt == "" or txt.lower() in ("nan", "none", "null"):
            return None, False, None, None
        m = _ISO_RE.match(txt)
        if m:
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            has_time = bool(m.group(4))
            try:
                return date(y, mo, d), has_time, None, None
            except ValueError:
                return None, False, None, None
        m = _VN_RE.match(txt)
        if m:
            d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            has_time = bool(m.group(4))
            try:
                return date(y, mo, d), has_time, None, None
            except ValueError:
                return None, False, None, None
        m = _DMY_RE.match(txt)
        if m:
            a, b, y = int(m.group(1)), int(m.group(2)), _two_digit_year(int(m.group(3)))
            has_time = bool(m.group(4))
            try:
                return date(y, b, a), has_time, a, b
            except ValueError:
                pass
            try:
                return date(y, a, b), has_time, a, b
            except ValueError:
                return None, False, None, None
        m = _MDY_RE.match(txt)
        if m:
            a, b, y = int(m.group(1)), int(m.group(2)), _two_digit_year(int(m.group(3)))
            has_time = bool(m.group(4))
            try:
                return date(y, a, b), has_time, a, b
            except ValueError:
                return None, False, None, None
        return None, False, None, None

    parsed = [_parse_one(v) for v in s.tolist()]

    out: list[Any] = []
    for (d, has_time, a, b) in parsed:
        if d is None:
            out.append(None)
            continue
        if has_time:
            out.append(pd.Timestamp(d))
        else:
            out.append(d)
    return pd.Series(out, index=s.index, dtype="object")


def detect_date_column(s: pd.Series) -> tuple[bool, bool]:
    """Trả (là_cột_ngày, có_giờ)."""
    if s is None or len(s) == 0:
        return False, False
    nonnull = s.dropna()
    if nonnull.empty:
        return False, False
    parsed = parse_date_series(nonnull)
    ok_ratio = float(parsed.notna().sum()) / float(len(nonnull))
    has_time = bool(parsed.map(lambda v: isinstance(v, pd.Timestamp)).any())
    return ok_ratio >= 0.9, has_time


# ------------------------------------------------------------------- bảng

_TOTAL_RE = re.compile(r"^(tong|total|cong|cuong|grand)\b", re.IGNORECASE)


def dedupe_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Tên cột trùng ⇒ hậu tố ``_2``, ``_3``."""
    seen: dict[str, int] = {}
    cols: list[str] = []
    for c in df.columns:
        name = str(c).strip()
        if name in seen:
            seen[name] += 1
            name = f"{name}_{seen[name]}"
        else:
            seen[name] = 1
        cols.append(name)
    out = df.copy()
    out.columns = cols
    return out


def _is_total_row(row: pd.Series) -> bool:
    """Dòng tổng ("Tổng ngày 30/06", "Tổng tháng 6/2025") ⇒ bỏ."""
    vals = [v for v in row.tolist()
            if v is not None and not (isinstance(v, float) and pd.isna(v))
            and not (isinstance(v, str) and v.strip() == "")]
    if not vals:
        return True
    labelled = False
    for v in vals:
        if isinstance(v, str):
            s = nd(v)
            if _TOTAL_RE.match(s):
                labelled = True
                break
    if not labelled:
        return False
    # dòng tổng thường chỉ có nhãn + (một) số
    numeric = sum(1 for v in vals if isinstance(v, (int, float))
                  or (isinstance(v, str) and re.fullmatch(r"[\d.,]+", v.strip())))
    return numeric <= 2 and len(vals) <= 4


def find_header_row(df_raw: pd.DataFrame, max_scan: int = 15) -> int:
    """Dòng header: dòng có **nhiều ô chuỗi khác số nhất** trong 15 dòng đầu.

    Quy tắc: dòng hợp lệ khi ≥ 60% ô không rỗng và ≥ 60% ô là chuỗi không
    phải số; chọn dòng có nhiều ô nhất (để bỏ qua dòng tiêu đề nhóm), ưu tiên
    dòng sớm khi hòa.
    """
    if df_raw is None or df_raw.empty:
        return 0
    n_cols = max(1, len(df_raw.columns))
    best: tuple[int, int, int] = (-1, -1, 0)  # (n_nonnull, n_string, -index)
    n = min(max_scan, len(df_raw))
    for i in range(n):
        row = df_raw.iloc[i]
        vals = [c for c in row.tolist()
                if not (c is None or (isinstance(c, float) and pd.isna(c))
                        or (isinstance(c, str) and c.strip() == ""))]
        if not vals:
            continue
        n_nonnull = len(vals)
        if n_nonnull < 0.6 * n_cols:
            continue
        str_cells = [c for c in vals
                     if isinstance(c, str) and not _NUMERIC_ONLY_RE.match(c.strip())]
        if len(str_cells) < 0.6 * n_nonnull:
            continue
        key = (n_nonnull, len(str_cells), -i)
        if key > best:
            best = key
    return -best[2] if best[0] >= 0 else 0


def _avg_null_run_length(s: pd.Series) -> float:
    """Độ dài vệt null trung bình. Ô gộp thành vệt dài (≥1.5); null rải rác ≈ 1."""
    runs: list[int] = []
    cur = 0
    for v in s.isna().tolist():
        if v:
            cur += 1
        elif cur:
            runs.append(cur)
            cur = 0
    if cur:
        runs.append(cur)
    return sum(runs) / len(runs) if runs else 0.0


def forward_fill_group_cols(df: pd.DataFrame) -> pd.DataFrame:
    """Ô gộp: forward-fill cột có null thành vệt (nhóm lặp HOẶC mã đơn nhất).

    Điều kiện cũ (giá trị lặp ≥50%) bỏ sót mã đơn nhiều dòng vì mã nào cũng
    khác nhau. Điều kiện vệt null (dài trung bình ≥1.5) bắt đúng ô gộp mà vẫn
    tha cột thưa rải rác (vệt dài ≈ 1).
    """
    if df is None or df.empty:
        return df
    out = df.copy()
    for col in out.columns:
        s = out[col]
        null_ratio = float(s.isna().sum()) / float(len(s)) if len(s) else 0.0
        if null_ratio < 0.30:
            continue
        vals = s.dropna()
        if vals.empty:
            continue
        # giá trị không null lặp lại?
        counts = vals.astype(str).value_counts()
        repeated = not (len(counts) > 1 and counts.iloc[0] / len(vals) < 0.5)
        # ...hoặc null thành vệt dài (ô gộp khối)?
        merged_runs = _avg_null_run_length(s) >= 1.5
        if not (repeated or merged_runs):
            continue
        out[col] = s.ffill()
    return out


def clean_table(df_raw: pd.DataFrame, header_row: int | None) -> pd.DataFrame:
    """Chuẩn hoá bảng thô: header, tên cột, dòng rỗng, dòng tổng, trùng lặp.

    ``header_row=None`` ⇒ bảng **đã có** tên cột (ví dụ đọc từ SQLite).
    """
    if df_raw is None or df_raw.empty:
        return pd.DataFrame()
    df = df_raw.copy()
    if header_row is not None and header_row >= 0 and header_row < len(df):
        header_values = [str(v).strip() if v is not None else "" for v in df.iloc[header_row].tolist()]
        df = df.iloc[header_row + 1:].reset_index(drop=True)
        df.columns = header_values
    df.columns = [str(c).strip() for c in df.columns]
    df = df.loc[:, [c for c in df.columns if c != ""]]
    df = dedupe_columns(df)
    # bỏ dòng toàn rỗng
    df = df.dropna(how="all").reset_index(drop=True)
    # bỏ dòng "tổng"
    mask = df.apply(lambda r: _is_total_row(r), axis=1) if len(df) else pd.Series(dtype=bool)
    if len(df) and mask.any():
        df = df[~mask].reset_index(drop=True)
    df = forward_fill_group_cols(df)
    # chuẩn hoá chuỗi + thêm cột __nd
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].map(lambda v: nfc(v).strip() if isinstance(v, str) else v)
            df[f"{col}__nd"] = df[col].map(
                lambda v: nd(v) if isinstance(v, str) else (nd(v) if v is not None and not pd.isna(v) else None)
            )
    # trùng dòng: toàn bộ cột trùng VÀ có cột id bị trùng
    df = drop_duplicate_rows(df)
    return df.reset_index(drop=True)


def drop_duplicate_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Bỏ dòng trùng hoàn toàn nếu có ít nhất một cột id bị trùng."""
    if df is None or df.empty:
        return df
    id_like = [c for c in df.columns
               if any(k in nd(str(c)) for k in ("ma ", "mã ", "id", "so ", "số ", "code", "ma_", "mã_"))]
    if not id_like:
        return df
    dup_mask = df.duplicated(keep="first")
    if not dup_mask.any():
        return df
    id_dup = df.duplicated(subset=id_like, keep="first")
    drop_mask = dup_mask & id_dup
    n_drop = int(drop_mask.sum())
    if n_drop:
        log.info("bỏ %d dòng trùng", n_drop)
    return df[~drop_mask].reset_index(drop=True)


def looks_numeric(s: pd.Series) -> bool:
    """Cột có phải số không (>=90% parse được)."""
    nonnull = s.dropna()
    if nonnull.empty:
        return False
    parsed = parse_number_series(nonnull)
    return float(parsed.notna().sum()) / float(len(nonnull)) >= 0.9
