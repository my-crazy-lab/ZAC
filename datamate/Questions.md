# Questions.md — Câu hỏi cần trả lời trước khi implement

**Cách trả lời:** điền vào dòng `→ Trả lời:` của từng câu. Nếu chấp nhận đề xuất mặc định thì ghi `OK` (tôi sẽ dùng đề xuất đó). Nhóm nào trả lời chậm thì tôi dùng mặc định và ghi log để bạn xem lại sau.

**Mức độ ưu tiên:**
- 🔴 **chặn** — không có câu trả lời thì milestone đó không thể code đúng.
- 🟡 **quan trọng** — code vẫn chạy được nhưng có thể sai ở hàng loạt câu.
- ⚪ **nice-to-have** — tối ưu, không ảnh hưởng đúng/sai.

---

## A. LLM & hạ tầng (chặn M9 → M13)

### A1 🔴 Model LLM nào sẽ dùng?
Máy này không có CUDA, không có ollama/llama.cpp, không có model nào trong cache. Bài `lifemate` cùng giải đang dùng `transformers` + `Qwen3-4B`.
**Đề xuất:** `Qwen3-4B-Instruct` qua `transformers`, greedy, `dtype` phù hợp máy. Lựa chọn khác: Qwen3-8B (chậm hơn ~2×), Qwen2.5-7B-Instruct.
`→ Trả lời:`

### A2 🔴 Có được cấp API LLM (endpoint có sẵn) không?
Nếu có, bỏ được việc đóng gói model vào Docker và chạy nhanh hơn nhiều.
**Đề xuất mặc định (nếu không có API):** model local trong Docker, không mạng lúc inference.
`→ Trả lời:`

### A3 🔴 Inference chạy ở đâu, và máy có bao nhiêu RAM/VRAM?
Quyết định trực tiếp `k₁, k₂` (số mẫu mỗi câu) và `batch_size` — 1000 câu × (k₁+k₂) prompt là con số lớn, plan giả định deadline 5,25h.
**Đề xuất:** đo throughput thật ở M9 rồi chốt; nếu yếu → giảm k, chạy đường 2 chỉ cho `intent=other`.
`→ Trả lời:`

### A4 🟡 Được phép tải model từ internet lúc setup chứ?
Network lúc **runtime** thì chắc là không (BTC chạy Docker của đội). Lúc setup thì cần để tải weights.
`→ Trả lời:`

### A5 🟡 Có máy nào có GPU/CUDA không?
Nếu có thì vLLM quay lại khả thi và nhanh hơn nhiều lần so với `transformers` trên CPU.
`→ Trả lời:`

### A6 🟡 Deadline thực tế của lượt nộp?
Plan đang giả định 5,25h (khớp `lifemate`). Cần con số thật để chốt ngân sách LLM.
`→ Trả lời:`

### A7 ⚪ Có được chạy nhiều tiến trình song song không?
Mac M5 có nhiều lõi; chạy song song nhiều worker có thể cắt wall-time.
`→ Trả lời:`

### A8 🟡 Đưa câu hỏi gốc (có dấu) hay đã bỏ dấu vào prompt LLM?
M6 bỏ dấu để **khớp tên** trong dữ liệu; nhưng LLM hiểu tiếng Việt có dấu tốt hơn nhiều, còn câu hỏi train lại viết tắt/sai chính tả nên cần cả hai.
**Đề xuất:** prompt đưa **câu gốc** + bên cạnh là danh sách entity đã khớp (tên master, mã, điểm) bằng chữ **có dấu**.
`→ Trả lời:`

---

## B. Bài toán nộp bài & cách đo (chặn M0/M13)

### B1 🔴 File nộp chính thức nằm ở đâu?
Plan đang giả định `public_test/submission.jsonl` (theo README `lifemate`). Hay `/result/submission.jsonl`?
`→ Trả lời:`

### B2 🔴 Vòng private test chạy thế nào?
Có Docker do BTC build không? Có yêu cầu offline tuyệt đối không? Có giới hạn RAM/CPU cho container không?
`→ Trả lời:`

