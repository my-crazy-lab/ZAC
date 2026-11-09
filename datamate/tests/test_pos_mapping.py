from types import SimpleNamespace

import pandas as pd

from schema.canon import canonicalize
from schema.mapper import map_business


def _t(name, cols):
    return SimpleNamespace(name=name, source=f"{name}.sqlite", sheet=None,
                           df=pd.DataFrame(cols))


TABLES = [
    _t("pos_don_hang", {
        "MaHoaDon": ["ORD1", "ORD2"],
        "MaKhachHang": ["KH1", "KH2"],
        "NgayLap": ["2025-01-01", "2025-01-02"],
        "ThoiGianLap": ["2025-01-01 10:00:00", "2025-01-02 11:00:00"],
        "TinhTrang": ["completed", "returned"],
        "KenhBanHang": ["store", "online"],
        "MaNhanVien": ["NV1", "NV2"],
        "TongThanhToan": [100, 200],
        "ConPhaiThu": [0, 50],
        "KhachDaTra": [100, 150],
        "PhuongThucTT": ["cash", "transfer"],
        "PhiVanChuyen": [0, 0],
    }),
    _t("pos_chi_tiet_don", {
        "MaHoaDon": ["ORD1", "ORD2"],
        "SoThuTu": [1, 1],
        "MaHangHoa": ["SP1", "SP2"],
        "DonViTinh": ["hộp", "hộp"],
        "SL": [2, 3],
        "SLQuyDoi": [2, 3],
        "GiaDonVi": [50, 60],
        "TriGia": [100, 200],
        "GiaVonLucBan": [10, 20],
        "ChietKhau": [0, 0],
    }),
    _t("pos_khach_hang", {
        "MaKhachHang": ["KH1", "KH2"],
        "TenGoi": ["An", "Binh"],
        "LoaiKhachHang": ["lẻ", "sỉ"],
        "SoDienThoai": ["0901", "0902"],
    }),
    _t("pos_san_pham", {
        "MaHangHoa": ["SP1", "SP2"],
        "TenGoi": ["Panadol", "Efferalgan"],
        "DanhMuc": ["giảm đau", "giảm đau"],
        "DonViCoSo": ["hộp", "hộp"],
        "GiaVonHang": [10, 20],
    }),
    _t("pos_the_kho", {
        "MaHangHoa": ["SP1"],
        "NgayGioPhatSinh": ["2025-01-01"],
        "TonCuoi": [5],
    }),
    _t("pos_thanh_toan", {
        "MaPhieuThu": ["PT1"],
        "MaHoaDon": ["ORD1"],
        "NgayGioThu": ["2025-01-01"],
        "SoTienThu": [50],
        "PhuongThuc": ["cash"],
    }),
    _t("pos_phieu_nhap", {
        "MaPhieuNhap": ["PN1"],
        "NgayNhapKho": ["2025-01-01"],
        "TongGiaTriNhap": [100],
        "TinhTrang": ["completed"],
    }),
    _t("pos_chi_tiet_nhap", {
        "MaPhieuNhap": ["PN1"],
        "MaHangHoa": ["SP1"],
        "SLNhapQuyDoi": [5],
        "DonGiaNhap": [10],
    }),
]


def _mapping():
    return map_business(TABLES, "", None)[0].mapping


def test_pos_mapping_uses_display_names_and_status():
    ent = _mapping()["entities"]
    assert ent["orders"]["cols"]["customer_key"] == "MaKhachHang"
    assert ent["orders"]["cols"]["status_raw"] == "TinhTrang"
    assert ent["orders"]["cols"]["order_date"] == "NgayLap"
    assert ent["customers"]["cols"]["customer_name"] == "TenGoi"
    assert ent["customers"]["cols"]["customer_group"] == "LoaiKhachHang"
    assert ent["products"]["cols"]["product_name"] == "TenGoi"
    assert ent["products"]["cols"]["category"] == "DanhMuc"
    assert ent["products"]["cols"]["unit_cost"] == "GiaVonHang"
    assert ent["lines"]["cols"]["unit_cost"] == "GiaVonLucBan"
    assert ent["lines"]["table"] == "pos_chi_tiet_don"
    assert "inventory" in ent and "payments" in ent


def test_pos_canonical_cost_customer_status_inventory_payments():
    mapping = _mapping()
    canon = canonicalize(TABLES, mapping, "G_sqlite", "")
    lines = canon["c_lines"].sort_values("order_id")
    assert list(lines["line_cost_total"]) == [20, 60]
    orders = canon["c_orders"].sort_values("order_id")
    assert list(orders["status_raw"]) == ["completed", "returned"]
    assert bool(orders.loc[orders["order_id"] == "ORD2", "is_returned"].iloc[0])
    customers = canon["c_customers"].set_index("customer_key")
    assert customers.loc["KH1", "customer_name"] == "An"
    assert customers.loc["KH2", "customer_group"] == "sỉ"
    products = canon["c_products"].set_index("product_code")
    assert products.loc["SP1", "product_name"] == "Panadol"
    assert products.loc["SP1", "category"] == "giảm đau"
    assert len(canon["c_inventory"]) == 1
    assert len(canon["c_payments"]) == 1
    assert canon["c_payments"]["customer_key"].iloc[0] == "KH1"
