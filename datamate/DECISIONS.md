# DECISIONS.md — Biên bản quyết định (record, KHÔNG phải spec)

> **Đây là record, không phải nguồn chuẩn.** Nguồn chuẩn cho mọi quy tắc hiện thực là [`EXECUTION-PLAN.md`](EXECUTION-PLAN.md); khi hai file lệch nhau, `EXECUTION-PLAN.md` thắng và file này phải được sửa theo.
> Lý do đổi tên từ `Questions.md`: file không còn chứa câu hỏi nào — nó chỉ ghi lại các quyết định đã chốt kèm lý do.

**Trạng thái: đã chốt.** Các câu dưới đây đã được hỏi trực tiếp và có quyết định. Mục "mặc định tôi tự áp dụng" là các quyết định tôi tự chọn theo rulebook — có thể override bất cứ lúc nào.

Nếu muốn đổi một quyết định, sửa dòng `**Quyết định:**` tương ứng và báo tôi cập nhật plan.

---

## A. LLM & hạ tầng

| # | Câu hỏi | **Quyết định** |
|---|---|---|
| A1 | Model LLM nào | **Dev/phase 1:** `MiniMax M3.1-flash` qua API OpenAI-compatible. **Bản cuối:** `Qwen3-4B` self-host (vLLM trong image) |
| A2 | Có API LLM sẵn không | **Có ở lúc dev** — dùng API được cấp. **Lúc nộp bài: luật thi bắt chạy offline** ⇒ model phải nằm trong image (M16 của `EXECUTION-PLAN.md`) |
| A3 | RAM máy | 16 GB — **không còn là ràng buộc chính** (batch nằm ở server API) |
| A4 | Mạng lúc setup | Dev: không cần tải model local (gọi API). Vòng nộp: **offline** ⇒ tải trọng số lúc build image |
| A5 | Có GPU NVIDIA không | Không → **không dùng vLLM**, dùng API |
| A6 | Deadline | Để trong `config.py`, mặc định `5,25·3600`; tự co giãn k₁/k₂ theo thời gian còn lại |
| A7 | Song song hoá | **16 luồng**, không giới hạn RPM, backoff khi 429/5xx |
| A8 | Câu hỏi trong prompt | **Câu gốc có dấu** + danh sách entity đã khớp (tên master, mã, điểm) |

**Hệ quả:** quy ước "không gọi API ngoài" đã bị gỡ ở tầng dev. `api_key` **không** hard-code, **không** commit — đọc từ biến môi trường `DATAMATE_LLM_API_KEY`.

**Phase 1 vs bản cuối:** phase 1 (`EXECUTION-MVP.md`) chạy end-to-end bằng API, không deploy, không nộp bài. Bản cuối (`EXECUTION-PLAN.md`) thêm M16 (Docker + model local offline + luật thi BTC).

---

## B. Bài toán nộp & đo

| # | Câu hỏi | **Quyết định** |
|---|---|---|
| B1 | File nộp | `public_test/submission.jsonl` |
| B2 | Vòng private | Docker của đội, chạy **offline**, trọng số model trong image, `predict.sh` đọc `/data` ghi `/result/submission.jsonl` |
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

## F. Nhật ký tăng điểm (benchmark PA300 train, n=3000 dòng chấm)

Sai = −1, bỏ = 0. Chấm bằng `dev/evaluate.py --answers train/answers.jsonl`.

