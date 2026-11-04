# Câu hỏi đã trả lời — quyết định trước khi implement LifeMate

> **Đây là RECORD, không phải spec.** Nguồn chuẩn cho quy tắc hiện thực là [`EXECUTION-PLAN.md`](EXECUTION-PLAN.md); file này chỉ lưu lại lựa chọn đã chốt và *việc còn phải xác nhận*.
> **Trạng thái:** đã chốt 2026-11-03. Mục đích: ghi lại lựa chọn để implement không hỏi lại, và để các bước sau (M4+) biết phải đo gì.
> Bối cảnh máy: **Apple M5, 24 GB RAM, không GPU NVIDIA** (chạy MPS), internet OK, HF cache trống.

---

## A. CHẶN

### A1. Công thức chấm của BTC
**Trả lời:** *Đo cả hai, ưu tiên F1-call.*
→ `eval/metrics.py` xuất **F1-call** (khớp theo `(name, arguments)` **và** biến thể chỉ khớp `name`) + tỉ lệ khớp `state_hash` + khớp state từng app. Mọi knob liên quan read/prefetch để ablation (mục 1.1 của `EXECUTION-PLAN.md`).

### A2. Lượt nộp (public vs private/docker)
**Trả lời:** *Container private được gọi API thoải mái* ⇒ **không cần bundle model**, không có ràng buộc offline.
→ Mặc định: tối ưu `public_test` (634 mẫu), `infer.py` vẫn chạy được với API ở cả local lẫn container.

### A3. Size LLM
**Trả lời:** *Qwen3-4B* — qua API OpenAI-compatible (nên "size" chỉ là model id phía server).

### A4. GPU
**Trả lời:** *Có API* — không cần GPU cục bộ. LLM **và** STT đều gọi qua API.

### A5. Hạn chót / quy mô
**Trả lời:** chưa chốt cụ thể → dùng mặc định:
- Lộ trình: **M0 → M1 → M3 → M2 → M4 → M5 → M6** (theo `EXECUTION-PLAN.md` mục 8).
- Ablation: **300 mẫu held-out** (đủ để so cấu hình), xác nhận 1 lần bằng full train khi có thời gian.
- Ưu tiên nếu thiếu thời gian: M0 → M1 → M3 → M2.

---

## B. QUAN TRỌNG

### B1. Fine-tune
**Trả lời:** *Không fine-tune.* `label.audio_text` chỉ dùng để phân tích (Pha 0) + few-shot retrieval (M4).

### B2. Mô hình đã tải sẵn
**Trả lời:** *Dùng API* ⇒ không cần tải model về máy.

### B3. Cấu trúc repo
**Trả lời:** mặc định theo `EXECUTION-PLAN.md` mục 6: `lifemate/` + `config.py` + `scripts/` + `eval/` + `tests/` ở gốc repo, data ở `train+public_test/`.

### B4. Hỏi linh hoạt
**Trả lời:** mặc định — chỉ gọi `sys.ask_missing_info` khi **thiếu tham số bắt buộc** (đã verify: gold 217/217 mẫu ask trỏ `tool_name` là tool đã cài).

### B5. Giới hạn lượt/lệnh
**Trả lời:** mặc định `MAX_TURNS = 6`, `MAX_WRITES = 8`.

---

## C. MẶC ĐỊNH đã chọn (áp dụng luôn, không cần hỏi lại)

| # | Quyết định |
|---|---|
| C1 | Python **3.12** trong venv `.venv`; thư viện: `numpy`, `soundfile`, `openai` (+ `pytest` cho test). Không cần `torch`/`transformers` |
| C2 | LLM + STT gọi **OpenAI-compatible API**; có retry/backoff; **không** network-offline, **không** bundle model |
| C3 | Seed cố định, `temperature=0` (greedy), không fine-tune |
| C4 | Xuất `submission.jsonl` đúng format README (1 dòng/mẫu) + `runs/<tên>/metrics.json` + `debug/<id>.json` |
| C5 | Test bằng `pytest tests/` |
| C6 | **`git init` + commit theo từng mốc M0…M6** (đã được duyệt). Chỉ commit khi tới mốc, không commit file rác/cache/model |
| C7 | Metric ưu tiên: **F1-call**; hash là chỉ số phụ (mục 1.1 `EXECUTION-PLAN.md`) |
| C8 | ASR 2 mode: `api` (STT thật) và `gold` (`label.audio_text`, đo trần harness) — `ASR_MODE` trong `config.py` |

---

## VIỆC CÒN THIẾU — cần điền vào env/config trước khi chạy thật

> Không có 3 giá trị này thì mọi lượt gọi API đều fail. Tôi để placeholder trong `config.py`, điền qua biến môi trường.

| Biến môi trường | Nội dung cần điền | Ghi chú |
|---|---|---|
| `LIFEMATE_LLM_BASE_URL` | vd `https://api.openai.com/v1` hoặc endpoint của provider | OpenAI-compatible |
| `LIFEMATE_LLM_API_KEY` | key | **Không** commit key vào repo |
| `LIFEMATE_LLM_MODEL` | model id có tool-calling, vd `gpt-4o-mini` | phải hỗ trợ `tools` |
| `LIFEMATE_STT_BASE_URL` | endpoint STT (OpenAI-compatible `audio/transcriptions`) | |
| `LIFEMATE_STT_API_KEY` | key (nếu khác key LLM) | |
| `LIFEMATE_STT_MODEL` | model id STT, vd `whisper-1`, `gpt-4o-mini-transcribe`, `Qwen3-ASR-...` | chọn theo WER + lỗi thực thể (M2) |

### Cần xác nhận thêm về endpoint (chưa rõ)
1. Endpoint có hỗ trợ **tool-calling** (`tools`/`tool_choice`) không? Nếu không → phải đổi model hoặc dùng fallback text-JSON (đã ghi trong `EXECUTION-PLAN.md` 6.9).
2. STT có hỗ trợ `temperature > 0` để lấy **n-best** không? Nếu không → chỉ có 1 transcript, mất `alt_values` của resolver (đã ghi trong 5.5).
3. STT có trường `prompt` (hotwords/context) không? (quyết định `ENABLE_HOTWORD_REASR`).
4. Có rate-limit/giới hạn đồng thời không (để chọn số worker khi gọi song song).

---

## Ghi chú thêm (nếu có)

> Trả lời:
