# EXECUTION-MVP — Phase 1: dựng harness end-to-end (text → tool calls)

> **Phạm vi:** plan *làm ngay bây giờ*. Mục tiêu: có một agent chạy được từ **transcript dạng chữ** → tool calls → state → metrics, đủ harness (catalog, store, resolver, gate, executor, eval, debug, test).
> **Khác `EXECUTION-PLAN.md` ở đúng 3 điểm:** (1) gọi **API** để call model — MiniMax `M3.1-flash`; (2) **không có STT** (không module ASR, không audio, không n-best); (3) **không quan tâm deploy / nộp bài** (không `infer.py`, không `submission.jsonl`, không Docker, không `public_test`).
> **Quan hệ với `EXECUTION-PLAN.md` (final plan, tới lúc nộp):** file đó là **nguồn chuẩn cho đặc tả từng module** (`§8.x`) và cho metric (`§9`). File này chỉ nói **làm gì, theo thứ tự nào, xong thì gì**, và chỉ điểm khác biệt. Khi hai file khác nhau về cùng một module → **`EXECUTION-PLAN.md` thắng**.

---

## 0. Quy tắc làm việc

1. **Không đoán.** Gặp điều không nói: ghi vào `reports/open_questions.md`, dùng mặc định ở mục 9, làm tiếp.
2. **Đúng thứ tự mốc** (mục 5). Mốc chưa đạt DoD thì không sang mốc sau.
3. **Mỗi mốc kết thúc bằng:** `pytest tests/ -q` xanh + chạy lệnh nghiệm thu của mốc + `git commit -m "MVP<n>: <mô tả>"`.
4. **Không thêm tính năng** ngoài danh sách.
5. **Cấm sửa** `train+public_test/**`; cấm commit `.env`, key, `cache/`, `runs/`, `debug/`.
6. **Hằng số/cờ** nằm trong `config.py`.
7. **Lỗi phải có log** (`debug/<id>.json`, `reports/`), không nuốt lỗi im lặng.
8. Bảng test ghi "bắt buộc pass 100%" ⇒ chưa pass thì không sang bước sau.

---

## 1. Quyết định đã chốt (áp dụng cho MVP)

| Quyết định | Nội dung |
|---|---|
| Metric | Ưu tiên **F1-call**; luôn xuất **cả hai**: F1-call (3 kiểu khớp) + `state_hash`/state từng app. Không được chỉ báo cáo hash |
| LLM | **MiniMax `M3.1-flash` qua API** (OpenAI-compatible). `temperature=0` (greedy) |
| ASR | **Không có.** Transcript lấy thẳng từ `label.audio_text` (chỉ train) |
| Fine-tune | **Không.** Mọi cải thiện qua harness, prompt, few-shot, luật |
| Hard-code | Không hard-code tên app/tool/`x-ref`/collection |
| Môi trường | 1 `ToolEnv`/mẫu, tạo 1 lần trong `eval/run.py`; scope quyết định **trước** mọi `env.call` |
| Split | 1 process = 1 split (`train` trong MVP); không nạp 2 `zaic_tools` trong cùng process |
| Chia tập | `tune` 75% / `heldout` 25% / `dev300` (rút từ `tune`), phân tầng act/ask/refuse. **Không** dùng `heldout` để rút luật hay chọn cờ |
| Song song | `--workers` mặc định 1; nếu bật >1 phải kiểm tra `workers=1` vs `workers=4` cho **giống hệt** |
| Git | `git init`; mỗi mốc một commit |

---

## 2. Ràng buộc cơ học của bài toán (giữ nguyên, không phải chuyện Small Model)

| # | Ràng buộc | Hệ quả trong code |
|---|---|---|
| R1 | Mỗi mẫu đúng một `ToolEnv` | Không tạo lại env để "thử" |
| R2 | **Mọi** `env.call` đều được ghi log và nộp, kể cả call bị từ chối | Gate chặn call rác **trước** khi gọi; đọc thừa làm giảm precision |
| R3 | Ngoài phạm vi ⇒ `tool_calls == []` | Scope chạy trước mọi `env.call` |
| R4 | Cấm đọc/copy/parse file dưới `<split>_environment/` | Dữ liệu app chỉ qua `env.call`; chỉ `scripts/` được replay gold bằng `ToolEnv` |
| R5 | Lệnh ghi không hoàn tác | Planner → Gate → validate → execute |
| R6 | Public test có app/tool lạ | Không hard-code |
| R7 | Mỗi split có `zaic_tools` riêng | 1 process = 1 split (`envloader.py`) |
| R8 | 1 dòng kết quả cho mỗi id | Vòng ghi file bọc `try/except` từng mẫu |