### B3 🟡 Có được dùng câu hỏi `public_test/questions.jsonl` để dev/tinh chỉnh prompt không?
Không có nhãn nên tôi cho là **được** (rulebook public test cũng là input hợp lệ để parse).
`→ Trả lời:`

### B4 🟡 Chia train thế nào để đo leave-one-business-out?
Plan: giữ 20% business (6/30) làm holdout, không lấy ví dụ từ business đó trong bank.
**Đề xuất:** 6 business holdout cố định theo seed, phủ cả retail lẫn vài ngành khác.
`→ Trả lời:`

### B5 ⚪ Mục tiêu PA tối thiểu?
Để biết có nên đánh đổi coverage (trả nhiều) ↔ precision (chỉ trả khi chắc).
**Đề xuất:** tối ưu PA, không ép coverage tối thiểu.
`→ Trả lời:`

### B6 ⚪ Ngoài `submission.jsonl` còn phải nộp gì không (log, mô hình calibrator, script chạy lại)?
`→ Trả lời:`

---

## C. Phạm vi nghiệp vụ (chặn M4/M5)

### C1 🔴 3 ngành mới ở public_test xử lý thế nào?
`public_test/rulebook.md` có thêm **Mẹ và bé**, **Sửa xe**, **Cửa hàng điện thoại** — 170/1000 câu (dev_012: 50, dev_013: 57, dev_014: 63). Kiểu dữ liệu của chúng **không** có mô hình đơn/dòng/sản phẩm mà plan đang giả định.
**Ba lựa chọn:**
- (a) Thiết kế thêm view/metric riêng cho từng domain (tốn công nhất nhưng phủ được câu).
- (b) Không làm gì, để đường 2 (SQL tự do) + hạ `p` → nhiều câu sẽ abstain (0 điểm).
- (c) Làm (a) nhưng chỉ phần câu đơn giản (đếm phiếu, tiền, top khách).
**Đề xuất:** (c) — ưu tiên dev_014 (điện thoại, 63 câu, vẫn là sổ bán hàng nên gần mô hình chuẩn) và dev_012 (sửa xe, 50 câu, đơn giản: đếm lượt xe, tiền, thợ); dev_013 (mẹ và bé) dùng chung mô hình bán hàng + bổ sung cột Số/Size.
`→ Trả lời:`

### C2 🟡 dev_012 (sửa xe): ô "Làm gì" ghi nhiều việc chung một ô
Rulebook nói "lượt xe có làm một việc = phiếu có việc đó" → cần tách việc trong 1 ô (dấu phẩy / số thứ tự?). Cần biết cách ghép việc trong file thật.
**Đề xuất:** tách theo dấu phẩy và các mẫu số thứ tự (`1)`, `2)`), rồi khớp fuzzy với danh sách việc trong rulebook.
`→ Trả lời:`

### C3 🟡 dev_014: sổ góp (trả góp) có cần tính kỳ góp / quá hạn không?
Rulebook §"Cửa hàng điện thoại" nói rõ công thức kỳ góp. Nếu câu hỏi có hỏi thì cần implement; nếu không thì bỏ qua.
`→ Trả lời:`

### C4 🟡 Mức "dũng cảm" khi quyết định trả hay abstain?
Đúng +1, sai −1 → trả liều có thể âm. Plan đang dùng margin 0,05 và `p>0.5`.
**Đề xuất:** giữ nguyên, chỉnh margin theo đường cong PA mô phỏng ở M12 (không chốt cứng từ đầu).
`→ Trả lời:`

### C5 🟡 Câu nằm ngoài taxonomy (`intent=other`) thì xử lý thế nào?
**Đề xuất:** cho đường 2 viết SQL tự do trên view, hạ `p`; nếu đường 2 cũng rỗng → abstain.
`→ Trả lời:`

### C6 ⚪ Được phép dùng `README.md` của từng shop làm nguồn sự thật không?
Plan M4 đã đọc README (đơn vị quy đổi, quy ước số liệu). Với public_test, README cũng là input hợp lệ.
**Đề xuất:** có, và phải parse (biz_101 có bảng quy đổi 90 dòng trong README).
`→ Trả lời:`

---

## D. Chỗ rulebook còn mơ hồ, cần bạn chốt (chặn M2/M5/M8)

> Đây là nhóm tôi cần ý kiến nhất: mỗi câu dưới đây là một quyết định nghiệp vụ mà rulebook **không nói rõ**, nếu chọn sai thì hàng loạt câu sai.

### D0 🔴 Chuỗi: dấu tiếng Việt có phải bắt buộc đúng không?
Rulebook §9 ghi *"không phân biệt hoa thường, khoảng trắng, dấu câu"* nhưng cũng ghi *"Ngoài các cách viết đó, **dấu tiếng Việt phải đúng**"*, và ví dụ sai ghi rõ `"Sting dầu 330ml"` (sai dấu) là **sai**. Trong khi đó plan M0 đang so khớp string bằng `unaccent(lower(strip(x)))` → **bỏ dấu khi so khớp, tức sai**.
**Đề xuất sửa plan:** so khớp chuỗi = bỏ khoảng trắng thừa + hạ chữ thường + bỏ dấu câu, **giữ nguyên dấu tiếng Việt**; chỉ chấp nhận dấu khác khi dấu đó có trong `alias` của shop.
`→ Trả lời:`

### D1 🔴 "Tháng này" so với "tháng trước" → cắt cùng số ngày
Rulebook §2: *"So với tháng trước thì lấy cùng số ngày của tháng trước"*. Câu thật: *"từ đầu tháng này đến hết bữa nay, doanh thu hơn hay kém cùng kỳ tháng trc mấy %"* (as_of 2026-04-10) → base = 01/03..**10/03**, không phải cả tháng 3.
Câu hỏi: quy tắc này chỉ áp khi **kỳ chính kết thúc đúng hôm nay**, hay áp cho mọi cặp "tháng này / tháng trước" (kể cả khi kỳ chính là tháng đã qua, vd *"so với tháng trước đó, doanh thu tháng 2/2026 tăng hay giảm mấy %"* → base có phải tháng 1 đầy đủ)?
**Đề xuất:** chỉ áp khi kỳ chính kết thúc ở hôm nay; nếu kỳ chính là tháng đã qua thì base = tháng liền trước đầy đủ.
`→ Trả lời:`

### D2 🟡 "Tuần này" so với "tuần trước" có cắt cùng số ngày không?
Rulebook chỉ nói *"Tuần trước, tuần rồi: cả tuần liền trước, thứ Hai đến Chủ nhật"*, không nói cắt theo hôm nay — khác với tháng.
**Đề xuất:** "tuần trước" luôn là trọn tuần (T2→CN), kể cả khi ghép với "tuần này".
`→ Trả lời:`

### D3 🟡 Nhận diện "khách lẻ" / khách không ghi mã
Rulebook §3: đơn không ghi mã khách → không phải khách, không đếm, không xếp hạng. Nhưng nhiều file ghi tên literal `"Khách lẻ"` (vd biz_101 README: "Đối tác: tên khách (Khách lẻ nếu không lưu)").
**Đề xuất:** loại các khách có tên khớp `khach le|khach vang lai|khach le (khong luu)` (không dấu); đơn đó vẫn **tính vào doanh thu** và **vẫn vào tổng nợ**, chỉ không có dòng trong bảng nợ theo khách.
`→ Trả lời:`

### D4 🟡 "Hai tên chỉ khác cách viết là cùng một khách" — chuẩn hoá thế nào?
Rulebook §3 (shop không có mã khách). Cần quy tắc gộp tên: bỏ dấu? bỏ khoảng trắng? bỏ dấu chấm? gộp "Nguyễn Văn A" vs "Nguyễn Văn A."?
**Đề xuất:** so khớp tên khách bằng key = bỏ dấu tiếng Việt + bỏ mọi ký tự không phải chữ/số + hạ chữ thường (giữ nguyên khi *ghi* ra).
`→ Trả lời:`

### D5 🟡 Nhận diện dòng "Phí phục vụ"
Rulebook §3: dòng này không xếp hạng, không đếm, nhưng **vẫn tính vào doanh thu** và vẫn ở mẫu số tỉ trọng nhóm hàng.
**Đề xuất:** khớp tên dòng chứa (không dấu) `phi phuc vu` hoặc `phi dich vu`; nếu shop có cột phân loại dòng thì dùng cột đó.
`→ Trả lời:`

