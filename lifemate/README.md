# LifeMate

Trợ lý giọng nói: nghe yêu cầu bằng **giọng nói tiếng Việt** → hiểu → **gọi tool** trên các app thật (nhắn tin, lịch, báo thức, đèn, ngân hàng…) → trả lời.

> Bài toán 2/2 của đội thi tại **Zalo AI Challenge 2026**. Xem [`README.md` gốc repo](../README.md) để so sánh với bài DataMate.

---

## Mục lục

- [Bài toán](#bài-toán)
- [Dữ liệu](#dữ-liệu)
- [Pipeline](#pipeline)
- [Cấu trúc code mục tiêu](#cấu-trúc-code-mục-tiêu)
- [Cài đặt](#cài-đặt)
- [Chạy](#chạy)
- [Định dạng nộp bài](#định-dạng-nộp-bài)
- [Lộ trình milestone](#lộ-trình-milestone)
- [Bất biến bắt buộc](#bất-biến-bắt-buộc)
- [Tài liệu](#tài-liệu)

---

## Bài toán

**Đầu vào:** mỗi mẫu là một mệnh đề bằng giọng nói (`audio/<id>/<id>.wav`) cùng bối cảnh người dùng (`context`: thời gian, vị trí, hồ sơ, các app đã cài) và lịch sử hội thoại trước.

**Đầu ra:** chuỗi tool call + hash trạng thái app cuối cùng.

**Ba nhãn hành vi** trong dữ liệu train:

| Nhãn | Dấu hiệu | Cần làm |
|---|---|---|
| `act` | gold có tool call ghi | Thực thi đúng tool, đúng tham số |
| `ask` | gold có `sys.ask_missing_info` | Hỏi bổ sung tham số bắt buộc |
| `refuse` | gold `tool_calls == []` | **Không gọi tool nào** (kể cả tool đọc) |

**Ba khó khăn chính:**

1. **Mọi lời gọi `env.call` đều bị ghi log và nộp bài.** Ngoài phạm vi phải trả `[]` — nên phải biết yêu cầu *có nằm trong phạm vi* **trước khi** gọi bất kỳ tool đọc nào.
2. **Cấm đọc `state.json`.** ID thiết bị, danh bạ… chỉ lấy được qua tool đọc → phải *prefetch* trước rồi mới lập kế hoạch.
3. **Lệnh ghi không hoàn tác được.** Mỗi mẫu chỉ có một `ToolEnv`; "thử rồi sửa" trên lệnh ghi là hỏng. Phải *plan → kiểm tra → mới thực thi*.

---

## Dữ liệu

Gói dữ liệu chính thức do BTC cung cấp — mô tả đầy đủ tại [`train+public_test/README.md`](train+public_test/README.md).

```text
lifemate/train+public_test/
├── VERSION                          # release v3.2.0, built 2026-10-24
├── train/
│   ├── train.jsonl                  # 1545 mẫu có nhãn
│   ├── train_tools_catalog.json     # schema tool
│   ├── train_environment/<id>/state.json
│   ├── audio/<id>/<id>.wav          # lượt cuối; <id>_u1.wav… cho các lượt trong history
│   └── zaic_tools/                  # thư viện chạy tool local
└── public_test/
    ├── public_test.jsonl            # 634 mẫu, chỉ input
    ├── public_test_tools_catalog.json
    ├── public_test_environment/<id>/state.json
    ├── audio/<id>/
    ├── sample_submission.jsonl
    └── zaic_tools/
```

| | Train | Public test |
|---|---|---|
| Số mẫu | 1545 | 634 |
| Nhãn | `act` + `ask` + `refuse` | không có |
| Audio | có | có |

**Ứng dụng trong catalog (36 app, 122 tool):** nhà thông minh, báo thức, nhắc việc, lịch, ghi chú, việc cần làm, danh bạ, gọi điện, SMS, chat OTT, email, ngân hàng, ví điện tử, thanh toán hóa đơn, chứng khoán, thời tiết, giá vàng, giá xăng, dịch, bản đồ, đặt đồ ăn, đi chợ, công thức nấu ăn, đặt xe, xe buýt, đỗ xe, vé máy bay, vé tàu, mua sắm, danh sách mua sắm, nhạc, truyền hình, vé sự kiện, thói quen, tủ bếp, hệ thống.

**Kind của tool** (trường `kind` trong catalog):

- `read` — chỉ đọc, không đổi state.
- `write` — thay đổi dữ liệu.
- `meta` — `sys.ask_missing_info`.

**`context.installed_apps`** liệt kê các app được phép gọi trong mẫu đó — mỗi mẫu chỉ được gọi tool thuộc app đã cài.

> **Bản quyền:** gói dữ liệu chỉ cung cấp cho đội thi đã đăng ký trong khuôn khổ ZAC 2026. Không chia sẻ, phát tán hay commit lại ra ngoài.

---

## Pipeline

```text
item + catalog
  ├─[1] ASR (chưa có snapshot): audio → n-best
  ├─[2] SCOPE: ngoài phạm vi? → trả [] và kết thúc (chưa gọi tool nào)
  ├─[3] PREFETCH: gọi tool kind=read → snapshot
  ├─[4] LEXICON + RESOLVER: gợi ý thực thể/số/giờ từ n-best + snapshot
  ├─[5] PROMPT + PLANNER (Qwen3-4B, tool-calling gốc)
  ├─[6] GATE: kiểm tra tất định theo schema + snapshot
  ├─[7] EXECUTOR: validate → call (mỗi lệnh ghi đúng một lần); vòng B2 cho bước phụ thuộc
  └─► env.get_tool_calls(), env.get_state_hash()
```

Điểm mấu chốt: **ASR chạy trước prefetch** để mẫu ngoài phạm vi không để lại bất kỳ log đọc nào; và **GATE kiểm tra tất định theo catalog** (`required`, `enum`, `x-ref`, `x-one-of`) chứ không tin vào việc mô hình tự khai — mô hình 4B không fine-tune rất dễ bịa ID, thiếu tham số, hỏi/làm sai.

---

## Cấu trúc code mục tiêu

Theo [`Planning.md`](Planning.md) §2:

```text
lifemate/
├── config.py          # config tập trung (LLM/STT endpoint, knob, giới hạn)
├── apiclient.py       # client OpenAI-compatible + retry/backoff (dùng chung LLM & STT)
├── catalog.py         # nạp & chuẩn hoá tools catalog
├── prefetch.py        # gọi tool read, dựng snapshot
├── lexicon.py         # từ vựng thực thể trong môi trường
├── vi_norm.py         # chuẩn hoá tiếng Việt (giữ dấu / bỏ dấu)
├── resolver.py        # giải thực thể, số, giờ
├── asr.py             # STT qua API (n-best)
├── scope.py           # quyết định ngoài phạm vi
├── llm.py             # client LLM (OpenAI-compatible)
├── prompt.py          # dựng prompt
├── planner.py         # LLM sinh kế hoạch tool call
├── gate.py            # kiểm tra tất định (module quan trọng nhất)
├── executor.py        # validate → call
├── retrieval.py       # few-shot BM25 (có điều kiện)
├── agent.py           # vòng lặp agent
├── infer.py           # chạy trên một split, xuất submission.jsonl
├── scripts/           # inspect_data.py, analyze_train.py, gold_hash.py, split.py
├── eval/              # run.py, metrics.py, asr_eval.py
├── tests/
└── train+public_test/ # dữ liệu
```

---

## Cài đặt

```bash
cd lifemate
python3.12 -m venv .venv
source .venv/bin/activate
pip install numpy soundfile openai httpx pytest
```

Biến môi trường:

```bash
export LIFEMATE_LLM_BASE_URL="https://<endpoint>/v1"
export LIFEMATE_LLM_API_KEY="<key>"
export LIFEMATE_LLM_MODEL="Qwen3-4B"

export LIFEMATE_STT_BASE_URL="https://<endpoint>/v1"
export LIFEMATE_STT_API_KEY="<key>"
export LIFEMATE_STT_MODEL="<stt-model-id>"
```

> Key **không** hard-code, **không** commit. `.env` đã bị `.gitignore` loại trừ.

---

## Chạy

```bash
# 1) Pha 0 — khảo sát dữ liệu, phân tích nhãn, tính gold hash, chia tập
python scripts/inspect_data.py
python scripts/analyze_train.py
python scripts/gold_hash.py
python scripts/split.py

# 2) Đánh giá trên held-out (ASR vàng để đo trần của harness)
python eval/run.py --split train --ids heldout_ids.txt --asr gold --out runs/gold

# 3) Đánh giá với ASR thật
python eval/run.py --split train --ids heldout_ids.txt --asr real --out runs/real

# 4) Sinh submission cho public_test (chạy trong thư mục chứa public_test/)
python infer.py
```

`infer.py` bám theo template của ban tổ chức: mỗi mẫu trong `try/except` để **luôn có đúng một dòng** cho mỗi `id`; `AGENT` (ASR, LLM, catalog) khởi tạo **một lần** ở mức module.

`eval/run.py` xuất `metrics.json` gồm **cả hai** chỉ số: **F1 trên tool call** (khớp theo `(name, arguments)`, thêm biến thể chỉ khớp `name`) **và** tỉ lệ khớp `state_hash` (kèm khớp state từng app), theo nhóm `act/ask/refuse`, theo app; kèm taxonomy lỗi tự động gán: `scope_false_refuse`, `scope_missed_refuse`, `ask_vs_act`, `act_vs_ask`, `wrong_tool`, `wrong_arg_entity`, `wrong_arg_number`, `wrong_arg_time`, `wrong_id`, `gate_dropped_valid`, `exception`.

> **Không được chỉ báo cáo hash.** Công thức chấm thật của BTC chưa chốt (xem [`Questions.md`](Questions.md) A1) — mọi quyết định liên quan phải đo **cả hai** chỉ số.

---

## Định dạng nộp bài

`submission.jsonl` — UTF-8 JSON Lines, **đúng một dòng cho mỗi mẫu** của split:

```json
{"id": "public_0039", "tool_calls": [{"name": "alarm.list", "arguments": {}}, {"name": "alarm.create", "arguments": {"time": "2026-11-11T05:30:00+07:00"}}], "state_hash": "461fcd40…"}
{"id": "public_0003", "tool_calls": [{"name": "sys.ask_missing_info", "arguments": {"tool_name": "music.add_to_playlist", "params": ["playlist_id", "track_id"]}}], "state_hash": "23f1c7d2…"}
{"id": "public_0002", "tool_calls": [], "state_hash": "0c9a2ec0…"}
```

- `tool_calls` — **mọi** tool call đã gọi (`env.get_tool_calls()`), kể cả call bị từ chối; `[]` nếu không gọi tool nào.
- `state_hash` — hash state cuối (`env.get_state_hash()`).

Xem `sample_submission.jsonl` trong gói dữ liệu (3 dòng ví dụ: làm được / thiếu thông tin / ngoài phạm vi).

---

## Lộ trình milestone

Chi tiết đầy đủ (từng module, thuật toán, test bắt buộc) trong [`Planning.md`](Planning.md) §5–§6.

| M | Việc | Hoàn thành khi |
|---|---|---|
| **M0** | `inspect_data.py`, `analyze_train.py`, `gold_hash.py`, `split.py`; điền giá trị `[M0]` trong `config.py`; **chốt công thức chấm** (hoặc ghi rõ giả định) | Có `reports/*.json`; `gold_hash.json` đủ mọi mẫu; tạo `ToolEnv` lần hai không rò trạng thái; `metrics.py` xuất **cả hai** F1-call và hash |
| **M1** | `catalog`, `prefetch`, `lexicon`, `llm`, `prompt`, `planner`, `gate`, `executor`, `agent` (chưa ASR, dùng `--asr gold`), `eval/run.py` | `tests/test_catalog.py`, `tests/test_gate.py` qua; `metrics.json` cho `--asr gold` — đây là **trần của harness** |
| **M2** | `vi_norm.py` + test; `asr.py` (chế độ `api`/`gold`); `eval/asr_eval.py` | Bảng so sánh STT; chốt `STT_MODEL`/endpoint và `ASR_MODE` |
| **M3** | `scope.py`, `resolver.py`, nối ASR thật, tune `SCOPE_LEX_THRESHOLD` | `metrics.json` chế độ `real`; chênh lệch với M1 cho biết phần mất do ASR; mọi mẫu `refuse` của held-out cho `tool_calls == []` |
| **M4** | Bật từng cờ ở §5.15 (độ sâu prefetch, few-shot BM25, hotwords, override, hỏi khi mơ hồ), mỗi lần một ablation | Mỗi cờ có bảng so sánh trên held-out (F1-call + hash); giữ cờ nào tăng điểm |
| **M5** | Che/đổi tên tool trong catalog dev rồi chạy lại (kiểm tra tổng quát hoá); đo thời gian chạy cả split | Độ sụt điểm khi đổi tên tool được ghi nhận; `infer.py` xuất đủ một dòng cho mỗi `id` |
| **M6** | Chạy `infer.py` trên `public_test`, kiểm tra `submission.jsonl` | File nộp qua kiểm tra định dạng |

> **Thứ tự ưu tiên khi thiếu thời gian:** `M0 → M1 → M3 → M2 → M4 → M5`. M1 đã cho một agent chạy được với transcript vàng; mọi mốc sau đều đo độ cải thiện so với nó.

---

## Bất biến bắt buộc

- **Cấm** đọc, copy, parse bất kỳ file nào dưới `<split>_environment/`. Dữ liệu app chỉ lấy qua `env.call`.
- Mỗi mẫu tạo `ToolEnv` **đúng một lần**, trong `infer()`. Truyền `env` xuống các hàm khác, không tạo lại.
- Mọi lời gọi `env.call` phải đi qua `executor.safe_call()` hoặc `prefetch` — không có lời gọi nào ngoài tầm kiểm soát.
- Mọi hàm xử lý dữ liệu từ JSON/LLM phải chịu được khóa thiếu và kiểu sai (`.get`, `isinstance`). Một mẫu lỗi không được làm sập cả lượt chạy.
- Trong prompt cho LLM **giữ nguyên dấu tiếng Việt**; bản bỏ dấu chỉ dùng để so khớp tên. `parse_numbers`/`parse_times` chạy trên **text gốc** (không dùng `normalize()` — nó bỏ dấu câu và làm méo `500.000` / `1,5 triệu`).
- Mỗi mẫu ghi file debug `debug/<id>.json`: `hyps`, `scope`, `snapshot_keys`, `hints`, `planner_raw`, `gate_notes`, `executed` — **bắt buộc**, vì phân tích lỗi cần nó.
- Seed cố định; LLM dùng greedy (`temperature = 0`).
- Không hard-code tên tool/app — mọi thứ đi qua catalog (test có thể có tool/app lạ).
- Artefact sinh ra (`cache/`, `reports/`, `runs/`, `debug/`, `logs/`, `submission.jsonl`) bị `.gitignore` loại trừ.

---

## Tài liệu

| Tệp | Nội dung |
|---|---|
| [`Planning.md`](Planning.md) | Kiến trúc, quy ước chung, vấn đề công thức chấm (§1.1), chi tiết từng module (§5), lộ trình M0 → M6 (§6) |
| [`Questions.md`](Questions.md) | Câu hỏi còn bỏ ngỏ cần BTC/đội trưởng trả lời: công thức chấm thật, lượt nộp (public vs Docker private), quyền dùng model lớn hơn, GPU, deadline, có được fine-tune không, cấu trúc repo cuối cùng |
| [`train+public_test/README.md`](train+public_test/README.md) | Tài liệu gói dữ liệu chính thức của BTC: cấu trúc thư mục, định dạng `.jsonl`, catalog, `state.json`, cách chạy `zaic_tools`, tạo file nộp |
| `train+public_test/<split>/zaic_tools/README.md` | Mô tả cách BTC chấm: replay `tool_calls` trên `state.json` ban đầu, so state với đáp án, tính F1 trên call |