---

## 3. Phạm vi MVP

| | Nội dung |
|---|---|
| **IN** | `config.py`, `envloader.py`, `apiclient.py`, `catalog.py`, `types.py`, `state_store.py`, `lexicon.py`, `vi_norm.py`, `history.py`, `resolver.py`, `scope.py`, `prefetch.py`, `prompt.py`, `retrieval.py`, `policy_text.py`, `llm.py`, `planner.py`, `gate.py`, `executor.py`, `agent.py`, `scripts/*`, `eval/run.py`, `eval/metrics.py`, `tests/*` |
| **IN (giới hạn)** | `eval/run.py` chạy trên **`train`**; transcript = `label.audio_text`; đầu ra = `runs/<tên>/{metrics.json, per_sample.jsonl, errors.json}` + `debug/<id>.json` |
| **OUT** | `asr.py`, `eval/asr_eval.py`, STT nào cả, hotwords · `infer.py`, `submission.jsonl`, validate format nộp bài · Docker/đóng gói · backend local, budget tham số, `M5`/`M7` · `public_test` (không có nhãn, không có STT) · fine-tune |

---

## 4. Môi trường & cấu hình

### 4.1 Setup

```bash
cd <repo_root>
python3.12 -m venv .venv && source .venv/bin/activate
pip install openai numpy pytest httpx
```

`.gitignore`: `.env`, `cache/`, `runs/`, `debug/`, `.venv/`, `__pycache__/`.

### 4.2 Biến môi trường

```
LIFEMATE_DATA_ROOT=/abs/path/to/train+public_test
LIFEMATE_LLM_BASE_URL=<MiniMax base URL, dạng .../v1>
LIFEMATE_LLM_API_KEY=<key>
LIFEMATE_LLM_MODEL=<model id của MiniMax>
LIFEMATE_LLM_EXTRA_BODY={}          # JSON tuỳ chọn (vd {"chat_template_kwargs":{"enable_thinking":false}})
```

> Key **không** commit. `config.py` nạp `.env` bằng bộ nạp tối giản (đọc `KEY=VALUE`, bỏ dòng trống/`#`, **không** ghi đè biến đã có trong môi trường).

### 4.3 `config.py` (MVP — rút từ `EXECUTION-PLAN.md` §4.3, bỏ phần ASR)

```python
import json, os
from pathlib import Path

def _load_env():
    p = Path(__file__).resolve().parent.parent / ".env"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
_load_env()

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = Path(os.getenv("LIFEMATE_DATA_ROOT", str(REPO_ROOT / "train+public_test")))
SPLIT_DEFAULT = "train"

# --- LLM: MiniMax qua API OpenAI-compatible ---
LLM_BASE_URL = os.getenv("LIFEMATE_LLM_BASE_URL", "")
LLM_API_KEY  = os.getenv("LIFEMATE_LLM_API_KEY", "")
LLM_MODEL    = os.getenv("LIFEMATE_LLM_MODEL", "")
LLM_EXTRA_BODY = json.loads(os.getenv("LIFEMATE_LLM_EXTRA_BODY", "{}") or "{}")
LLM_TEMPERATURE = 0
LLM_TIMEOUT, LLM_MAX_RETRIES = 60, 5
LLM_MAX_TOKENS = 512

# --- Nhận diện thực thể ---
ENTITY_MATCH_THRESHOLD = 0.80
ENTITY_AMBIGUITY_GAP = 0.05
ENTITY_UNIQUE_MIN_CONF = 0.90

# --- Scope [MVP3] ---
SCOPE_RATIO_THRESHOLD = 0.5
SCOPE_COVERAGE_THRESHOLD = 0.3
SCOPE_SKIP_LLM_IF_RATIO_GE = 0.9

# --- Prefetch ---
PREFETCH_MODE = "off"            # "off" | "deps" | "all"
PREFETCH_MAX_READS = 2

# --- Gate ---
XREF_MODE = "strict"             # "strict" | "lenient"
DEFER_UNVERIFIED_REF_WRITES = True
MAX_NUDGES = 2
ENABLE_AUTOFILL_REF = True
ENABLE_OVERRIDE = False
ENABLE_AMBIG_ASK = False
ASK_AFTER_PARTIAL = True
ONE_OF_ASK_MODE = "auto"
DROP_DUPLICATE_READS = True
SILENT_RETRY = 1

# --- Executor ---
MAX_TURNS, MAX_WRITES = 6, 8
SAMPLE_DEADLINE_S = 120
REPEAT_MARKERS = ("thêm", "nữa", "lại", "tiếp")

# --- Prompt/few-shot ---
SNAPSHOT_MAX_CHARS = 6000
ENABLE_FEWSHOT = False
FEWSHOT_K = 3
ENABLE_POLICY_RULES = False

# --- Ghi log ---
DEBUG_DIR = "debug"
CACHE_DIR = "cache"
DEBUG_MAX_BYTES = 200_000
```

> Giữ nguyên **tên biến** của final plan để khi chuyển sang `EXECUTION-PLAN.md` không phải sửa lại code.

---

## 5. Lộ trình MVP (mỗi mốc = 1 commit)

### MVP0 — Khảo sát dữ liệu (đo trước khi đoán)

**Làm:** chạy các script ở `EXECUTION-PLAN.md` §8.0 — `inspect_data.py`, `inspect_zaic.py`, `gold_hash.py`, `split.py`, `analyze_train.py`, `mine_policy.py`, `check_ref_alignment.py`. Bỏ phần đọc audio (không có STT); giữ nguyên phần in `history` (không có audio) và phần replay gold bằng `ToolEnv`.

**Sinh ra:**
`reports/inspect.json`, `reports/history_format.md`, `reports/zaic_scoring.md`, `reports/policy.json`, `reports/ask_analysis.json`, `reports/ask_unexplained.json`, `reports/refuse_analysis.json`, `reports/ref_sources.json`, `reports/policy_rules.json`, `reports/open_questions.md`, `cache/gold_hash.json` (1545 mẫu), `tune_ids.txt`, `heldout_ids.txt`, `dev300_ids.txt`.

**Điền `config.py`:** `XREF_MODE` (theo kết quả `check_ref_alignment.py`), hằng số `history.py` (theo `reports/history_format.md`), mọi `[M0]`.

**DoD:** đủ file trên; `gold_hash.json` đủ 1545 mẫu; replay gold khớp `label.final_state`; tạo `ToolEnv` lần hai cho cùng id cho hash giống; `XREF_MODE` đã chốt và ghi lý do.

---

### MVP1 — Harness lõi, chạy end-to-end với transcript vàng

> Đặc tả chi tiết từng module: `EXECUTION-PLAN.md` §8.2–§8.8, §8.10, §8.14–§8.16. Ở MVP **không** có `asr.py`; transcript lấy thẳng từ `item["label"]["audio_text"]`.