### D6 🟡 "Giá bán X ngày D" lấy đơn giá nào?
Rulebook §5: *"đơn giá ghi trên dòng bán X của các đơn đặt ngày D, cho một đơn vị cơ bản, trước chiết khấu dòng; tính cả dòng của đơn huỷ, đơn trả"*. Vậy "đơn giá cho một đơn vị cơ bản" là cột `unit_price` (giá 1 đơn vị tính) hay phải chia theo hệ số quy đổi?
**Đề xuất:** `unit_price` thường là giá **1 đơn vị tính** → chia theo hệ số quy đổi để ra giá 1 đơn vị cơ bản (có `v_units`).
`→ Trả lời:`

### D7 🟡 "Bán được bao nhiêu <đơn vị>" — quy đổi thế nào khi đơn vị của dòng khác đơn vị cơ bản?
Rulebook §3: chỉ tính mặt hàng **có đơn vị cơ bản là `<đơn vị>`**, "kể cả dòng bán theo đơn vị lớng".
**Đề xuất:** lọc theo `unit_base == <đơn vị>`, rồi cộng `qty_base`.
`→ Trả lời:`

### D8 🟡 "Tồn theo đơn vị lớn" trả về đúng format nào?
Train có ví dụ `[16, 1]` (2 số) → `[số đơn vị lớn nguyên, số đơn vị cơ bản lẻ]`.
**Đề xuất:** giữ nguyên list 2 số, không kèm nhãn.
`→ Trả lời:`

### D9 🟡 "Giá trị hàng tồn kho" dùng giá vốn nào?
Rulebook §5: *"tồn hết hôm nay của từng mặt hàng nhân giá vốn một đơn vị cơ bản **ghi trong danh mục hàng**"* → dùng cột giá vốn ở bảng sản phẩm, **không** phải bình quân theo lô.
**Đề xuất:** ưu tiên `products.unit_cost`; shop không có thì dùng bình quân theo lô; không có cái nào → unanswerable.
`→ Trả lời:`

### D10 🟡 "Lãi gộp" dùng giá vốn dòng hay giá vốn danh mục?
Rulebook §5 nói rõ: *"Giá vốn của mỗi dòng bán bằng số lượng nhân với giá vốn **ghi trên dòng bán**… Không tự tính lại giá vốn từ phiếu nhập hay từ lô"*.
**Đề xuất:** dùng cột giá vốn trên dòng; shop không có → câu lãi gộp/lãi ròng là unanswerable (rulebook §7).
`→ Trả lời:`

### D11 🟡 "Còn nợ" tính trên tổng đơn nào?
Rulebook §4: *"phần chưa trả của tổng đơn (số khách phải trả cả đơn: đã trừ giảm giá trên cả đơn, gồm phí giao)"* → tổng đơn = tiền hàng − giảm giá đơn + phí ship (không cộng VAT?). Vậy công nợ có cộng VAT không?
**Đề xuất:** tổng đơn = tiền hàng sau giảm giá đơn + phí giao, **không** VAT (VAT do khách trả riêng).
`→ Trả lời:`

### D12 🟡 "Tuổi nợ" tính từ ngày nào khi đơn có nhiều lần trả nợ?
Rulebook §4: tuổi nợ tính từ **ngày đặt**, không từ hạn thanh toán. Với câu hỏi kiểu "tuổi nợ trung bình" / "nợ quá 30 ngày" thì chốt theo ngày đặt.
**Đề xuất:** dùng `order_date` cho mọi phép đo tuổi nợ.
`→ Trả lời:`

---

## E. Việc tôi tự lo, chỉ cần bạn xác nhận hướng

### E1 ⚪ Chuỗi trả ra dùng tên master trong danh mục hay tên xuất hiện ở dòng bán?
Train trả `"Panadol 500mg hộp 10 vỉ x 12 viên"` kèm `alias=["SP0003"]` → nhiều khả năng là **tên master**.
**Đề xuất:** tên master (tên xuất hiện đa số trong bảng sản phẩm), fallback tên trên dòng bán.
`→ Trả lời:`

