# Solution Description — DataMate (Zalo AI Challenge 2026)

## Bản ngắn (dán form)

Đội **MH** xây dựng hệ thống hỏi đáp dữ liệu bán hàng theo hướng
**context-first + template selection**, không để LLM viết SQL tự do.

Pipeline: đọc CSV/XLSX/SQLite → chuẩn hoá thành bảng canonical `c_*` và view
`v_*` → compile README của từng shop (mô tả cột, quy ước, quy đổi đơn vị, dòng
đặc biệt) cùng snapshot dữ liệu thành **Business Context** → sinh **catalog
template truy vấn** từ metric registry và capability thật của shop → LLM
(Qwen3-14B) chỉ chọn `template_id` và điền tham số trong tập đóng → code render
SQL deterministic, chạy DuckDB, verify kết quả → calibration quyết định trả lời
hoặc abstain.

Model dùng nguyên bản **Qwen/Qwen3-14B** (revision
`40c069824f4251a91eefaf281ebe4c544efd3e18`, Apache-2.0, 14.77B tham số, GGUF
Q4_K_M) chạy offline bằng llama.cpp CUDA 12.8 trong Docker. Không fine-tune LLM;
chỉ train một calibration logistic regression nhỏ trên train set.

Kết quả nội bộ: public_test nộp đủ **1000/1000 câu**, 234 câu trả lời
(coverage 23.4%). Trên hard-set train (đo riêng planner, tắt calibration): PA
0.66 ở 50 câu, 0.17 ở 100 câu, 0.10 ở 200 câu. Docker smoke 10 câu chạy offline
thành công, hai lần cho kết quả giống hệt; tốc độ ~9.75 s/câu trên RTX 3060.

## English short

Team **MH** built a **context-first, template-selection** DataMate system. Raw
shop files are canonicalized into `c_*`/`v_*`; each shop README is compiled with
its schema and data snapshot into a typed **Business Context**. A catalog of
predefined query templates is generated from the metric registry and the shop's
actual capabilities. Qwen3-14B only selects a `template_id` and fills closed-set
parameters; deterministic code renders and executes SQL, verifies the result,
and calibration decides whether to answer or abstain.

We use the original **Qwen/Qwen3-14B** (revision
`40c069824f4251a91eefaf281ebe4c544efd3e18`, Apache-2.0, 14.77B parameters, GGUF
Q4_K_M) fully offline with llama.cpp CUDA 12.8. No LLM fine-tuning; only a small
logistic-regression calibration is trained on the training split. The public
submission covers all 1000 questions (234 answered, 23.4% coverage). Docker smoke
tests ran offline and were bit-identical across two runs.

## Bản đầy đủ

### 1. Bài toán và cách tiếp cận

Mỗi shop có bộ file thô khác nhau (CSV/XLSX/SQLite), README riêng, quy ước
nghiệp vụ riêng. Điểm khó không phải SQL mà là **hiểu đúng nghiệp vụ của từng
shop** và chọn đúng nguồn dữ liệu. Vì vậy hệ thống ưu tiên:

1. Chuẩn hoá dữ liệu và nghiệp vụ bằng code.
2. Cho LLM chọn trong một **tập truy vấn đóng** thay vì sinh SQL tự do.
3. Verify và calibration trước khi trả lời (sai = −1, bỏ = 0).

### 2. Kiến trúc

```text
Raw files
  → ingest / clean
  → canonical c_* / views v_*
  → Business Context (README + mapping + snapshot)
  → Template Catalog (metric registry × capability)
  → LLM planner (chọn template_id + params)
  → deterministic SQL compile + DuckDB execute
  → result verifier
  → calibration (answer / abstain)
```

- **Business Context**: đọc đủ mô tả dataset, `## File`, mô tả cột,
  `## Quy ước`; thêm snapshot (số dòng/đơn/sản phẩm/khách, khoảng ngày, trạng
  thái, kênh, nhóm hàng, hàng mẫu). Không hardcode theo `business_id`.
- **Template Catalog**: sinh từ `engine/registry.py` (metric đã code) và
  capability thật (`v_*`, data caps). Các dạng: tổng, xếp hạng theo chiều,
  tỷ trọng, so sánh kỳ, chuỗi/trend, point-in-time, threshold.
- **LLM planner**: Qwen3-14B chỉ trả JSON `{template_id, params, filters, time,
  confidence, evidence}`. Không tự tạo template, không viết SQL.
- **Executor**: `engine/compile.py` render SQL deterministic; sandbox chỉ cho
  SELECT/WITH; DuckDB chạy trên view canonical.
- **Verifier**: chặn SQL lỗi, rỗng với câu xếp hạng, NULL ở câu số, phần trăm
  ngoài miền, sai shape.
- **Calibration**: logistic regression quyết định trả lời/abstain theo PA.

### 3. Model và dữ liệu

| Hạng mục | Giá trị |
|---|---|
| Model | Qwen/Qwen3-14B |
| Revision | `40c069824f4251a91eefaf281ebe4c544efd3e18` |
| License | Apache-2.0 |
| Parameters | 14,768,307,200 (14.77B) |
| Inference weights | GGUF Q4_K_M, đóng trong image |
| Runtime | llama.cpp CUDA 12.8, offline |
| Fine-tuning | Không |

- Train/validation: bộ train của BTC (30 shop, 3000 câu hỏi + đáp án).
- Không dùng public/private test để train; không thu thập đáp án test.
- Calibration train bằng `dev/calibrate.py`; train data và
  `data_manifest.json` nằm trong `training_code/`.

### 4. Kết quả nội bộ

- Public_test: nộp đủ **1000/1000** câu; **234** câu trả lời; coverage **23.4%**
  (number 180, list 19, date 14, string 12, percent 9).
- Hard-set train, đo riêng planner (`DECIDER=off`): PA **0.66** (50 câu),
  **0.17** (100 câu), **0.10** (200 câu).
- LLM judge proxy trên 109 câu trả lời của public_test (311 câu đầu): 87 đúng /
  22 sai, PA 0.596, precision 0.798.
- Docker smoke 10 câu: exit 0, hai lần giống hệt; ~9.75 s/câu trên RTX 3060;
  private 500 câu ước ~81 phút + load, dưới giới hạn 6 giờ.

Các số trên là đo nội bộ, không phải điểm chấm chính thức của BTC.

### 5. Đóng gói và tái lập

- Image `linux/amd64`, base `ghcr.io/ggml-org/llama.cpp:server-cuda`
  (CUDA 12.8), model + calibration + training code + train data nằm trong image.
- Entry point `/code/predict.sh` không tham số: khởi động llama-server local,
  đọc `/data` (read-only), ghi `/result/submission.jsonl` và
  `/result/logs/answers.jsonl`.
- Log mỗi câu có `id`, `answer`, `elapsed_ms`, `thinking` (null), `code`,
  `output`, `inputs`.
- Greedy decoding (`temperature=0`, `seed=0`); hai lần chạy smoke cho
  `submission.jsonl` giống hệt.
- Ảnh `.tar` uncompressed: **13,134,734,848 bytes** (<100GB).

### 6. Hạn chế đã biết

- Coverage public_test còn thấp (23.4%) do nhiều câu cần capability chưa có
  (đếm ngày theo ngưỡng, công nợ, quy đổi đơn vị giá) và mapping một số shop
  chưa tạo được `v_lines`/`v_imports`.
- Một số câu `revenue.total` còn thiếu filter `category`/`pay_method`.
- Chưa fine-tune LLM; chất lượng phụ thuộc Qwen3-14B và context.