| Lượt chạy | PA | Precision | Abstain | Đã làm gì |
|---|---|---|---|---|
| `dm_bench_client` (baseline) | −0.0213 | 0.363 | 2766 | sửa client HTTP (AsyncClient mỗi lần gọi) |
| `dm_bench_gate` (`bd6ac65`) | −0.0113 | 0.417 | 2796 | đáp án path1/path2 phải qua cửa `decide()` (path2 đúng 0/30 khi nộp thẳng) |
| `dm_bench_kindcheck` (`1b16eeb`) | −0.0037 | 0.470 | 2819 | luật cứng kiểm kiểu đáp án (`decide/candidate_check.py`): hỏi đếm mà đáp tiền, hỏi % mà đáp số thô, hỏi ngày mà đáp tên → bỏ |
| `dm_bench_kindv2` (`574291f`) | **+0.0013** | 0.512 | 2834 | phân biệt đếm/tiền bằng cụm tiền mạnh + đơn vị đếm (ly/đĩa/cục/mặt hàng/mấy ngày); thêm `--resume` cho `predict.py` (cứu lượt đo rớt ở câu 143) |
| `dm_bench_pctfix` (bước 1) | **+0.0050** | 0.548 | 2845 | chặn đáp án nhãn `percent` nhưng value là tiền thô (percent=360000); `infer_output` loại nồng độ "0,1%" trước khi gắn nhãn percent — câu otrivin về đúng `number` 58000 |
| `dm_full_train` (full 3000) | **−0.0467** | 0.455 | 1452 | chạy hết train (~2.7h): coverage 51.6% (subset 300 câu/phần đầu file không đại diện — máy bỏ qua tới 95% ở đó). Lỗ lớn nhất: `number` −0.078 (1884 câu), `list` −0.249, `boolean` −0.348; `date` +0.42, `percent` +0.016. **843/844 câu sai từ đường xác định** (LLM đã bịt kín) — cửa `decide` để lọt đáp án tính sai nhưng tự tin |

Quyết định kèm theo: mọi đường trả lời (xác định, path1, path2, escalate) đều đi qua `decide()`; luật kiểm kiểu validate 0 câu đúng bị oan trên tập train trước khi đưa vào máy (17 test trong `tests/test_candidate_check.py`).

Mục tiêu tiếp theo (bước 2 sửa lại theo số full): 668 câu `number` đường xác định tính sai nhưng tự tin. Hướng đã chọn sau khi phân rã: **sửa schema linking** (metric/domain/thực thể/thời gian), không phải kiểm chéo đáp số. Chi tiết ở §G.

---

## G. Bước 2 — sửa theo số liệu full train (schema-linking guard)

**Chẩn đoán lại.** 843/844 câu sai vẫn đến từ đường xác định, nhưng **không phải sai cửa sổ thời gian**: 609/667 câu số sai vẫn có window `main`. Lỗi nằm ở khâu chọn ngữ nghĩa (schema linking):

| Nhóm lỗi | Số câu | Ví dụ |
|---|---|---|
| Câu hỏi phiếu nhập nhưng metric = doanh thu | 472/667 | "tổng giá trị các phiếu nhập hàng" → trả tiền bán |
| Không nhận ra thực thể | 502/667 | "đã huỷ" bị khớp thành khách **Đào Bích Huy** (2/3 token mờ) |
| Đếm đơn huỷ bằng metric đếm mọi đơn | 25 | "đếm số đơn đã huỷ" → 2775 thay vì 64 |
| Ca sáng/chiều | 35 | `order_ts` bị cắt thành `date` nên lọc giờ luôn rỗng |
| Xếp hạng top-N | 65 | "top 5 hàng bán chạy" nhóm theo tháng → trả `['2025-11-01']` |

**Cách sửa — khai báo, không theo id/câu cụ thể:**

1. **Entity linking** (`text/entity_linker.py`): bằng chứng token chặt — exact sau bỏ dấu; fuzzy chỉ cho token ≥4 ký tự; span phải phủ ≥60% tên. Từ nghiệp vụ một âm tiết ("huỷ", "trả", "nhập") chỉ link khi có ngữ cảnh đối tượng quanh nó.
2. **Ngữ nghĩa metric** (`engine/semantics.py`): mỗi metric khai báo `domain` (sales/purchase/inventory/debt) và `requires_entity`; câu hỏi có tín hiệu miền/trạng thái. `candidate_specs` ưu tiên metric đúng miền; `decide()` bỏ khi spec lệch miền, và bỏ metric cần đối tượng khi chưa nhận ra đối tượng.
3. **Chủ thể xếp hạng**: bỏ mốc thời gian khỏi rank/list; loại "cửa hàng/khách hàng/đơn hàng" khỏi tín hiệu mặt hàng; xếp hạng "nhiều tiền" ưu tiên metric tiền.
4. **Thời gian** (`timeutil/resolver.py`, `ingest/clean.py`): ca là **thuộc tính của kỳ**; danh sách nhiều tháng giữ đủ tháng, không lặp tháng đầu; khoảng tháng chỉ mở thành chuỗi khi câu hỏi so sánh từng tháng; `order_ts` giữ phần giờ.
5. **Định dạng** (`fmt/formatter.py`, `engine/compile.py`): nhãn kỳ nội bộ ("p2") đổi về tháng/ngày thật; câu đúng/sai phải trả `boolean`; câu liệt kê nhiều kỳ trả list giá trị theo thứ tự.

