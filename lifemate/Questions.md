# Câu hỏi cần trả lời trước khi implement LifeMate

> Trả lời ngay dưới mỗi câu (viết `Trả lời:` hoặc xoá dòng default). Bỏ trống = chấp nhận default.
> Bối cảnh máy hiện tại: **Apple M5, 24 GB RAM, không GPU NVIDIA** (chạy MPS), internet OK, HF cache trống.

---

## A. CHẶN — không có thì phải đoán, có thể chọn sai hướng

### A1. Công thức chấm thật của BTC là gì?

Gói dữ liệu chỉ nói: *"BTC chấm bằng cách replay `tool_calls` trong file nộp trên `state.json` ban đầu bằng đúng gói này, rồi so state với đáp án và tính F1 trên call"* (`train+public_test/<split>/zaic_tools/README.md:3`). Cần biết:

- [ ] F1 khớp theo `(name, arguments)` **hay chỉ `name`**?
      (gold có `contacts.search {"query":"Lan"}` — nếu khớp chặt thì phần đọc gần như không ăn điểm)
- [ ] **State có được tính điểm không**, hay chỉ để kiểm tra?
- [ ] Trọng số giữa F1-call và state?
- [ ] Có bằng / mốc chấm khác không (ví dụ chỉ tính trên các app có thay đổi state)?

**Default nếu không trả lời:** coi như mô tả trên; đo **cả hai** trong `eval/metrics.py`; ưu tiên F1-call.

**Kênh liên hệ BTC:** có (email/nhóm/đầu mối) / không

> Trả lời:

---

### A2. Lượt nộp cuối là `public_test` hay `private_test` (Docker)?

- [ ] Lượt nộp đang chạy là `public_test` (634 mẫu, có audio sẵn)
- [ ] Phải sẵn sàng cho `private_test` (docker, **không có audio** → phải chạy ASR trong container)

Nếu là private/docker cần biết thêm:
- [ ] RAM / CPU / thời gian limit của container?
- [ ] Base image được phép (vd `python:3.12-slim`)? Có GPU không?
- [ ] Model được bundle trong image hay tải lúc chạy? (plan nói "không dùng mạng khi inference")

**Default:** tối ưu cho `public_test`, nhưng giữ `infer.py` chạy được offline với model đã bundle.

> Trả lời:

---

### A3. Có được dùng mô hình lớn hơn Qwen3-4B không?

24 GB unified memory: 4B (≈8 GB bf16) thoải mái; 8B/14B chậm hơn ~2–3×.
Plan đang hard-code `LLM_MODEL = "Qwen/Qwen3-4B"`.

- [ ] Giữ Qwen3-4B
- [ ] Được dùng Qwen3-8B / 14B nếu đo ra tốt hơn
- [ ] Gợi ý model khác: ____________________

**Default:** Qwen3-4B (đổi được sau bằng 1 biến config).

> Trả lời:

---

### A4. Có GPU/NVIDIA ở đâu khác không (máy khác, cloud, thuê)?

Ảnh hưởng trực tiếp tới chi phí chạy:
ASR ≈ 2 200 lượt chính (train 1545 + public 634) + ≈ 2 630 lượt trong `history`;
LLM ≈ 2 200 lượt scope + ≈ 2 200 lượt planner. Trên M5 đây là **vài chục giờ**.

- [ ] Không có, chạy M5
- [ ] Có: ____________________ (GPU/VRAM?)

**Default:** chạy trên M5 (MPS), ưu tiên model nhỏ + cache aggressive.

> Trả lời:

---

### A5. Hạn chót thực tế + quy mô đội?

- [ ] Hạn chót: ____________
- [ ] Số người phụ trách code: ____________
- [ ] Có chạy full 1545 mẫu train cho mỗi lần ablation được không, hay chỉ ~300 mẫu held-out?

**Default:** ablation trên 300 mẫu held-out, full train 1 lần để xác nhận.

> Trả lời:

---

## B. QUAN TRỌNG — ảnh hưởng chất lượng; tôi tự quyết được nếu bạn không nói

### B1. Được dùng `label.audio_text` của train để **fine-tune** không?

Train có 1545 mẫu có nhãn đầy đủ (1 217 act + 217 ask). Fine-tune planner (LoRA Qwen3-4B) hoặc fine-tune ASR có thể tăng đáng kể call-F1 so với prompt thuần.

- [ ] Không fine-tune (đúng plan: chỉ phân tích + few-shot retrieval)
- [ ] Có, cho phép LoRA planner
- [ ] Có, cho phép fine-tune ASR

**Default:** không fine-tune.

> Trả lời:

---

### B2. Mô hình đã tải sẵn chưa / lưu ở đâu?

HF cache hiện trống. Cần: `Qwen/Qwen3-4B`, `vinai/PhoWhisper-medium` (hoặc `Qwen/Qwen3-ASR-0.6B`/`1.7B`), có thể thêm `Qwen3-ASR-1.7B` để so sánh.

- [ ] Đã có sẵn ở: ____________________
- [ ] Được tải về `models/` trong repo (không dùng HF cache)

**Default:** tôi tải về `models/` trong repo.

> Trả lời:

---

### B3. Cấu trúc repo cuối cùng?

Plan §2 đặt `lifemate/` + `scripts/`, `eval/`, `tests/` cạnh `train+public_test/`. Hiện tại repo chỉ có `Planning.md` + `train+public_test/`.

- [ ] Đúng như plan §2: `lifemate/`, `scripts/`, `eval/`, `tests/`, `config.py` ở gốc, data ở `train+public_test/`
- [ ] Khác: ____________________

**Default:** đúng plan §2.

> Trả lời:

---

### B4. Agent có được "hỏi linh hoạt" không?

Tôi đã verify: gold `sys.ask_missing_info` luôn trỏ `tool_name` là tool **đã cài** (217/217 mẫu). Câu hỏi: có mẫu nào cần hỏi thông tin **không suy ra được** mà vẫn gọi `ask` (ví dụ "gọi cho Minh" nhưng danh bạ không có Minh)?

- [ ] Không, chỉ hỏi khi thiếu tham số bắt buộc (đúng plan)
- [ ] Được hỏi linh hoạt (thêm ablation)

**Default:** chỉ hỏi khi thiếu tham số bắt buộc.

> Trả lời:

---

### B5. Giới hạn số lượt/lệnh?

Plan: `MAX_TURNS = 6`, `MAX_WRITES = 8`. Vòng B2 (gọi tool đọc có tham số rồi mới ghi) là chiến lược chính.

- [ ] Giữ `MAX_TURNS = 6`, `MAX_WRITES = 8`
- [ ] Muốn: ____________________

**Default:** giữ nguyên.

> Trả lời:

---

## C. MẶC ĐỊNH — không cần trả lời (trừ khi muốn đổi)

| # | Mặc định tôi sẽ đi |
|---|---|
| C1 | Python 3.12 trong venv `.venv`, torch CPU/MPS (`PYTORCH_ENABLE_MPS_FALLBACK=1`) |
| C2 | Không network lúc inference; model nằm trong `models/` |
| C3 | Seed cố định, LLM greedy, không fine-tune |
| C4 | `submission.jsonl` đúng format README (1 dòng/mẫu) + `runs/<tên>/metrics.json` + `debug/<id>.json` |
| C5 | Test bằng `pytest tests/` (thêm `pytest` vào dev deps) |
| C6 | Không commit gì — repo hiện **chưa phải git**; có muốn `git init` + commit từng mốc M0…M6 không? |

> Ghi chú/điều chỉnh cho C:

---

## Ghi chú thêm (nếu có)

> Trả lời:
