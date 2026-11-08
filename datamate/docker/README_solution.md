# DataMate — Zalo AI Challenge 2026

## Approach

Pipeline trả lời câu hỏi nghiệp vụ từ file thô của từng shop:

1. Ingest CSV/XLSX/SQLite → canonical tables `c_*` → views `v_*`.
2. Compile README + mapping + snapshot thành **Business Context** (luật doanh thu,
   huỷ/trả, đơn vị, dòng đặc biệt, cột đã map, phân bố dữ liệu).
3. Sinh **catalog template** từ metric registry + capability thật của shop.
4. LLM (Qwen3-14B) **chỉ chọn template_id + tham số** trong tập đóng; không viết
   SQL tự do. Code render SQL bằng `engine/compile.py`, chạy DuckDB và verify.
5. Calibration quyết định trả lời hay abstain.

Fallback deterministic dùng cùng registry/template khi LLM không chọn được.

## Models

| Field | Value |
|---|---|
| Model | Qwen/Qwen3-14B |
| Public source | https://huggingface.co/Qwen/Qwen3-14B |
| Fixed revision | `40c069824f4251a91eefaf281ebe4c544efd3e18` |
| License | Apache-2.0 |
| Parameters | 14,768,307,200 (14.77B, ≤15B) |
| Original release | Qwen3 family, 2025-04-29; HF revision last modified 2025-07-26 |
| Inference weights | Local GGUF Q4_K_M at `/code/models/Qwen3-14B-Q4_K_M.gguf` |
| Runtime | llama.cpp `server-cuda` (CUDA 12.8), offline |

Không fine-tune LLM. Calibration là logistic regression nhỏ, train trên train set
( xem `training_code/` ).

## Data

- Train/validation: bộ train của BTC (30 shop), đóng gói trong
  `/code/training_code/data/train/`.
- Không dùng public/private test để train; không thu thập đáp án test.
- `data_manifest.json` liệt kê path, size, SHA-256, counts và nguồn model.

## Run

BTC chạy:

```bash
docker run --rm --gpus '"device=0,1"' --network none --shm-size=16g \
  --entrypoint bash \
  -v /path/to/public_test:/data:ro \
  -v /path/to/output:/result \
  zaic2026_datamate_<team>:final /code/predict.sh
```

`predict.sh`:
1. Khởi động llama.cpp local với model trong image.
2. Chờ `/health`.
3. Chạy `predict.py --split ""` đọc `/data`, ghi `/result`.

Không có network, không tải model, không gọi API ngoài. `/data` chỉ đọc; cache ghi
vào `/tmp/datamate_cache`.

## Output

- `/result/submission.jsonl`: mỗi dòng `{id, type, answer?}`.
- `/result/logs/answers.jsonl`: mỗi câu một record:
  - `id`, `answer`, `elapsed_ms`
  - `thinking`: `null` (thinking tắt)
  - `code`: SQL đã chạy hoặc `engine/compile.py::compile_spec` + `inputs`
  - `output`: giá trị trả về
- `/result/logs/decisions.jsonl`: log nội bộ đầy đủ để kiểm tra.
- `/result/logs/llama-server.log`: log model server.

## Reproducibility

- LLM greedy: `temperature=0`, `seed=0`; llama.cpp một slot/4 slot cố định.
- Thứ tự câu hỏi và business được sort.
- Nên chạy image 2 lần trên cùng input; so sánh `submission.jsonl` hoặc PA trên
  train (có `answers.jsonl`).

## Build

```bash
# context là thư mục datamate/, model đặt ở models/Qwen3-14B-Q4_K_M.gguf
docker build --platform linux/amd64 -f docker/Dockerfile \
  -t zaic2026_datamate_<team>:final .
```
