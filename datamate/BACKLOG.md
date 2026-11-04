# BACKLOG — việc chưa xong (xếp theo ảnh hưởng)

Mỗi mục ghi: **vấn đề đo được** → **cách sửa** → **file cần sửa**.

## P0 — ảnh hưởng trực tiếp tỉ lệ đúng (đo ở M8, dev 2367 câu, hiện 21.9%)

| # | Vấn đề | Cách sửa | File |
|---|---|---|---|
| 1 | 1458 câu `wrong_value`: câu hỏi có **bộ lọc** (nhóm hàng, nhóm khách, kênh, phương thức thanh toán, nhân viên, đơn vị, size) mà luật chưa sinh đủ bộ lọc | sinh bộ lọc từ **mọi** giá trị trong `value_dict` có xuất hiện trong câu (kể cả giá trị tiếng Anh ↔ tiếng Việt) | `engine/answer.py` (`filters_from`) |
| 2 | Câu hỏi cần metric chưa có trong registry: *giá nhập bình quân theo thùng*, *số ly theo size*, *tồn theo lô*, *giá trị tồn kho theo lô* | thêm metric và `engine/registry.py` + template SQL | `engine/registry.py`, `engine/templates.py` |
| 3 | 331 câu `no_spec`: `metric_source_missing` (shop không có bảng nguồn) | sinh thêm ứng viên dựa trên **view đang có** thay vì metric lý thuyết | `engine/answer.py` |
| 4 | Nhóm `null` (46 câu, đáp án null) không có đường trả lời được | luật "kỳ ngoài khoảng ngày" bắt 14/70; cần luật theo **capability** nhưng `data_caps` phản ánh *mapping*, chưa phải *dữ liệu thực* ⇒ cần phân biệt "shop không có" với "mapper chưa tìm ra" | `decide/answerability.py`, `schema/views.py` |
| 5 | Nhóm `tail` (61 câu) — công nợ, tồn kho, hạn dùng | dựng `c_stock` (tồn theo lô), `c_debt` (số dư theo khách), mở rộng `c_lots` | `schema/canon.py` |

## P1 — chất lượng mapping (ảnh hưởng trực tiếp tỉ lệ đúng theo shop)

| # | Vấn đề | Cách sửa | File |
|---|---|---|---|
| 6 | 5/24 shop dev không có `v_lines` (shop chỉ có bảng đơn, hoặc bảng dòng không nhận ra) | thêm luật nhận dạng bảng dòng theo **cột** (qty + giá + tên hàng) thay vì theo tên file | `schema/mapper.py` |
| 7 | `schema_conf` thấp ở nhiều shop (0.4–0.6) ⇒ câu hỏi bị coi là không chắc chắn | hiện chưa dùng `schema_conf` để chặn; cần dùng khi hiệu chỉnh bộ quyết định | `decide/decider.py` |
| 8 | `c_price_history` chưa nối vào câu hỏi giá theo ngày | thêm view `v_price_at(product, date)` | `schema/views.py` |
| 9 | Archetype cho nhiều shop là `UNKNOWN` | bổ sung tín hiệu nhận dạnh theo cấu trúc file | `schema/archetypes.py` |

## P2 — phần LLM (chưa đo được vì không có API key trong môi trường dev)

| # | Vấn đề | Cách sửa | File |
|---|---|---|---|
| 10 | Path 1 (LLM → Spec) và Path 2 (LLM → SQL) **chưa được đo** (không có `DATAMATE_LLM_BASE_URL`) | chạy `dev/enumerate_match.py` với biến môi trường API rồi so sánh với đường tất định | `paths/path1_spec.py`, `paths/path2_sql.py` |
| 11 | Bộ quyết định (M12) **đã hiệu chỉnh** (`dev/calibrate.py --build --scope dev`) nhưng chỉ dựa trên đặc trưng cấu trúc câu hỏi; chưa dùng tín hiệu "đường 1 và đường 2 đồng thuận" | thêm feature "đồng thuận 2 đường" khi có API LLM | `decide/features.py` |
| 12 | PA hiện ~+0.03 vì phần lớn câu bị **bỏ trống** (coverage 11%) | mở rộng metric + bộ lọc (mục P0 #1, #2) để tăng tỉ lệ khớp rồi hiệu chỉnh lại | `dev/calibrate.py` |
| 13 | Chưa có đường "LLM đọc số liệu rồi trả lời" cho câu không map được | `decide/escalate.py` đã có khung, cần chuẩn hoá dữ liệu đưa cho LLM | `decide/escalate.py` |

## P3 — hạ tầng

| # | Vấn đề | Cách sửa | File |
|---|---|---|---|
| 14 | `predict.py` dựng lại context cho mỗi shop (chậm: ~4 s/shop) | cache `c_*` theo sha256 đã có; cần cache **view** và `schema_card` | `schema/views.py` |
| 15 | `dev/repro_check.py` **đã có** (chạy 2 lần, so kết quả) — cần chạy định kỳ trước khi nộp | thêm vào checklist phát hành | `dev/repro_check.py` |
| 16 | Thiếu kiểm thử cho `schema/mapper.py`, `engine/compile.py`, `paths/*` | thêm test với dữ liệu thật của 1–2 shop | `tests/` |
| 17 | `survey/`, `models/` chứa artefact sinh ra — không commit | đã thêm `.gitignore` | `.gitignore` |