| Bước | Viết gì | Test bắt buộc | Xong khi |
|---|---|---|---|
| 1.1 | `envloader.py` (1 split/process), `apiclient.py` (retry backoff, không ném lỗi ra ngoài), `llm.py` (structured tool-calls + fallback text-JSON) | `tests/test_llm.py`: parse tool call structured, parse `<tool_call>` text, JSON hỏng ⇒ `[]` | Gọi MiniMax 1 lần thật, nhận `tool_calls` hoặc text-JSON đúng |
| 1.2 | `types.py` (dataclass ở §7), `catalog.py` (`tools_for`, `all_tools`, `to_llm_tools`, `resolve_tool_name`, `readers_for`) | `tests/test_catalog.py` (6 ca) | xanh |
| 1.3 | `state_store.py` (`StateStore.ingest/ids_for/has_called/entity_list`), `lexicon.py` (`trim_snapshot`) | `tests/test_state_store.py` (5 ca) | xanh |
| 1.4 | `vi_norm.py` — **phần văn bản**: `normalize`, `strip_tone`, `strip_accents`, `phonetic_key`, `token_sim` (bậc), `STOPWORDS_VI` | `tests/test_vi_norm.py::test_text` (4 ca, **pass 100%**) | xanh |
| 1.5 | `resolver.py` — **phần thực thể**: `match_entities`, `build_hints` (chỉ entity), `format_hints` | `tests/test_resolver.py` (6 ca) | xanh |
| 1.6 | `history.py` (`history_turns`, `format_history` — dùng `text` có sẵn, **không** có audio) | — | in đúng lịch sử của 3 mẫu (đối chiếu `reports/history_format.md`) |
| 1.7 | `prompt.py` (system prompt 9 quy tắc + user message), `planner.py` | — | prompt dựng được, đúng thứ tự mục |
| 1.8 | `gate.py` — 8 bước + `sanitize_ask`, `coerce_args`, `fix_refs`, `autofill_refs`, `missing_params` | `tests/test_gate.py` (13 ca) | xanh |
| 1.9 | `executor.py` (`safe_call`, `run_plan` — vòng B2, `SILENT_RETRY`, `needs_read`, chống lặp), `agent.py` (scope stub `return True`) | `tests/test_executor.py` (6 ca) | xanh |
| 1.10 | `prefetch.py` (mode `off` mặc định; `deps`/`all` để ablation) | — | — |
| 1.11 | `eval/run.py` + `eval/metrics.py` | `tests/test_metrics.py` (4 ca) | xanh |

**Lệnh nghiệm thu MVP1:**
```bash
pytest tests/ -q
python eval/run.py --split train --ids dev300_ids.txt --out runs/mvp1
```

**DoD:** `runs/mvp1/metrics.json` có **F1-call** (3 kiểu khớp) **và** hash-match, theo nhóm `act/ask/refuse`; `errors.json` có đếm taxonomy; `per_sample.jsonl` đủ 300 mẫu; `debug/<id>.json` có `hyps`/`scope`/`gate_notes`/`executed`; không có mẫu nào làm sập lượt chạy.

---

### MVP2 — Số/giờ + resolver đầy đủ

| Bước | Viết gì | Xong khi |
|---|---|---|
| 2.1 | `vi_norm.py` — **phần số**: `parse_numbers` (đường chữ + regex đơn vị + chuỗi chữ số rời + loại trừ ngữ cảnh giờ) | Bảng test 8.11 (24 dòng) **pass 100%** |
| 2.2 | `vi_norm.py` — **phần giờ/ngày**: `parse_times` (khoảng thời gian, ngày, giờ trong ngày, từ chỉ buổi, kết hợp) | Bảng test 8.11 **pass 100%** |
| 2.3 | `resolver.build_hints` đủ entity/number/time + `alt_values` từ ứng viên khác | `tests/test_resolver.py` bổ sung ca số/giờ xanh |
| 2.4 | `gate` + `executor` dùng hints: `ENABLE_OVERRIDE` (ghi đè số/giờ khi đúng 1 hint `conf ≥ 0.9`) | ablation bật/tắt cho kết quả |

**Lệnh nghiệm thu:**
```bash
pytest tests/ -q
python eval/run.py --split train --ids dev300_ids.txt --out runs/mvp2
```

**DoD:** bảng test 8.11 pass 100%; `runs/mvp2/metrics.json` có F1-call **không thấp hơn** MVP1 (báo cáo cả hai, kể cả khi giảm).

---

### MVP3 — Scope thật + few-shot + quy tắc chính sách

| Bước | Viết gì | Xong khi |
|---|---|---|
| 3.1 | `scope.py`: BM25 trên toàn catalog, `ratio = best_installed/best_all`, `coverage`, quyết định theo §8.13; bỏ `scope.py` stub trong `agent.py` | `tests/test_scope.py` (4 ca) xanh |
| 3.2 | `eval/run.py --tune-scope`: quét lưới ngưỡng trên `tune_ids` | `reports/scope_tune.json`; chọn cặp tối đa hoá F1 lớp `refuse` với recall `act+ask` ≥ 99% |
| 3.3 | `retrieval.py` (BM25 few-shot, ID che) + `policy_text.py` (quy tắc từ `reports/policy_rules.json`) | ví dụ trong prompt đúng định dạng §8.9 |
| 3.4 | `agent.py`: nối `fewshot_index`, `policy_text` vào prompt | — |