**Đo bằng** `dev/replay_det.py` — chạy đúng đường xác định (không LLM), chấm bằng `fmt.compare.is_correct`:

| Bản | PA | coverage | precision | đúng | sai | ghi chú |
|---|---|---|---|---|---|---|
| full train gốc nộp | −0.0467 | 0.516 | 0.455 | 694 | 854 | có cả path LLM |
| v1 | +0.0223 | 0.526 | 0.521 | 823 | 756 | entity + semantics + guard |
| v7 | +0.0487 | 0.528 | 0.546 | 865 | 719 | thêm thời gian, chủ thể, định dạng |
| **v8** | **+0.0553** | **0.530** | **0.552** | **878** | **712** | thêm chiều so sánh đúng/sai |

PA theo type ở v8: `boolean` +0.61 (từ −0.35), `date` +0.40, `number` +0.041, `percent` +0.057, `string` +0.011, `list` −0.124, `unanswerable` +0.10.

Test: 108 test, gồm `test_semantics.py`, `test_entity_linker.py`, và các ca hồi quy cho thời gian/định dạng.

**Bài học kiến trúc:** với dạng bài này, câu trả lời sai nhưng "trông hợp lý" không chặn được bằng kiểm kiểu đáp án. Phải kiểm ở **khâu chọn nguồn dữ liệu** (schema linking) và ở **tính toàn vẹn của kỳ** (ca, chuỗi tháng, giờ), rồi mới đến bộ quyết định.

---

## H. Vòng 3 — nhiều giá trị cùng chỉ tiêu (research-driven)

**Đọc trước khi làm:** RoSL (EMNLP 2025) cho thấy tách câu hỏi ở **khâu schema linking** tăng recall liên kết; CQE và TAT-QA cho cách tách *giá trị + đơn vị* và các phép ghép số. Áp dụng cho câu "doanh thu Zalo OA **và** tại quầy": đây là hai phép tính cùng metric, không phải một bộ lọc.

**Đã làm:**
- `engine/answer.py`: `matched_values()` khớp cụm chính xác sau bỏ dấu, có từ đồng nghĩa **không thể nhầm** (`tai quay`, `dien thoai`, `tien mat`, `chuyen khoan`, `cod`, `vi dien tu`, `ghi no`), xếp theo thứ tự được nhắc; loại giá trị chung (`khác`, `hàng hóa`).
- Nhiều giá trị của cùng một chiều → intent `multi_value`, compile thành UNION từng nhánh, formatter trả list đúng thứ tự.
- Chặn "tổng A và B" bị hiểu thành list.

**Kết quả v11:** PA **+0.0563** (v8 +0.0553), `list` −0.124 → −0.109. So với v8: +4 câu đúng, **0 câu đúng bị mất**, 9 câu trước bỏ nay trả sai (dữ liệu shop lệch, xem dưới).

**Giới hạn phát hiện:** với nhiều shop, tổng doanh thu theo kênh trong `v_lines` thấp hơn đáp án ~25% (ví dụ biz_111 tháng 2/2026: `v_lines` 131,9tr, `v_orders_all` 137,5tr, đáp án 166,4tr). Đây là **thiếu dữ liệu ở tầng ingest/map**, không phải lỗi ghép list. Tương tự, câu "mấy hộp chẵn, mấy cái lẻ" (17 câu) chưa làm được vì `v_inventory` rỗng và `c_lots.lot_qty` bị map thành NULL ở nhiều shop.

