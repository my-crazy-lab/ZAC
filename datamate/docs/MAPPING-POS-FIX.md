# POS/SQLite mapping fix (dev_006)

## Triệu chứng

Public leaderboard: `dev_006` có 29 câu trả lời và **-0.029** (gần như sai toàn bộ),
dù `schema_conf` cũ là 0.95.

## Nguyên nhân gốc

| Lỗi | Bằng chứng |
|---|---|
| Tên khách lấy cột loại | `customer_name = LoaiKhachHang` → `v_customers` trả `"lẻ"/"thân thiết"` |
| Không có khoá khách trên đơn | `orders.customer_name = MaKhachHang`, `customer_key` rỗng |
| Mất trạng thái | `TinhTrang` không map → `status_raw=NULL`, `is_cancelled=False` toàn bộ |
| Mất sản phẩm | `pos_san_pham` không map → `v_lines.product_name=NULL`, `category=NULL` |
| Mất tồn kho | `the_kho` không map → `v_inventory=0` |
| Mất thanh toán | `thanh_toan` không map → `v_payments=0` |
| Sai giá vốn | `GiaVonLucBan` (giá vốn/đơn vị) bị map thành `line_cost_total` |
| Role chéo bảng | `TinhTrang` bị `import_status` lấy; `TenGoi`/`LoaiKhachHang` tranh role |

## Thay đổi

1. **Table-entity hints** (`schema/mapper.py`): tên bảng quyết định entity, tránh
   role chéo. Ví dụ `don_hang → orders`, `khach_hang → customers`,
   `san_pham → products`, `the_kho → inventory`, `thanh_toan → payments`.
2. **Role token POS** (`schema/roles.py`):
   - `TenGoi` → customer_name/product_name;
   - `TinhTrang` → status_raw/import_status;
   - `LoaiKhachHang` → customer_group;
   - `NgayLap` → order_date; `NgayGioThu` → pay_date;
   - `NgayGioPhatSinh` → inv_date; `GiaVonLucBan` → unit_cost;
   - `DanhMuc` → category; `DonViCoSo` → unit.
3. **Không lấy cột mã làm tên**: `_assign` bỏ candidate `customer_name`/
   `product_name`/`employee`/`supplier` nếu tên cột bắt đầu bằng
   `Ma/ID/Code/So/SKU` (dùng `column_key`, tách CamelCase).
4. **Cost**: nếu chỉ có `unit_cost` thì `line_cost_total = qty_base × unit_cost`
   (`schema/canon.py`).
5. **Inventory**: thêm `lot_id` rỗng để canonical đủ cột.
6. **View join** (`schema/views.py`):
   - `v_orders_all` join `c_customers` lấy name/group/walkin;
   - `v_lines`/`v_lines_all` join `c_products` lấy product_name/category và
     `c_customers` lấy name/group/walkin.

## Kết quả kiểm tra

- `126 passed` (thêm `tests/test_pos_mapping.py`).
- 50 câu train hard-set: **39 đúng / 7 sai / 4 bỏ, PA 0.64** (trước 40/7/3, 0.66)
  → không regress.
- `dev_006` sau sửa:
  - `v_customers`: tên thật (`Đoàn Huy Khoa`, ...), group `lẻ/sỉ`.
  - `v_orders_all`: status `completed/returned/shipping`, `is_returned=True` 352 đơn.
  - `v_lines`: product_name/category thật; `line_cost_total` = qty × unit cost.
  - `v_inventory`: 73.901 dòng; `v_payments`: 37.939 dòng.
  - `schema_conf`: 0.95 → 0.75 (phản ánh đúng hơn).
- Chạy lại 111 câu dev_006: còn 16 câu trả lời (nhiều câu abstain vì calibration
  cũ `p_trong_thap`), nhưng tên khách/sản phẩm/trạng thái đã đúng.

File test leaderboard: `public_test/submission_dev_006_v2.jsonl` (16 câu).
So sánh với bản cũ `dev_006` (-0.029).

## Regression 100 câu train (phát hiện sau khi sửa)

Lần chạy đầu với mapping mới: **41 đúng / 41 sai / 18 bỏ, PA 0.0** (baseline 51/34/15,
0.17). Nguyên nhân không phải revenue mà là **chọn sai bảng dòng bán**:

- `danhsachchitietnhaphang` (chi tiết nhập) bị chọn làm `lines` vì hint chỉ giới hạn
  role, chưa giới hạn entity.
- Hệ quả: `v_lines` rỗng/không join được `v_orders` → `orders.threshold = 0`,
  `orders.total` sai; toàn bộ 10 câu mất điểm nằm ở `biz_106`.
- `ban_hang` (bảng phẳng) bị hint chỉ `lines/orders`, làm mất entity `products/customers`
  của `biz_101` → 3 câu qty/top bị abstain.

Sửa:
1. Hint cụ thể `chitietnhap`, `hoadonchitiet`, `hoadon`, `tonkho`, `nhaphang`, ...;
   chi tiết hoá đơn đứng trước hoá đơn chung.
2. **Chỉ xét entity thuộc hint** khi fit bảng (chi tiết nhập không thể thành lines).
3. Bảng phẳng `ban_hang` giữ thêm `products/customers`.

Kết quả 100 câu cuối: **51 đúng / 35 sai / 14 bỏ, PA 0.16** — bằng baseline về số câu
đúng; 1 câu `q_bfa` (“bao nhiêu sp có mặt trong ít nhất 145 bill”) bị planner chọn
`orders.total` thay vì bỏ/đếm sản phẩm. Đây là lỗi planner, không phải mapping.

## Việc tiếp theo

- Train lại calibration trên feature mới (nhiều câu đúng bị abstain do `p_trong_thap`).
- Bổ sung template/guard “đếm sản phẩm theo số bill/đơn tối thiểu” (`q_bfa`).
- Bổ sung `returns` (`tra_hang`), `thong_tin_thuoc.BanTheoDon`, `nhan_vien.TenGoi`,
  `lich_su_gia`; `stock_value` phải nhân tồn với giá vốn.
- Đo lại trên train holdout và dev_006 trước khi mở coverage.