### E2 ⚪ Có cần kiểm tra lại "bán chạy theo đơn vị cơ bản" với câu hỏi có nêu đơn vị không?
Ví dụ *"bán được tổng cộng bao nhiêu chai"* → chỉ mặt hàng có đơn vị cơ bản = chai.
**Đề xuất:** có, lọc theo `unit_base` nếu câu nêu đơn vị.
`→ Trả lời:`

### E3 ⚪ Quy tắc tie-break khi không có mã
Rulebook §9: *"không có mã thì theo tên"*.
**Đề xuất:** so khớp tên theo key bỏ dấu + hạ chữ thường.
`→ Trả lời:`

### E4 ⚪ Ngưỡng "sắp hết hạn" (30 ngày) và "bán chậm / tồn nhiều" (phân vị 25%/75%) — có giữ mặc định không?
**Đề xuất:** giữ, rồi chỉnh bằng dữ liệu train ở M8.
`→ Trả lời:`

### E5 ⚪ Có được tạo repo git để theo dõi tiến độ không?
Hiện `/Users/minhnl8/Documents/1vin/datamate` **chưa có `.git`**.
**Đề xuất:** `git init` + commit theo từng milestone.
`→ Trả lời:`

---

## Phụ lục — Dữ kiện tôi đã khảo sát (để bạn đối chiếu nhanh)

**Quy mô:** train 30 business / 3000 câu (number 1884, percent 578, list 193, date 145, string 88, unanswerable 70, boolean 23, table 19). Public test 14 business / 1000 câu, không có đáp án.

**Rulebook:** `train/rulebook.md` vs `public_test/rulebook.md` — test **thêm** 3 ngành mới (Mẹ và bé, Sửa xe, Cửa hàng điện thoại), thêm ~12 luật (khách trung thành nhất, giờ cao điểm, nhà cung cấp chính, topping ghi chung ô…), **bỏ** 3 luật (giá nhập bình quân theo tháng, tồn theo đơn vị lớn, giá bán X ngày D), và sửa 1 luật (đơn trả hàng sau kỳ vẫn bị loại khỏi doanh thu kỳ đặt).

**Lịch:** `calendar.csv` có `date,weekday,lunar_day,lunar_month,lunar_year,lunar_leap,holiday`, phủ 2024-01-01..2027-12-31 (đủ, có cột tháng nhuận).

**Câu hỏi train theo nhóm khái niệm (đếm bằng regex, có thể chồng lấn):**

| Nhóm | Số câu |
|---|---|
| Đơn vị lớn / quy đổi | 131 |
| Công nợ (còn nợ, tuổi nợ, trả nợ) | 116 |
| Ca sáng / ca chiều | 77 |
| Tỉ lệ đơn huỷ | 60 |
| So sánh kỳ (% hoặc số) | 156 |
| Đơn vị cơ bản, thùng/hộp | 251 |
| Phương thức thanh toán (COD, tiền mặt…) | 21 |
| Nhân viên | 18 |
| Giá vốn / lãi gộp / lãi ròng | 10 |
| Nhà cung cấp | 6 |
| Hết hạn | 14 |
| Tồn kho | 37 |
| Giá nhập bình quân | 33 |
| Nhóm hàng / danh mục | 33 |

**Cấu trúc dữ liệu:** header không phải luôn ở dòng 0 (biz_103 dòng 2, biz_108/111/112 dòng 3); nhiều file là nhiều sheet theo tháng cần union; `biz_123`/`dev_006` là SQLite (17 bảng: `don_hang`, `chi_tiet_don`, `thanh_toan`, `tra_hang`, `the_kho`, `lo_hang`, `lich_su_gia`, `don_vi_sp`, `nhan_vien`, `nha_cung_cap`, `thong_tin_thuoc`…).

**Môi trường hiện tại:** đã tạo `.venv` (Python 3.12) với `pandas, openpyxl, duckdb, numpy, rapidfuzz, scikit-learn, joblib, pyarrow`. Chưa có `torch/transformers` (cần cho LLM), chưa có `rank_bm25` (tự cài được).
