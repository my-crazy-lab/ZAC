# Questions.md — Biên bản quyết định trước khi implement

**Trạng thái: đã chốt.** Các câu dưới đây đã được hỏi trực tiếp và có quyết định. Mục "mặc định tôi tự áp dụng" là các quyết định tôi tự chọn theo rulebook — có thể override bất cứ lúc nào.

Nếu muốn đổi một quyết định, sửa dòng `**Quyết định:**` tương ứng và báo tôi cập nhật plan.

---

## A. LLM & hạ tầng

| # | Câu hỏi | **Quyết định** |
|---|---|---|
| A1 | Model LLM nào | `Qwen3-4B-Instruct`, qua API OpenAI-compatible |
| A2 | Có API LLM sẵn không | **Có** — dùng API được cấp, không tự host model |
| A3 | RAM máy | 16 GB — **không còn là ràng buộc chính** (batch nằm ở server API) |
| A4 | Mạng lúc setup | Không cần tải model local; API dùng được cả ở vòng private (Docker của đội) |
| A5 | Có GPU NVIDIA không | Không → **không dùng vLLM**, dùng API |
| A6 | Deadline | Để trong `config.py`, mặc định `5,25·3600`; tự co giãn k₁/k₂ theo thời gian còn lại |
| A7 | Song song hoá | **16 luồng**, không giới hạn RPM, backoff khi 429/5xx |
| A8 | Câu hỏi trong prompt | **Câu gốc có dấu** + danh sách entity đã khớp (tên master, mã, điểm) |

**Hệ quả:** quy ước "không gọi API ngoài" ở mục 0 của plan đã bị gỡ. `api_key` **không** hard-code, **không** commit — đọc từ biến môi trường.

---

## B. Bài toán nộp & đo

| # | Câu hỏi | **Quyết định** |
|---|---|---|
| B1 | File nộp | `public_test/submission.jsonl` |
| B2 | Vòng private | Docker của đội; API vẫn gọi được |
| B3 | Dev trên `public_test` | **Được** (không có nhãn → không rò rỉ đáp án); rulebook public test cũng là input hợp lệ để parse |
| B4 | Chia holdout | **6/30 business** holdout cố định theo seed (ghi trong `config.py`), phủ cả retail lẫn ngành khác |
| B5 | Mục tiêu | *mặc định:* tối ưu PA, không ép coverage tối thiểu |
| B6 | Nộp gì thêm | *mặc định:* `submission.jsonl` + thư mục `logs/`; không bắt buộc nộp model |

---

## C. Phạm vi nghiệp vụ

| # | Câu hỏi | **Quyết định** |
|---|---|---|
| C1 | 3 ngành mới (Sửa xe, Điện thoại, Mẹ và bé — 170/1000 câu) | **LÀM CẢ 3** → cần bộ view + metric riêng cho từng ngành, phát hiện theo dấu hiệu cấu trúc (không theo `business_id`) |
| C2 | Ô "Làm gì" (sửa xe) | **Tách theo dấu phẩy + mẫu số thứ tự** (`1)`, `2)`) → cột `works`; phiếu bảo hành = ghi chú bảo hành **hoặc** tiền = 0 |
| C3 | Sổ góp (điện thoại) | **Làm cả kỳ góp + quá hạn** (hạn góp < ngày hỏi = quá hạn; hạn đúng ngày hỏi thì chưa) |
| C4 | Mức dũng cảm khi abstain | `margin = 0,05`, trả khi `p_adj > 0,5`; chỉnh margin theo đường cong PA mô phỏng ở M12 |
| C5 | Câu ngoài taxonomy (`intent=other`) | *mặc định:* cho đường 2 viết SQL tự do trên view + hạ `p`; rỗng thì abstain |
| C6 | Dùng `README.md` của shop làm nguồn sự thật | *mặc định:* **có** (đơn vị quy đổi, quy ước số liệu) — README là input hợp lệ |

---

## D. Luật nghiệp vụ đã chốt

| # | Câu hỏi | **Quyết định** |
|---|---|---|
| D0 | So khớp chuỗi: dấu tiếng Việt | **GIỮ DẤU.** Chuẩn hoá = bỏ khoảng trắng thừa + hạ chữ thường + bỏ dấu câu. Chỉ chấp nhận khác dấu nếu khớp `alias` (cách viết có thật trong file). *Rulebook §9: "dấu tiếng Việt phải đúng"; `"Sting dầu 330ml"` là sai.* |
| D1 | "Tháng trước" cắt cùng số ngày | **Chỉ khi kỳ chính kết thúc đúng hôm nay.** Kỳ chính đã qua (vd "so với tháng trước đó" với kỳ chính là tháng 2/2026) → base = cả tháng liền trước |
| D2 | "Tuần trước" | **Luôn trọn tuần T2→CN**, kể cả khi ghép với "tuần này" (không cắt theo hôm nay, khác tháng) |
| D3 | Khách lẻ / đơn không ghi khách | **Loại khỏi xếp hạng, không đếm khách**; nhưng đơn **vẫn tính vào doanh thu** và **vẫn vào tổng nợ** (chỉ không có dòng trong bảng nợ theo khách) |
| D4 | Chuẩn hoá tên khách (shop không có mã) | key = **bỏ dấu tiếng Việt + bỏ ký tự không phải chữ/số + hạ chữ thường** (khi *ghi* ra thì giữ nguyên tên trong file) |
| D5 | Nhận diện dòng "Phí phục vụ" | *mặc định:* tên dòng chứa (không dấu) `phi phuc vu` hoặc `phi dich vu`; nếu shop có cột phân loại dòng thì ưu tiên cột đó. Dòng này **không** xếp hạng, **không** đếm, **nhưng vẫn tính vào doanh thu** và vẫn ở mẫu số tỉ trọng nhóm hàng |
| D6 | "Giá bán X ngày D" | Đơn giá trên dòng thường là giá **1 đơn vị tính** → **chia theo hệ số quy đổi** để ra giá 1 đơn vị cơ bản; trước chiết khấu dòng; tính cả dòng của đơn huỷ, đơn trả |
| D7 | "Bán được bao nhiêu <đơn vị>" | **Lọc theo đơn vị cơ bản**: chỉ tính mặt hàng có đơn vị cơ bản = `<đơn vị>` (kể cả dòng bán theo đơn vị lớn), cộng `qty_base` |
| D8 | "Tồn theo đơn vị lớn" | *mặc định:* list đúng 2 số `[số đơn vị lớn nguyên, số đơn vị cơ bản lẻ]` (có bằng chứng train: `[16, 1]`) |
| D9 | "Giá trị hàng tồn kho" | Dùng **giá vốn 1 đơn vị cơ bản trong danh mục hàng**; không có thì fallback bình quân theo lô; không có cái nào → unanswerable |
| D10 | "Lãi gộp" | Dùng **giá vốn ghi trên dòng bán** (`line_cost`), **không** tự tính lại từ phiếu nhập hay từ lô. Shop không có cột này → câu lãi gộp/lãi ròng là unanswerable |
| D11 | Công nợ có cộng VAT không | **Không.** Tổng đơn = tiền hàng − giảm giá đơn + phí giao (VAT khách trả riêng) |
| D12 | Tuổi nợ | Tính từ **ngày đặt** (`order_date`), không từ hạn thanh toán; đơn đặt hôm nay có tuổi nợ 0 |