**Hướng tiếp có căn cứ:** (1) vá ingest/map cho tồn kho – lô – kênh của các shop lệch; (2) hai chỉ tiêu khác nhau trong một câu ("ghi nợ thêm" + "trả nợ") dùng `v_debt_events`; (3) chỉ mở `multi_value` khi dữ liệu shop tự nhất quán (tổng các nhánh ≈ tổng cả kỳ) để tránh 9 câu sai mới.

---

## I. Vòng 4 — ingest/map (mức nhảy lớn nhất)

**Triệu chứng:** `biz_116` trả doanh thu 0 cho mọi kỳ; `biz_105`/`biz_117` mất ~50% `order_date`; `biz_122` có `v_lines` rỗng; `biz_130` thiếu nửa dữ liệu; 210 câu bị coi là "kỳ ngoài khoảng dữ liệu" (trước đó 14).

**Bốn gốc lỗi, đều ở tầng đọc/map:**

1. **Tên bảng trùng giữa các sheet.** Mọi sheet trong một file dùng chung tên file, nên `canonicalize` lấy sheet cuối đè sheet đầu (file báo cáo có cả sổ bán hàng, bảng giao hàng, danh mục). → Tên bảng phải kèm tên sheet.
2. **Gộp bảng so sánh sai kiểu.** `other_cols = set(a2.values())` lấy tuple `(cột, điểm)` thay vì tên cột ⇒ overlap luôn 0 ⇒ chỉ dùng một bảng, bỏ các sheet tháng/file `_1`, `_2`. → Lấy đúng tên cột, và chỉ gộp khi cùng **tên logic** (tránh trộn bảng nhập với bảng bán).
3. **Đuôi đơn vị bị hiểu là độ lớn.** `suf.startswith("t")` biến "2 thùng" thành 2 triệu, "1 bình" thành 1 tỷ. → Chỉ nhận độ lớn khi khớp đúng (`k`, `tr`, `trieu`…), thêm dạng "1tr440".
4. **Ngày.** Cột trộn chuỗi ngày và số Excel (45689); ngày thiếu năm ("1/1") trong sheet tháng. → Nhận serial khi cột có cả chuỗi ngày; điền năm từ tên sheet.

Thêm: bảng phẳng tự cung cấp cột đơn (tránh chọn dòng bán ở file tháng này, đơn ở file tháng khác ⇒ join rỗng), và ưu tiên bảng dòng bán có tiền hơn bảng giao hàng.

**Kết quả v13** (đo đầy đủ, `dev/replay_det.py` + `dev/evaluate.py`):

| PA | precision | đúng | sai | abstain | coverage |
|---|---|---|---|---|---|
| **+0.1297** | **62,3%** | **987** | **598** | 1415 | 52,8% |

PA theo type: boolean +0,61 · date +0,58 · number +0,12 · percent +0,09 · string +0,08 · unanswerable +0,11 · list +0,02 · table 0.

Kiểm chứng trực tiếp: `biz_116` Q4/2025 = 4.441.276.600, tháng 11/2025 = 1.423.804.300, Tôn Hoa Sen tháng 7/2025 = 9.435.000 — khớp đáp án (trước là 0). `biz_130` phủ 2025-02..2026-08; `biz_105` đến 2026-06; `biz_122` có 101.714 dòng bán.

**Lượt v14** (thêm guard gộp bảng) đã dừng giữa chừng nên không có số chính thức. Đã đối chiếu: guard chỉ bỏ các gộp sai (`products`+bảng đơn vị, `lots`+chi tiết nhập); danh sách bảng bán giống hệt v13, nên kết quả kỳ vọng tương đương.

**Còn lại (598 câu sai):** doanh thu/bộ lọc thiếu (nhóm hàng, hoạt chất, nhân viên) · đếm đơn 60 · trung bình đơn 37 · list xếp hạng 36 · đơn huỷ/tỉ lệ huỷ 33 · tách tồn theo đơn vị · số đợt giao chưa có metric. Shop yếu: `biz_117` 51, `biz_127` 44, `biz_111` 43, `biz_109` 41, `biz_123` 35.

Test: 116 test pass, gồm các ca hồi quy cho số ("2 thùng", "1tr440"), ngày trộn serial, ngày thiếu năm, gộp bảng và thứ tự list.

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