**Lệnh nghiệm thu:**
```bash
pytest tests/ -q
python eval/run.py --split train --ids tune_ids.txt --tune-scope --out runs/mvp3_scope
python eval/run.py --split train --ids heldout_ids.txt --out runs/mvp3
```

**DoD:** mọi mẫu `refuse` của `heldout` mà scope đúng ⇒ `tool_calls == []`; `reports/scope_tune.json` có; so sánh `MVP2` vs `MVP3` ghi trong `reports/`.

---

### MVP4 — Ablation & chốt cấu hình

Bảng ablation (giống `EXECUTION-PLAN.md` §10, bỏ dòng hotwords ASR):

| Thí nghiệm | Lệnh |
|---|---|
| Cơ sở | không `--set` |
| Prefetch | `--set PREFETCH_MODE=deps`, `--set PREFETCH_MODE=all` |
| Autofill ID | `--set ENABLE_AUTOFILL_REF=False` |
| Hoãn write chưa xác minh | `--set DEFER_UNVERIFIED_REF_WRITES=False` |
| XREF | `--set XREF_MODE=lenient` |
| Few-shot | `--set ENABLE_FEWSHOT=True` |
| Chính sách | `--set ENABLE_POLICY_RULES=True` |
| Ghi đè số/giờ | `--set ENABLE_OVERRIDE=True` |
| Hỏi khi mơ hồ | `--set ENABLE_AMBIG_ASK=True` |
| Thứ tự `ask` | `--set ASK_AFTER_PARTIAL=False` |

**Quy tắc giữ cờ:** giữ khi F1-call (fuzzy-aware) tăng ≥ 0.5 điểm phần trăm **và** hash-match không giảm trên `dev300`; xác nhận 1 lần trên `heldout`. Ghi `reports/ablation.md`.

**DoD:** `reports/ablation.md` đầy đủ; `config.py` chốt cờ; `git log` có 5 commit (MVP0→MVP4).

---

## 6. Bảng mapping MVP ↔ final plan

| Module | Đặc tả chi tiết ở | Khác biệt ở MVP |
|---|---|---|
| `envloader.py`, `apiclient.py` | §8.2, §8.3 | không đổi |
| `catalog.py` | §8.4 | không đổi |
| `vi_norm.py` | §8.5, §8.11 | chỉ phần **văn bản** ở MVP1; số/giờ ở MVP2; **không** có phần ASR |
| `state_store.py`, `lexicon.py` | §8.6 | không đổi |
| `history.py` | §8.7 | dùng `text` có sẵn; **không** có audio |
| `resolver.py` | §8.8 | MVP1 chỉ entity; MVP2 đủ số/giờ |
| `prompt.py`, `retrieval.py`, `policy_text.py` | §8.9 | không đổi |
| `llm.py`, `planner.py` | §8.10 | MiniMax API; nhánh structured + text-JSON |
| `scope.py` | §8.13 | MVP1 stub; MVP3 thật |
| `prefetch.py` | §8.14 | không đổi |
| `gate.py` | §8.15 | không đổi |
| `executor.py`, `agent.py` | §8.16 | `agent.py` nhận transcript thay vì gọi ASR; không `infer.py` |
| `eval/run.py`, `eval/metrics.py` | §9.3 | nguồn transcript = `label.audio_text`; không `--asr`; không xuất `submission.jsonl` |
| `asr.py`, `eval/asr_eval.py` | §8.12 | **KHÔNG làm ở MVP** |
| `infer.py`, đóng gói | §8.16, §8.17 | **KHÔNG làm ở MVP** |

---

## 7. Metric (giữ nguyên `EXECUTION-PLAN.md` §9)

- **F1-call (chính)**: multiset call dự đoán vs gold.
  - `strict`: cùng `name` **và** `arguments` bằng nhau (so sâu, bỏ thứ tự khoá; `500000` ≡ `500000.0`).
  - `fuzzy-aware`: cùng `name`; tham số `x-match: fuzzy` so token-F1 ≥ 0.8 (sau `normalize`), tham số khác phải bằng.
  - `soft`: chỉ cùng `name`.
  - `sys.ask_missing_info`: khớp khi `tool_name` bằng và `set(params)` bằng.
  - `precision = TP/|pred|`, `recall = TP/|gold|`, `F1 = 2PR/(P+R)`; cả hai bên rỗng ⇒ F1 = 1.0. **Macro-average theo mẫu.**