---

## E. Mặc định tôi tự áp dụng (được override)

| # | Nội dung | **Mặc định** |
|---|---|---|
| E1 | Chuỗi trả ra | **Tên master** trong danh mục (fallback: tên trên dòng bán) |
| E2 | Tie-break khi không có mã | Theo tên đã chuẩn hoá (bỏ dấu + bỏ ký tự lạ) |
| E3 | Ngưỡng "sắp hết hạn" / "bán chậm" / "tồn nhiều" | 30 ngày; phân vị 25% (qty) và 75% (stock) — chỉnh lại sau khi đối chiếu câu train ở M8 |
| E4 | Tiêu chí khớp | Với `number`/`percent`: khớp tuyệt đối sau khi làm tròn (rulebook §9). Với `string`: giữ dấu (D0) |
| E5 | Quản lý phiên bản | `git init` trong `/Users/minhnl8/Documents/1vin/datamate`, một commit mỗi milestone, `.gitignore` bỏ `.venv/`, `cache/`, `models/` |
| E6 | Chuỗi so khớp dấu câu | Bỏ `. , ; : ! ? " ' ( )` và bỏ khoảng trắng thừa, hạ chữ thường — **giữ dấu tiếng Việt** |

---

## Phụ lục — Dữ kiện đã khảo sát

**Quy mô:** train 30 business / 3000 câu (number 1884, percent 578, list 193, date 145, string 88, unanswerable 70, boolean 23, table 19). Public test 14 business / 1000 câu, không có đáp án.

**Rulebook:** `train/rulebook.md` vs `public_test/rulebook.md` — test **thêm** 3 ngành mới (Mẹ và bé, Sửa xe, Cửa hàng điện thoại), thêm ~12 luật (khách trung thành nhất, khách sộp nhất, giờ cao điểm, nhà cung cấp chính, topping ghi chung ô…), **bỏ** 3 luật (giá nhập bình quân theo tháng, tồn theo đơn vị lớng, giá bán X ngày D), và sửa 1 luật (đơn trả hàng sau kỳ vẫn bị loại khỏi doanh thu kỳ đặt).

**Lịch:** `calendar.csv` có `date,weekday,lunar_day,lunar_month,lunar_year,lunar_leap,holiday`, phủ 2024-01-01..2027-12-31 (đủ, có cột tháng nhuận).

**Câu hỏi train theo nhóm khái niệm** (đếm bằng regex, có thể chồng lấn):

| Nhóm | Số câu |
|---|---|
| Đơn vị lớn / quy đổi | 131 |
| Đơn vị cơ bản, thùng/hộp | 251 |
| Công nợ (còn nợ, tuổi nợ, trả nợ) | 116 |
| Ca sáng / ca chiều | 77 |
| Tỉ lệ đơn huỷ | 60 |
| So sánh kỳ (% hoặc số) | 156 |
| Phương thức thanh toán (COD, tiền mặt…) | 21 |
| Nhân viên | 18 |
| Hết hạn | 14 |
| Giá vốn / lãi gộp / lãi ròng | 10 |
| Nhà cung cấp | 6 |
| Tồn kho | 37 |
| Giá nhập bình quân | 33 |
| Nhóm hàng / danh mục | 33 |

**Cấu trúc dữ liệu:** header không phải luôn ở dòng 0 (biz_103 dòng 2, biz_108/111/112 dòng 3); nhiều file là nhiều sheet theo tháng cần union; `biz_123`/`dev_006` là SQLite (17 bảng: `don_hang`, `chi_tiet_don`, `thanh_toan`, `tra_hang`, `the_kho`, `lo_hang`, `lich_su_gia`, `don_vi_sp`, `nhan_vien`, `nha_cung_cap`, `thong_tin_thuoc`…).

**Môi trường:** đã tạo `.venv` (Python 3.12) với `pandas, openpyxl, duckdb, numpy, rapidfuzz, scikit-learn, joblib, pyarrow`. Cần thêm: `httpx` (gọi API), `pytest` (test).
