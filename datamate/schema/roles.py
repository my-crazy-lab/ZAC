"""Từ điển role: ánh xạ cột thô → cột canonical của ``c_*`` (M4).

Namespace duy nhất là **tên cột canonical** (EXECUTION-MVP.md §4.1).
Mỗi role có:
- ``tokens``   : các cách viết tên cột / mô tả trong README (không dấu);
- ``kind``     : kiểu dữ liệu kỳ vọng (dùng cho VALUE_TESTS);
- ``entity``   : bảng canonical mà role thuộc về.

Token dài hơn được ưu tiên khi trùng điểm (ví dụ "số lượng đã đổi ra đơn vị
cơ bản" ⇒ ``qty_base`` chứ không phải ``qty``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from rapidfuzz import fuzz

# Từ quá chung — không dùng làm tín hiệu mạnh
GENERIC_TOKENS = {
    "ma", "so", "ten", "ngay", "gia", "tien", "hang", "hoa", "don", "khach",
    "ttm", "stt", "ncc", "dvt",
    "muc", "dien", "trang", "thai", "mau", "xuat", "nhap", "ban", "chiet",
    "khau", "giam", "thue", "phi", "sl", "tt", "ttm", "stt", "thu", "canh",
    "mo", "n", "tu", "den", "va", "cac", "moi", "loi", "gia tri", "don vi",
    "so luong", "le", "cua", "co", "khong", "theo", "trong", "tai", "vao",
    "khach hang", "don hang", "hang hoa", "san pham",
}


@dataclass
class RoleDef:
    name: str
    tokens: list[str]
    kind: str
    entity: str
    required: bool = False


def _r(name: str, tokens: str, kind: str, entity: str, required: bool = False) -> RoleDef:
    return RoleDef(name=name, tokens=[t.strip() for t in tokens.split("|") if t.strip()],
                   kind=kind, entity=entity, required=required)


# --------------------------------------------------------------- định nghĩa

ROLE_DEFS: list[RoleDef] = [
    # ---- đơn hàng
    _r("order_id", "ma don|ma hoa don|so hoa don|ma chung tu|so chung tu|ma phieu"
       "|ma don hang|ma giao dich|id don|ma hdd|ma bill|ma don hang", "id", "orders", True),
    _r("order_date", "ngay ban|ngay dat hang|ngay giao dich|ngay hoa don|ngay hdd|ngay dat"
       "|ngay thang|ngay cua don|ngay tao don|ngay cua phieu|ngay dat hang"
       "|ngay lap|ngay lap hoa don", "date", "orders", True),
    _r("order_ts", "thoi diem dat don|thoi gian dat don|thoi gian tao don|gio tao don"
       "|gio dat don|thoi gian|gio ban|gio giao dich", "ts", "orders"),
    _r("status_raw", "trang thai don|trang thai don hang|trang thai|xu ly|ket qua"
       "|trang thai xu ly|status|trang thai giao dich|trang thai hdd"
       "|tinh trang|tinh trang don", "str", "orders"),
    _r("customer_name", "ten khach|khach hang|doi tac|ben mua|khach le si|ho ten khach"
       "|ten khach hang|khach le|ten khach thanh vien|ten goi", "str", "orders"),
    _r("customer_key", "ma khach|so kh|ma khach hang|ma so khach|code khach hang", "id", "orders"),
    _r("channel", "kenh ban|nguon ban|ban qua|kenh|kenh ban hang", "str", "orders"),
    _r("pay_method", "hinh thuc thanh toan|phuong thuc thanh toan|phuong thuc tt"
       "|hinh thuc tt|phuong thuc|loai thanh toan", "str", "orders"),
    _r("employee", "ma nhan vien ban|nhan vien ban|nguoi tao|tho lam phieu|ho ten tho"
       "|nguoi giao hang|nhan vien|ma nv ban", "str", "orders"),
    _r("order_total", "tong tien don|tong bill|tong don|tong tien hang cua ca don"
       "|khach phai tra cho ca don|tong gia tri don|tong cua don|tong tien"
       "|tong thanh toan|tong gia tri", "money", "orders"),
    _r("shipping_fee", "phi giao hang|phi ship|phi giao|phi van chuyen", "money", "orders"),
    _r("vat_amount", "thue vat|tien thue", "money", "orders"),
    _r("vat_rate", "thue suat vat|muc thue|thue suat|ty le vat", "num", "orders"),
    _r("order_voucher", "giam gia cua ca don|voucher|ma giam gia|dung diem|tien giam"
       "|khuyen mai don", "money", "orders"),
    _r("order_debt_total", "con no|con lai|cong no|du no|so khach con no|chua tra"
       "|phai thu|no cua don|khach con no cua don", "money", "orders"),
    _r("order_paid", "da thanh toan|khach da tra|khach tra|da thu|tien da tra"
       "|khach da tra cho ca don", "money", "orders"),

    # ---- dòng bán
    _r("line_no", "so thu tu dong trong don|so thu tu dong trong phieu|so thu tu dong"
       "|thu tu|stt|so thu tu", "num", "lines"),
    _r("product_code", "ma hang hoa|ma san pham|ma hang|id sp|sku|ma sp|barcode"
       "|ma hh lien quan", "id", "lines"),
    _r("product_name", "ten hang hoa|ten san pham|ten san pham ban|ten hang|ten mon"
       "|noi dung|mat hang|ten hh|hang ban|ten mat hang|san pham|ten hoa"
       "|ten sp|ten sp ban|ten goi", "str", "lines", True),
    _r("qty", "so luong|sl", "num", "lines", True),
    _r("qty_base", "so luong da doi ra don vi co ban|so luong quy doi|quy ra don vi le"
       "|quy ra dv le|sl quy doi|so luong don vi co ban|so luong ban lay tu lo"
       "|so luong nhap don vi co ban|so luong le", "num", "lines"),
    _r("unit_name", "don vi tinh|don vi ban|don vi nhap|dv nhap|don vi lon"
       "|don vi cua dong", "str", "lines"),
    _r("unit_price", "don gia|gia don vi|gia ban hien tai|gia le|gia ban|gia nhap"
       "|gia ap dung tu ngay do|gia don vi la gia nhap", "money", "lines"),
    _r("line_discount", "giam gia|chiet khau|khau tru|tien giam cua ca dong", "money", "lines"),
    _r("line_amount", "thanh tien sau giam|thanh tien|tong tien|tri gia|t.tien"
       "|gia tri dong|tong thanh tien", "money", "lines", True),
    _r("line_cost_total", "tong gia von|gia von ca dong|thanh tien von|gia von", "money", "lines"),
    _r("return_flag", "co tra hang|tra hang|hoan hang", "flag", "lines"),
    _r("return_qty", "so luong khach tra lai|so luong tra|sl tra hang|so luong hoan"
       "|so luong hoan tra", "num", "lines"),
    _r("size", "size|kich co", "str", "lines"),

    # ---- danh mục hàng
    _r("category", "nhom hang hoa|nhom hang|nhom san pham|loai hang hoa|hang muc"
       "|loai san pham|nhom|danh muc", "str", "products"),
    _r("unit", "don vi co ban|don vi goc|don vi chuan|don vi le|don vi co so",
       "str", "products"),
    _r("unit_cost", "gia von danh muc|gia von co ban|gia von hang hoa|gia von hang"
       "|gia von don vi co ban|gia von luc ban|gia von don vi|gia von mot don vi",
       "money", "products"),

    # ---- khách hàng
    _r("phone", "so dien thoai|dien thoai|sdt|phone", "str", "customers"),
    _r("customer_group", "nhom khach hang|nhom khach|loai hinh khach|phan loai khach"
       "|khach le si|loai khach hang|loai khach", "str", "customers"),
    _r("customer_since", "ngay dang ky|ngay tao khach|ngay tao mat hang|tu ngay", "date", "customers"),

    # ---- thanh toán
    _r("pay_date", "thoi diem thu|ngay thu|thoi gian thu|ngay nhan tien|ngay ghi no"
       "|ngay thanh toan|ngay gio thu", "date", "payments", True),
    _r("pay_amount", "so tien thu|so tien tien|gia tri thu|gia tri", "money", "payments", True),
    _r("pay_ref", "ma phieu thu|so phieu thu|ma bien nhan|ma phieu", "id", "payments"),

    # ---- lô / tồn kho
    _r("lot_id", "so lo|ma lo|lot id", "id", "lots"),
    _r("lot_date", "ngay lo|ngay san xuat|ngay nhap|ngay het han lot", "date", "lots"),
    _r("lot_qty", "so luong lo|sl lot|ton lo|so luong con", "num", "lots"),
    _r("lot_cost", "gia von lot|gia nhap lot|gia von", "money", "lots"),
    _r("expiry_date", "han su dung|hsd|han dung|ngay het han", "date", "lots"),
    _r("inv_date", "ngay ton|ngay bao cao|ngay kiem ke|ngay ton kho|ngay cuoi ky"
       "|ngay gio phat sinh|ngay phat sinh", "date", "inventory"),
    _r("inv_qty", "ton cuoi ky|ton cuoi|ton kho|ton thuc|so luong ton|ton tai thoi diem",
       "num", "inventory"),

    # ---- nhập hàng
    _r("import_id", "ma phieu nhap|so phieu nhap|ma nhap hang|so nhap hang|ma phieu|so phieu", "id", "imports"),
    _r("import_date", "ngay phieu|ngay nhap hang|ngay nhap", "date", "imports", True),
    _r("import_amount", "tong tien phieu nhap|tong tien cua ca phieu|tong tien phieu"
       "|tien nhap cua ca dong|tong tien cua phieu|can tra ncc", "money", "imports"),
    _r("import_status", "trang thai phieu nhap|trang thai phieu|tinh trang", "str", "imports"),
    _r("supplier", "nha cung cap|ma nha cung cap|ncc|nha sx", "str", "imports"),

    # ---- quy đổi đơn vị
    _r("unit_factor", "he so|ty le quy doi|ti le quy doi|quy doi|so quy doi", "num", "units", True),
    _r("base_unit", "don vi co ban|don vi goc|don vi le", "str", "units"),

    # ---- giá
    _r("ph_old", "gia cu|gia truoc|gia truoc lan doi gia", "money", "price_history"),
    _r("ph_new", "gia moi|gia ban ap dung tu ngay do|gia sau", "money", "price_history"),
    _r("ph_date", "ngay ap dung|ngay bat dau ap dung gia|tu ngay", "date", "price_history"),

    # ---- trả hàng / giao hàng
    _r("del_date", "ngay giao|ngay giao hang|ngay van chuyen", "date", "deliveries"),
    _r("del_round", "dot giao|luot giao", "str", "deliveries"),
]

# Vai trò có thể nằm trong bảng "dòng bán" (bảng phẳng, bảng chi tiết)
LINES_EXTRA_ROLES = ("order_id",)

ENTITY_ROLES: dict[str, tuple[str, ...]] = {
    "lines": ("order_id", "line_no", "product_code", "product_name", "qty", "qty_base", "unit_name",
              "unit_price", "line_discount", "line_amount", "line_cost_total", "unit_cost",
              "return_flag", "return_qty", "size"),
    "orders": ("order_id", "order_date", "order_ts", "status_raw", "customer_name",
               "customer_key", "channel", "pay_method", "employee", "order_total",
               "shipping_fee", "vat_amount", "vat_rate", "order_voucher",
               "order_debt_total", "order_paid"),
    "products": ("product_code", "product_name", "category", "unit", "unit_cost"),
    "customers": ("customer_key", "customer_name", "phone", "customer_group",
                  "customer_since"),
    "payments": ("order_id", "customer_key", "pay_date", "pay_amount", "pay_method",
                 "pay_ref"),
    "units": ("product_code", "product_name", "unit_name", "unit_factor", "base_unit"),
    "imports": ("import_id", "import_date", "import_amount", "import_status",
                "supplier", "product_code", "product_name", "qty", "qty_base",
                "unit_name", "unit_price", "line_amount"),
    "inventory": ("product_code", "product_name", "inv_date", "inv_qty", "unit_name"),
    "lots": ("lot_id", "product_code", "product_name", "lot_date", "lot_qty",
             "lot_cost", "expiry_date"),
    "price_history": ("product_code", "product_name", "ph_date", "ph_old", "ph_new"),
    "deliveries": ("order_id", "del_date", "del_round", "employee", "qty"),
    "returns": ("order_id", "product_code", "return_qty", "return_flag", "order_date"),
}

# Vai trò bắt buộc của từng thực thể: mỗi nhóm là "một trong các vai trò"
ENTITY_REQUIRED: dict[str, tuple[tuple[str, ...], ...]] = {
    "lines": (("qty",), ("product_name", "product_code")),
    "orders": (("order_id",), ("order_date", "order_ts")),
    "products": (("product_name",),),
    "customers": (("customer_name",),),
    "payments": (("pay_date",), ("pay_amount",)),
    "units": (("unit_factor",), ("base_unit", "unit_name")),
    "imports": (("import_date",),),
    "inventory": (("inv_date",), ("inv_qty",)),
    "lots": (("lot_id",), ("expiry_date",)),
    "price_history": (("ph_old",), ("ph_new",)),
    "deliveries": (("del_date",),),
}


def roles_by_entity(entity: str) -> list[RoleDef]:
    names = ENTITY_ROLES.get(entity, ())
    out = []
    for r in ROLE_DEFS:
        if r.name in names:
            out.append(r)
    return out


def role_by_name(name: str) -> RoleDef | None:
    for r in ROLE_DEFS:
        if r.name == name:
            return r
    return None


# ------------------------------------------------------------- chấm điểm

def name_match(tokens: list[str], query_nd: str) -> tuple[float, int]:
    """Trả (điểm 0..1, số từ của token khớp) — token dài hơn được ưu tiên.

    Khớp mạnh khi **cụm từ** của token xuất hiện liên tiếp trong query (tên cột
    + mô tả README); nếu chỉ trùng rời rạc thì điểm bị trừ mạnh.
    """
    if not query_nd:
        return 0.0, 0
    qwords = set(query_nd.split())
    best = 0.0
    best_len = 0
    for tok in tokens:
        t = " ".join(str(tok).lower().split())
        if not t:
            continue
        twords = t.split()
        n_words = len(twords)
        if t in query_nd:
            sc = 1.0
        else:
            cov = sum(1 for w in twords if w in qwords) / n_words
            if cov <= 0:
                continue
            if n_words == 1 and t in GENERIC_TOKENS:
                cov = min(cov, 0.5)
            pr = fuzz.partial_ratio(query_nd, t) / 100.0
            sc = pr * (0.2 + 0.4 * cov)
        if sc > best or (abs(sc - best) < 1e-9 and n_words > best_len):
            best, best_len = sc, n_words
    return best, best_len


def name_score(tokens: list[str], query_nd: str) -> float:
    return name_match(tokens, query_nd)[0]


def value_score(kind: str, profile: dict[str, Any]) -> float:
    """Điểm khớp kiểu dữ liệu (VALUE_TESTS)."""
    nonnull = profile.get("n_nonnull", 0)
    if nonnull == 0:
        return 0.0
    num_ratio = profile.get("num_ratio", 0.0)
    date_ratio = profile.get("date_ratio", 0.0)
    ts_ratio = profile.get("ts_ratio", 0.0)
    str_ratio = profile.get("str_ratio", 0.0)
    distinct = profile.get("n_distinct", 0)
    rows = max(1, profile.get("n_rows", 1))
    distinct_ratio = distinct / rows

    if kind in ("num", "money"):
        return num_ratio
    if kind == "date":
        return date_ratio
    if kind == "ts":
        return ts_ratio
    if kind == "id":
        return str_ratio * min(1.0, 0.4 + distinct_ratio)
    if kind == "str":
        return str_ratio
    if kind == "flag":
        return str_ratio * (1.0 if distinct <= 8 else 0.4)
    return 0.0


def score_column(role: RoleDef, name_nd: str, profile: dict[str, Any],
                 desc_nd: str = "") -> tuple[float, int, float]:
    """score = 0.6*name_score + 0.4*value_score; trả kèm độ dài token và name_score.

    ``name_score`` được trả riêng để mapper **bắt buộc** tên phải khớp mạnh
    (nếu không thì mọi cột ngày sẽ khớp mọi vai trò ngày).

    Khớp trên **tên cột** được ưu tiên hơn khớp trên mô tả README: khớp tên
    được điểm 1.0, khớp mô tả được 0.9 (tránh việc ngoặc giải thích trong mô
    tả "tên hàng (file chỉ có mặt hàng có đơn vị lớn)" làm sai vai trò).
    """
    ns_name, nlen_name = name_match(role.tokens, name_nd)
    full = f"{name_nd} {desc_nd}".strip()
    ns_full, nlen_full = name_match(role.tokens, full)
    if ns_name >= ns_full:
        ns, nlen = ns_name, nlen_name
    else:
        ns, nlen = 0.9 * ns_full, nlen_full
    vs = value_score(role.kind, profile)
    return 0.6 * ns + 0.4 * vs, nlen, ns
