"""Phát hiện archetype của một shop theo **cấu trúc** (không theo business_id).

Mã archetype (EXECUTION-MVP.md §M4.A):
``A_flat`` | ``B_monthly`` | ``C_norm_csv`` | ``D_erp`` | ``E_retail_suite`` |
``G_sqlite`` | ``H_repair`` | ``I_phone`` | ``J_baby`` | ``UNKNOWN``
"""

from __future__ import annotations

import logging
from typing import Any

from text.normalize import nd

log = logging.getLogger(__name__)

ARCHETYPE_CODES = (
    "A_flat", "B_monthly", "C_norm_csv", "D_erp", "E_retail_suite", "G_sqlite",
    "H_repair", "I_phone", "J_baby", "UNKNOWN",
)

# Ngành mới (chỉ có ở public_test): dấu hiệu theo **tên cột**
DOMAIN_COLUMN_SIGNALS: dict[str, tuple[str, ...]] = {
    "H_repair": ("bien so", "xe khach", "bien xe", "loi sua xe", "phuong thuc sua chua",
                 "tac phong", "bien so xe", "mau xe"),
    "I_phone": ("ky gop", "tra gop", "so hop dong", "tai chinh", "thue bao",
                "tra cham", "hoa don ky gop"),
    "J_baby": ("so luong thang tuoi", "thang tuoi", "co so thuong", "mau sac",
               "size quan ao", "nhan et"),
}


def _files(tables: list[Any]) -> list[str]:
    return [nd(str(t.source)).replace("_", " ").replace("-", " ") for t in tables]


def _tables(tables: list[Any]) -> list[str]:
    return [nd(str(t.name)).replace("_", " ").replace("-", " ") for t in tables]


def _all_columns(tables: list[Any]) -> set[str]:
    out: set[str] = set()
    for t in tables:
        for c in t.df.columns:
            if not str(c).endswith("__nd"):
                out.add(nd(str(c)))
    return out


def detect_archetype(tables: list[Any]) -> tuple[str, float]:
    """Trả (mã archetype, độ tin cậy 0..1)."""
    if not tables:
        return "UNKNOWN", 0.0
    files = _files(tables)
    names = _tables(tables)
    cols = _all_columns(tables)
    joined_files = " | ".join(files)
    joined_names = " | ".join(names)

    # --- SQLite
    if any(f.endswith("sqlite") or f.endswith("db") for f in files):
        return "G_sqlite", 1.0

    # --- ngành mới (dấu hiệu cột)
    for code, signals in DOMAIN_COLUMN_SIGNALS.items():
        matched = {s for s in signals if any(s in c for c in cols)}
        # "Biển số xe" là thuộc tính giao hàng của retail, không đủ để kết
        # luận đây là dữ liệu sửa xe. Cần hai tín hiệu khác nhau, trong đó
        # H_repair phải có ít nhất một tín hiệu nghiệp vụ sửa chữa.
        if code == "H_repair":
            strong = {"loi sua xe", "phuong thuc sua chua", "tac phong", "mau xe"}
            if not matched & strong:
                continue
        if len(matched) >= 2:
            return code, min(1.0, 0.5 + 0.2 * len(matched))

    # --- D_erp: nhiều file, có hoá đơn/chi tiết/sản phẩm/khách/nhập/quỹ/tồn
    d_signals = ["hoa don", "chi tiet", "san pham", "khach hang", "nhap hang",
                 "quy", "ton kho"]
    d_hits = sum(1 for s in d_signals if s in joined_files or s in joined_names)
    n_files = len({t.source for t in tables})
    if n_files >= 7 and d_hits >= 5:
        return "D_erp", min(1.0, 0.6 + 0.05 * d_hits)

    # --- E_retail_suite: bán hàng + danh mục/giá + nhập + tồn (+ giao hàng/công nợ)
    e_hits = 0
    for group in (["ban hang", "so ban hang", "bao cao ban hang", "chi tiet ban hang"],
                  ["danh muc", "bang gia", "danh sach hang hoa", "danh sach quy doi"],
                  ["nhap hang", "so nhap hang"],
                  ["ton kho", "bao cao ton kho"]):
        if any(any(g in f for f in files + names) for g in group):
            e_hits += 1
    if e_hits >= 3:
        return "E_retail_suite", min(1.0, 0.5 + 0.12 * e_hits)

    # --- C_norm_csv: don_hang + chi_tiet_don + khach_hang + san_pham
    c_signals = ["don hang", "chi tiet don", "khach hang", "san pham"]
    c_hits = sum(1 for s in c_signals if any(s in f for f in files + names))
    if c_hits >= 3:
        return "C_norm_csv", min(1.0, 0.6 + 0.1 * c_hits)

    # --- B_monthly: một file nhiều sheet + file danh mục/quy đổi
    monthly = 0
    for t in tables:
        if t.sheet and "|" in str(t.sheet):
            monthly = max(monthly, len(str(t.sheet).split("|")))
    has_catalog = any(any(g in f for f in files + names)
                       for g in ("danh muc", "quy doi", "hang hoa", "bang gia", "san pham"))
    if monthly >= 6 and has_catalog:
        return "B_monthly", min(1.0, 0.6 + 0.05 * monthly)
    if monthly >= 6:
        return "B_monthly", 0.6

    # --- A_flat: 1 bảng có qty + giá + ngày + tên hàng
    if n_files <= 2:
        need = [("so luong",), ("gia",), ("ngay",), ("ten", "hang", "san pham", "noi dung")]
        hit = 0
        for group in need:
            if any(any(k in c for k in group) for c in cols):
                hit += 1
        if hit >= 3:
            return "A_flat", min(1.0, 0.5 + 0.1 * hit)

    return "UNKNOWN", 0.3
