# 1vin — Zalo AI Challenge 2026

Kho mã nguồn cho hai bài toán của đội thi tại **Zalo AI Challenge 2026 (ZAC 2026)**.
Mỗi bài toán nằm trong một thư mục riêng, dùng chung một số quy ước kỹ thuật (Python, mô hình qua API, định dạng nộp bài).

| | **DataMate** (`datamate/`) | **LifeMate** (`lifemate/`) |
|---|---|---|
| Bài toán | Trả lời câu hỏi nghiệp vụ bằng **dữ liệu bán hàng thô** (Excel/CSV/SQLite) | Agent **gọi tool** theo yêu cầu bằng **giọng nói tiếng Việt** (ASR → LLM → tool) |
| Dữ liệu | Train: 30 shop / 3000 câu · Public test: 14 shop / 1000 câu | Train: 1545 mẫu · Public test: 634 mẫu (có audio) |
| Đầu vào | `questions.jsonl` (câu hỏi + `as_of_date`) + dữ liệu shop + `rulebook.md` | Audio `.wav` + `state.json` của các app + catalog tool |
| Đầu ra | `submission.jsonl`: `{id, type, answer}` | `submission.jsonl`: `{id, tool_calls, state_hash}` |
| Cách chấm | Đúng **+1**, sai **−1**, bỏ trống **0** (PA) | **F1 trên tool call** và tỉ lệ khớp `state_hash` |
| Mô hình | `Qwen3-4B-Instruct` qua API OpenAI-compatible | `Qwen3-4B` (tool-calling) + STT qua API OpenAI-compatible |
| Tài liệu thiết kế | [`datamate/Planning.md`](datamate/Planning.md) · [`datamate/Questions.md`](datamate/Questions.md) | [`lifemate/Planning.md`](lifemate/Planning.md) · [`lifemate/Questions.md`](lifemate/Questions.md) |

---

## Mục lục