- **Hash match**: `env.get_state_hash() == gold_hash`; thêm khớp state từng app.
- **Ask accuracy**: % mẫu ask có `tool_name` đúng **và** `set(params)` đúng.
- Báo cáo theo nhóm `act/ask/refuse`, theo app, và theo **số lệnh đọc thừa**.
- **Taxonomy lỗi** (1 nhãn/mẫu, theo thứ tự): `exception` → `scope_false_refuse` → `scope_missed_refuse` → `ask_vs_act` → `act_vs_ask` → `gate_dropped_valid` → `wrong_tool` → `wrong_id` → `wrong_arg_entity` → `wrong_arg_number` → `wrong_arg_time` → `wrong_arg_other`.

> Lưu ý: công thức F1 thật của BTC **không có trong gói dữ liệu** (`EXECUTION-PLAN.md` §8.0.2 sẽ xác nhận). Ba kiểu khớp ở trên là **định nghĩa của ta** để đo; ưu tiên `fuzzy-aware`.

---

## 8. KHÔNG làm ở MVP

- Không sửa `train+public_test/**`.
- Không đọc `state.json` trong code agent (chỉ `scripts/` replay gold bằng `ToolEnv`).
- Không hard-code tên app/tool/`x-ref`/collection.
- Không viết module ASR/STT, không đọc file audio.
- Không viết `infer.py`, không sinh `submission.jsonl`, không làm Docker, không chạy `public_test`.
- Không cài `torch`/`transformers`, không tải model về máy.
- Không fine-tune.
- Không dùng `heldout` để rút luật/chọn cờ/few-shot.
- Không commit key, `.env`, `cache/`, `runs/`, `debug/`.
- Không thêm tính năng ngoài danh sách (multi-agent, memory, web search...).
- Không tối ưu theo số điểm riêng của MiniMax (xem mục 9.3).

---

## 9. Việc còn mở & mặc định

| # | Câu hỏi | Mặc định |
|---|---|---|
| O1 | **MiniMax**: base URL, model id chính xác, tên biến key | Chưa điền → dùng `LIFEMATE_LLM_*` từ env; xác nhận ở bước 1.1 |
| O2 | MiniMax có hỗ trợ OpenAI-style `tools`/`tool_choice`? | Cài **cả hai** nhánh (structured trước, text-JSON sau); nhánh nào chạy được thì dùng |
| O3 | Công thức F1-call của BTC | Đọc `zaic_tools` (đã biết: không có code chấm trong gói) ⇒ dùng mục 7 |
| O4 | Định dạng `history` (vai trò, lượt trợ lý) | Đọc `reports/history_format.md` (MVP0) |
| O5 | 3 mẫu ask chưa giải thích (`robot_vacuum.start(rooms)`, `tv.control(volume)`×2) | Không luật riêng; để LLM/gate xử lý theo `required`/`one_of` |
| O6 | Rate limit MiniMax | `--workers 1`; nếu bật >1, kiểm tra `workers=1` vs `4` giống hệt |
| O7 | Có cần `LIFEMATE_LLM_EXTRA_BODY` cho MiniMax không? | Mặc định `{}` |

---

## 10. Cảnh báo khi đọc số điểm MVP

MiniMax `M3.1-flash` **mạnh hơn nhiều** so với Qwen3-4B (model sẽ dùng lúc nộp theo `EXECUTION-PLAN.md`). Số điểm đo ở MVP **lạc quan hơn thực tế**, và lỗi sẽ tập trung ở chỗ khác (ít lỗi bịa ID, ít lỗi thiếu tham số; nhiều lỗi ở scope/định dạng/ID chính xác hơn).

⇒ **Đừng tối ưu theo số điểm của MiniMax.** Giữ nguyên knob của final plan, đừng thêm luật riêng cho MiniMax, và đừng suy ra "đã đủ tốt" từ số điểm MVP. Số đo lúc nộp sẽ dùng backend local theo `EXECUTION-PLAN.md` §8.17.
