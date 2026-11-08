from types import SimpleNamespace

import pandas as pd

from schema.archetypes import detect_archetype
from schema.mapper import map_business


def _table(name, source, columns, sheet="Sheet1"):
    return SimpleNamespace(name=name, source=source, sheet=sheet,
                           df=pd.DataFrame({c: [1] for c in columns}))


def test_delivery_license_plate_is_not_repair_domain():
    tables = [_table("sobanhang", "SoBanHang.xlsx",
                     ["Ngày bán", "Tên hàng", "Số lượng", "Giá"]),
              _table("sogiaohang", "SoGiaoHang.xlsx",
                     ["Biển số xe", "Mã bill", "Lượt giao"])]
    assert detect_archetype(tables)[0] == "A_flat"


def test_underscore_csv_names_detect_normalized_csv():
    tables = [_table("don_hang", "don_hang.csv", ["Mã chứng từ", "NgayBan"]),
              _table("chi_tiet_don", "chi_tiet_don.csv", ["Ma don", "SL"]),
              _table("san_pham", "san_pham.csv", ["SKU", "Sản phẩm"]),
              _table("khach_hang", "khach_hang.csv", ["ma_kh", "Khách lẻ/sỉ"])]
    assert detect_archetype(tables)[0] == "C_norm_csv"


def test_mapper_recovers_order_id_from_flat_sales_table():
    table = _table("sobanhang", "SoBanHang.xlsx",
                   ["Mã phiếu", "Ngày lập", "Tên SP", "Số lượng hàng",
                    "Giá", "Tiền"])
    table.df["Mã phiếu"] = ["P-1"]
    table.df["Ngày lập"] = ["2026-01-01"]
    table.df["Tên SP"] = ["Sản phẩm"]
    tables = [table]
    readme = """## Cột trong `SoBanHang.xlsx`
- **Mã phiếu**: mã đơn
- **Ngày lập**: ngày bán
- **Tên SP**: tên hàng
- **Số lượng hàng**: số lượng
- **Giá**: đơn giá
- **Tiền**: thành tiền sau giảm
"""
    mapping = map_business(tables, readme)[0].mapping
    assert mapping["entities"]["lines"]["cols"]["order_id"] == "Mã phiếu"