- [Cấu trúc thư mục](#cấu-trúc-thư-mục)
- [Yêu cầu & cài đặt](#yêu-cầu--cài-đặt)
- [Chạy nhanh](#chạy-nhanh)
- [Bộ dữ liệu](#bộ-dữ-liệu)
- [Quy ước chung cho code](#quy-ước-chung-cho-code)
- [Tài liệu](#tài-liệu)
- [Trạng thái dự án](#trạng-thái-dự-án)

---

## Cấu trúc thư mục

```text
1vin/
├── README.md                       # tài liệu này
├── .gitignore                      # loại trừ venv, cache, dữ liệu lớn, bí mật
│
├── datamate/                       # Bài toán 1 — QA trên dữ liệu doanh nghiệp
│   ├── README.md                   # tài liệu riêng của bài toán
│   ├── Planning.md                 # kế hoạch chi tiết M0 → M14
│   ├── Questions.md                # biên bản quyết định đã chốt
│   ├── train/                      # dữ liệu train (có nhãn)
│   │   ├── questions.jsonl         #   câu hỏi + as_of_date
│   │   ├── answers.jsonl           #   đáp án tham chiếu
│   │   ├── rulebook.md             #   luật nghiệp vụ (bộ train)
│   │   ├── calendar.csv            #   lịch dương + âm 2024-01-01 → 2027-12-31
│   │   └── data/biz_1xx/           #   dữ liệu từng shop (+ README mô tả cột)
│   ├── public_test/                # dữ liệu thi (không nhãn)
│   │   ├── questions.jsonl
│   │   ├── rulebook.md             #   bộ test: thêm 3 ngành mới, ~12 luật mới
│   │   └── data/dev_0xx/           #   dữ liệu 14 shop
│   └── .venv/                      # môi trường Python 3.12 (không commit)
│
└── lifemate/                       # Bài toán 2 — agent gọi tool bằng giọng nói
    ├── README.md                   # tài liệu riêng của bài toán
    ├── Planning.md                 # kế hoạch chi tiết M0 → M6
    ├── Questions.md                # câu hỏi cần trả lời trước khi implement
    └── train+public_test/          # gói dữ liệu chính thức của BTC
        ├── README.md               #   mô tả gói dữ liệu (do BTC cung cấp)
        ├── VERSION                 #   release: v3.2.0
        ├── train/                  #   1545 mẫu có nhãn + audio + environment
        └── public_test/            #   634 mẫu thi + audio + environment
```

> **Lưu ý:** thư mục `datamate/train/data/`, `datamate/public_test/data/`, `lifemate/train+public_test/*/audio/` và `*_environment/` bị `.gitignore` loại trừ — dữ liệu lớn, không commit. Xem [Bộ dữ liệu](#bộ-dữ-liệu).

---

## Yêu cầu & cài đặt

- **Python ≥ 3.10** (dùng 3.12 trong venv)
- **Git** (để kéo dữ liệu và quản lý phiên bản)
- **API OpenAI-compatible** cho LLM (và STT ở bài LifeMate) — cấu hình qua biến môi trường, **không** hard-code key

```bash
# 1) Tạo môi trường (riêng cho từng bài toán)
cd datamate && python3.12 -m venv .venv && source .venv/bin/activate
pip install pandas openpyxl duckdb numpy rapidfuzz scikit-learn joblib pyarrow httpx pytest

cd ../lifemate && python3.12 -m venv .venv && source .venv/bin/activate
pip install numpy soundfile openai httpx pytest
```

Biến môi trường dùng chung:

```bash
# LLM (DataMate)
export DATAMATE_LLM_BASE_URL="https://<endpoint>/v1"
export DATAMATE_LLM_API_KEY="<key>"
export DATAMATE_LLM_MODEL="Qwen3-4B-Instruct"

# LLM + STT (LifeMate)
export LIFEMATE_LLM_BASE_URL="https://<endpoint>/v1"
export LIFEMATE_LLM_API_KEY="<key>"
export LIFEMATE_LLM_MODEL="Qwen3-4B"
export LIFEMATE_STT_BASE_URL="https://<endpoint>/v1"
export LIFEMATE_STT_API_KEY="<key>"
export LIFEMATE_STT_MODEL="<stt-model-id>"
```

---

## Chạy nhanh

Mỗi bài toán có README riêng với lệnh chi tiết. Tóm tắt:

```bash
# DataMate — chấm submission trên tập train
cd datamate
python dev/evaluate.py --submission public_test/submission.jsonl --answers train/answers.jsonl

# DataMate — sinh submission cho public test (split/đường dẫn đọc từ config.py)
python predict.py

# LifeMate — chạy agent trên một split, xuất metrics + submission
cd ../lifemate
python eval/run.py --split public_test --ids heldout_ids.txt --asr real --out runs/<ten>
python infer.py
```

---

## Bộ dữ liệu

### DataMate

| Tệp | Nội dung |
|---|---|
| `questions.jsonl` | `{id, business_id, question, as_of_date}` — `as_of_date` là "hôm nay" của câu hỏi |
| `answers.jsonl` | `{id, type, answer, alias}` — `answer = null` ⇔ câu `unanswerable` |
| `rulebook.md` | Luật nghiệp vụ (doanh thu, công nợ, kho, xếp hạng, thời gian, định dạng đáp án) |
| `calendar.csv` | `date,weekday,lunar_day,lunar_month,lunar_year,lunar_leap,holiday` |
| `data/<business>/` | Dữ liệu shop: xlsx / csv / sqlite; mỗi shop có `README.md` mô tả cột và quy ước |

Phân bố 3000 câu train: `number` 1884 · `percent` 578 · `list` 193 · `date` 145 · `string` 88 · `unanswerable` 70 · `boolean` 23 · `table` 19.

### LifeMate

Gói dữ liệu do BTC cung cấp — xem [`lifemate/train+public_test/README.md`](lifemate/train+public_test/README.md) để biết chi tiết định dạng `*.jsonl`, catalog tool, `state.json` và cách chạy `zaic_tools`.

> **Bản quyền dữ liệu:** gói LifeMate chỉ cung cấp cho các đội thi đã đăng ký trong khuôn khổ ZAC 2026. Không chia sẻ, phát tán hay commit lại gói dữ liệu này ra ngoài.

---

## Quy ước chung cho code

Áp dụng cho **cả hai** bài toán:

- **Không hard-code bí mật.** `api_key`, `base_url`, `model` đọc từ biến môi trường hoặc `config.py`; `.env` bị git-ignore.
- **Không ràng buộc theo id.** Không có `if business_id == ...` hay logic riêng cho một câu hỏi/id cụ thể.
- **Tất định.** Seed cố định, LLM `temperature = 0`. Cache theo `sha256` nội dung đầu vào, không theo tên.
- **Sắp xếp trước khi quyết định.** Mọi duyệt `dict`/`set` đưa vào so sánh phải `sorted(...)`.
- **Type hints + test.** Mọi hàm có type hints, có test tương ứng trong `tests/`.
- **Ghi log đủ để debug.** Artefact sinh ra nằm ở `cache/`, `reports/`, `runs/`, `debug/`, `logs/` (đều bị git-ignore) — không commit output sinh tự động.
- **Tiếng Việt giữ dấu.** Bản bỏ dấu chỉ dùng để so khớp tên, không dùng để sinh câu trả lời hay trong prompt.
- **Không commit dữ liệu lớn / model.** Theo `.gitignore`.

---

## Tài liệu

| Tệp | Nội dung |
|---|---|
| [`datamate/Planning.md`](datamate/Planning.md) | Kiến trúc, hợp đồng dữ liệu, milestone M0 → M14 kèm tiêu chí nghiệm thu |
| [`datamate/Questions.md`](datamate/Questions.md) | Biên bản quyết định đã chốt (LLM, cách chấm, nghiệp vụ, so khớp chuỗi) |
| [`lifemate/Planning.md`](lifemate/Planning.md) | Kiến trúc pipeline, quy ước, chi tiết từng module, lộ trình M0 → M6 |
| [`lifemate/Questions.md`](lifemate/Questions.md) | Câu hỏi còn bỏ ngỏ cần BTC/đội trưởng trả lời |
| [`lifemate/train+public_test/README.md`](lifemate/train+public_test/README.md) | Tài liệu gói dữ liệu chính thức của BTC |

---

## Trạng thái dự án

> **Hiện tại repo ở trạng thái thiết kế + dữ liệu; mã nguồn chưa được implement.**
> Hai tệp `Planning.md` và `Questions.md` của mỗi bài toán đã đủ chi tiết để bắt đầu code (từng file, từng hàm, từng test, tiêu chí nghiệm thu).

Các bước tiếp theo:

1. **DataMate** — làm theo thứ tự phụ thuộc `M0 → M1 → M2/M3/M6 → M4 → M5 → M7 → M8 → M9 → M14`.
   Cổng kiểm soát quan trọng nhất: sau M8, phần deterministic phải tái hiện được ≥ 90% đáp án tham chiếu — nếu chưa thì LLM chỉ che lỗi chứ không sửa lỗi.
2. **LifeMate** — ưu tiên `M0 → M1 → M3 → M2 → M4 → M5`. M1 (chạy với transcript vàng) cho sẵn một agent chạy được; mọi mốc sau đo độ cải thiện so với nó.
3. **Cả hai** — chốt công thức chấm thật của BTC (LifeMate §1.1, DataMate §5) trước khi tối ưu, và đo **cả hai chỉ số** thay vì chỉ một.

---

## Giấy phép

Mã nguồn trong repo thuộc về đội thi. Dữ liệu giữ bản quyền của BTC theo điều khoản của ZAC 2026.
