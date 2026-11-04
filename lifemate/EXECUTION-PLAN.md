# KẾ HOẠCH THỰC THI — LifeMate (ZAC 2026) — Bản v2

> **Đây là nguồn chuẩn duy nhất cho mọi quy tắc hiện thực.** Agent đọc file này rồi code; không cần file nào khác.
> Ngày: 2026-11-04. Bản này gộp: kiến trúc + quyết định đã chốt + dữ liệu đã verify + đặc tả từng module + tiêu chí nghiệm thu.
> Khác bản v1: sửa lỗi gate (ID động), thêm `StateStore`, scope chuẩn hóa, prefetch theo phụ thuộc, tách backend LLM/ASR (api ↔ local), chấm điểm thực thể theo bậc, few-shot + chính sách vào lộ trình sớm, thêm các bước khảo sát bắt buộc ở M0.

---

## 0. Quy tắc làm việc cho agent (đọc trước)

1. **Không đoán.** Gặp điều plan không nói: ghi câu hỏi vào `reports/open_questions.md`, dùng giá trị mặc định ở mục 14, rồi làm tiếp.
2. **Làm đúng thứ tự mốc** (mục 11). Mốc chưa đạt tiêu chí nghiệm thu thì không sang mốc sau.
3. **Mỗi mốc kết thúc bằng:** `pytest tests/ -q` xanh + chạy đúng lệnh nghiệm thu của mốc + `git commit -m "<mốc>: <mô tả>"`.
4. **Không thêm tính năng** ngoài danh sách. Không refactor ngoài phạm vi mốc.
5. **Cấm sửa** `train+public_test/**`, cấm commit key/`.env`/`cache/`/`runs/`/`debug/`/`models/`/`.venv/`.
6. **Mọi hằng số/cờ** nằm trong `config.py`; không rải số ma thuật trong code.
7. **Mỗi lỗi bắt được phải có log** (`debug/<id>.json` hoặc `reports/`), không nuốt lỗi im lặng.
8. Khi một bảng test trong plan ghi "bắt buộc pass 100%", chưa pass thì không sang bước kế.

---

## 1. Mục tiêu và cách chấm

**Input một mẫu:** audio tiếng Việt (WAV 16 kHz mono) + `context` (thời gian, múi giờ, vị trí, hồ sơ, app đã cài) + `history`.
**Output:** một dòng `submission.jsonl`: `{"id", "tool_calls", "state_hash"}`.

**BTC chấm:**
1. `state_hash` (state cuối sau khi replay `tool_calls`).
2. **F1 trên call**: `zaic_tools/README.md` nói replay `tool_calls` rồi so với đáp án và tính F1 trên call. Công thức chính xác chưa biết ⇒ **M0 bắt buộc đọc mã `zaic_tools`** (mục 8.0.2).

⇒ **Chỉ số ưu tiên khi tối ưu: F1-call.** Hash là chỉ số phụ. Mọi lời gọi (kể cả đọc thừa, kể cả lời gọi lỗi) đều nằm trong `tool_calls` nên làm giảm precision.

---

## 2. Ràng buộc cứng

| # | Ràng buộc | Hệ quả bắt buộc trong code |
|---|---|---|
| R0 | **Luật mô hình/gọi API chưa xác nhận** (đề yêu cầu mô hình < 6B và bài nộp là Docker đóng băng trước private_test) | Mọi chỗ gọi LLM/ASR đi qua lớp backend có thể đổi giữa `api` và `local` chỉ bằng cấu hình. API chỉ dùng để dev/đo trần. **Bài nộp cuối phải chạy được bằng backend local** (mục 8.14, M5) |
| R1 | Mỗi mẫu **đúng một** `ToolEnv`, tạo trong `infer()` | Truyền `env` xuống mọi hàm; không bao giờ tạo lại `ToolEnv` để "thử" |
| R2 | **Mọi** `env.call` đều được ghi log và nộp, kể cả call bị từ chối (`zaic_tools/executor.py` ghi log trước khi validate) | Gate chặn call rác trước khi gọi. Đọc thừa và gọi lỗi đều trừ precision |
| R3 | Ngoài phạm vi ⇒ `tool_calls == []` | Quyết định scope **trước** mọi `env.call`, kể cả đọc |
| R4 | Cấm đọc/copy/parse file dưới `<split>_environment/` | Dữ liệu app chỉ qua `env.call`. Chỉ `scripts/` phân tích được phép replay gold bằng `ToolEnv` |
| R5 | Lệnh ghi không hoàn tác | Planner → gate → validate → execute. Không "gửi thử rồi sửa" |
| R6 | Public test có **11 app và 34 tool chưa từng có ở train** | Không hard-code tên app/tool/`x-ref`. Mọi logic đi qua catalog |
| R7 | Mỗi split có `zaic_tools` riêng (phiên bản khác nhau) | **Mỗi process chỉ nạp một split** (mục 8.2). Chạy train và public_test ở hai process khác nhau |
| R8 | Một dòng nộp cho mỗi id; JSON hợp lệ; `state_hash` không rỗng | Vòng ghi file bọc `try/except` từng mẫu |
| R9 | Không fine-tune | Mọi cải thiện qua harness, prompt, few-shot, luật |

---

## 3. Phạm vi các mốc

| Mốc | IN | OUT |
|---|---|---|
| **M0** | Mọi script trong `scripts/` (mục 8.0); `reports/*`; `cache/gold_hash.json`; các file split ids; điền các giá trị `[M0]` trong `config.py` | Chưa viết agent |
| **M1** | `config`, `envloader`, `apiclient`, `catalog`, `vi_norm` (phần văn bản), `lexicon`, `state_store`, `resolver` (phần thực thể), `history`, `llm`, `prompt`, `planner`, `gate`, `executor`, `prefetch`, `agent` (scope là stub trả `True`), `infer`, `eval/run.py`, `eval/metrics.py`, tests tương ứng. Chạy `--asr gold` | Chưa ASR thật, chưa parser số/giờ, chưa scope thật |
| **M2** | `vi_norm` (số + giờ) và test; `asr.py` (gold/api/local); `eval/asr_eval.py`; chốt ASR | Chưa bật cờ nào |
| **M3** | `scope.py` thật + tune; `resolver.build_hints` đủ số/giờ; nối ASR thật; `retrieval.py` + `policy_text.py` (few-shot + quy tắc chính sách) | — |
| **M4** | Ablation từng cờ theo mục 10 | Không tự động hóa ngoài `eval/run.py` |
| **M5** | Backend local (R0): chạy Qwen3-4B cục bộ + ASR cục bộ; đo lại; che/đổi tên tool; đo thời gian | — |
| **M6** | Chạy `public_test`, sinh `submission.jsonl`, validate | — |
| **M7** | Đóng gói theo mục 8.17 | — |

---

## 4. Môi trường và cấu hình

### 4.1 Setup

```bash
cd <repo_root>
python3.12 -m venv .venv && source .venv/bin/activate
pip install openai numpy soundfile pytest
# chỉ khi dùng ASR/LLM cục bộ (M2 local, M5):
pip install torch transformers
```

`.gitignore`: `.env`, `models/`, `cache/`, `runs/`, `debug/`, `.venv/`, `__pycache__/`, `submission.jsonl`.

### 4.2 Biến môi trường (đặt trong `.env`, không commit)

```
LIFEMATE_DATA_ROOT=/abs/path/to/train+public_test
LIFEMATE_LLM_BASE_URL=...        # endpoint OpenAI-compatible (API hoặc server cục bộ)
LIFEMATE_LLM_API_KEY=...
LIFEMATE_LLM_MODEL=...           # model id hỗ trợ tool-calling
LIFEMATE_LLM_EXTRA_BODY={}       # JSON; với Qwen3 cục bộ: {"chat_template_kwargs":{"enable_thinking":false}}
LIFEMATE_STT_BASE_URL=...        # chỉ khi ASR_MODE=api
LIFEMATE_STT_API_KEY=...
LIFEMATE_STT_MODEL=...
```

`config.py` tự nạp `.env` bằng bộ nạp tối giản (không thêm thư viện): đọc từng dòng `KEY=VALUE`, bỏ dòng trống/`#`, không ghi đè biến đã có trong môi trường.

### 4.3 `config.py` (copy nguyên văn, điền `[M0]` sau khi khảo sát)

```python
# config.py
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
SPLIT_DEFAULT = "public_test"

# --- LLM (OpenAI-compatible; api hoặc server cục bộ chỉ khác base_url/model) ---
LLM_BASE_URL = os.getenv("LIFEMATE_LLM_BASE_URL", "")
LLM_API_KEY  = os.getenv("LIFEMATE_LLM_API_KEY", "EMPTY")
LLM_MODEL    = os.getenv("LIFEMATE_LLM_MODEL", "")
LLM_EXTRA_BODY = json.loads(os.getenv("LIFEMATE_LLM_EXTRA_BODY", "{}") or "{}")
LLM_TEMPERATURE = 0
LLM_TIMEOUT, LLM_MAX_RETRIES = 60, 5
LLM_MAX_TOKENS = 512

# --- ASR ---
ASR_MODE = "api"                    # "gold" | "api" | "local"
STT_BASE_URL = os.getenv("LIFEMATE_STT_BASE_URL", "")
STT_API_KEY  = os.getenv("LIFEMATE_STT_API_KEY", "")
STT_MODEL    = os.getenv("LIFEMATE_STT_MODEL", "")
ASR_LOCAL_MODEL = "vinai/PhoWhisper-medium"    # [M2] chọn lại theo số đo
ASR_BEAMS, ASR_NBEST = 5, 3
ASR_SILENCE_TRIM = True

# --- Nhận diện thực thể ---
ENTITY_MATCH_THRESHOLD = 0.80
ENTITY_AMBIGUITY_GAP = 0.05
ENTITY_UNIQUE_MIN_CONF = 0.90       # dùng cho autofill/ghi đè

# --- Scope [M3] ---
SCOPE_RATIO_THRESHOLD = 0.5         # tune
SCOPE_COVERAGE_THRESHOLD = 0.3      # tune
SCOPE_SKIP_LLM_IF_RATIO_GE = 0.9    # in-scope chắc chắn, bỏ qua LLM

# --- Prefetch ---
PREFETCH_MODE = "off"               # "off" | "deps" | "all"   (luôn chạy SAU scope)
PREFETCH_MAX_READS = 2              # chỉ dùng khi mode != "off"

# --- Gate ---
XREF_MODE = "strict"                # [M0] "strict" | "lenient" (lenient: không xóa ID lạ, chỉ sửa khi có ứng viên duy nhất)
DEFER_UNVERIFIED_REF_WRITES = True
MAX_NUDGES = 2
ENABLE_AUTOFILL_REF = True
ENABLE_OVERRIDE = False             # [M4] ghi đè số/giờ bằng parser
ENABLE_AMBIG_ASK = False            # [M4] gold không có ask do mơ hồ ⇒ mặc định tắt
ASK_AFTER_PARTIAL = True            # [M0] xác nhận: ask luôn ở cuối chuỗi (đã verify)
ONE_OF_ASK_MODE = "auto"            # "auto" | "first_group"
DROP_DUPLICATE_READS = True
SILENT_RETRY = 1

# --- Executor ---
MAX_TURNS, MAX_WRITES = 6, 8
SAMPLE_DEADLINE_S = 120
REPEAT_MARKERS = ("thêm", "nữa", "lại", "tiếp")

# --- Prompt/few-shot [M3/M4] ---
SNAPSHOT_MAX_CHARS = 6000
ENABLE_FEWSHOT = False
FEWSHOT_K = 3
ENABLE_POLICY_RULES = False
ENABLE_HOTWORD_REASR = False
ENABLE_LLM_ALT_HYPS = False         # LLM không có audio ⇒ chỉ là phỏng đoán; mặc định tắt

# --- Ghi log ---
DEBUG_DIR = "debug"
CACHE_DIR = "cache"
DEBUG_MAX_BYTES = 200_000
```

---

## 5. Dữ liệu đã verify (dùng luôn, không khảo sát lại)

| Sự kiện | Số liệu |
|---|---|
| Train | 1545 mẫu = **act 1217 / ask 217 / refuse 111**; có `history`: 966 mẫu |
| Public test | 634 mẫu; có `history`: 419; **không** có `audio_text`, không có `label` |
| Cấu trúc `installed_apps` | `{app: {"tools": [tên tool, ...]}}` ở cả hai split |
| `env.allowed` | khớp `context.installed_apps` (kiểm 240 mẫu) |
| `x-one-of` | chỉ ở mức `parameters`, dạng list-of-list, mỗi nhóm đúng 1 tham số |
| `x-ref` | ở mức property, dạng `app.collection` (vd `contacts.contacts`) ⇒ `coll = x_ref.split(".")[-1]` |
| `x-match: fuzzy` | ở property (`content`, `title`, `note`, `label`, `query`, …); catalog nói chấm token-F1 |
| Replay gold | `label.tool_calls` ⇒ `env.get_state()` khớp `label.final_state` 60/60 |
| `ToolEnv` mới | `get_state_hash()` giống hệt giữa các lần tạo ⇒ không rò trạng thái |
| Read tool prefetch được | TB 9,7 mỗi mẫu (max 21); **gold chỉ có 1,03 read call/mẫu** |
| Gold read call có args | `contacts.search {"query":"Lan"}` 35 lần, `{"query":"Minh"}` 33 lần, `gold_price.get_price {"type":"sjc"}` 23 lần… |
| Mẫu ask (217) | 60 mẫu chỉ có 1 call; 157 mẫu có call khác **trước** ask; 79 mẫu có **write đã thực hiện** rồi mới hỏi; **`ask` luôn ở cuối chuỗi** |
| `ask.params` | 139/170 mẫu có `required` khác rỗng ⇒ `params` = tập `required` còn thiếu; **31 mẫu** hỏi tham số thuộc nhóm `x-one-of` (đúng **1** tham số). **47 mẫu ask còn lại chưa được giải thích** ⇒ M0 phải phân loại (mục 8.0.5) |
| Mẫu act (1217) | 124 mẫu chỉ có read (state không đổi ⇒ chỉ có giá trị khi tính F1-call); 1093 mẫu đổi state; TB 2,5 call/mẫu |
| ID do app sinh | dạng `alm_02`, `evt_01`… tất định theo thứ tự collection ⇒ gọi đúng tool/args là tự khớp state |
| `App.contact_ref` | app tự suy `contact_id ↔ phone_number` từ app `contacts` nếu đã cài |
| Audio | 16 kHz mono, 5036 file, TB 4,9 s, max 12,8 s |
| `canon()` bỏ khỏi hash | app `exchange_rate, fuel_price, gold_price, lottery, weather`; field text tự do `address, body, content, dropoff, expression, label, location, name, note, pickup, subject, title` ⇒ sai text không lộ trong hash nhưng **lộ trong F1-call** |
| `sys.ask_missing_info` | luôn nằm trong `allowed`; `kind="meta"`; không đổi state |

---

## 6. Kiến trúc và lý do

| Ràng buộc | Thiết kế | Module |
|---|---|---|
| R3: ngoài phạm vi phải `[]`, không để lại log đọc | Scope chạy trước mọi `env.call` | `scope.py` |
| R4: cấm đọc `state.json`; ID chỉ có qua tool | `StateStore` gom mọi kết quả `env.call` thành snapshot/entities/ids **cập nhật sau mỗi lệnh** | `state_store.py`, `lexicon.py` |
| Hash/F1 nhạy với từng tên, số, giờ | Resolver: ứng viên thực thể theo bậc điểm + parser số/giờ; chỉ là **gợi ý**, ghi đè chỉ khi tự tin cao | `resolver.py`, `vi_norm.py` |
| R5: ghi không hoàn tác | Planner → Gate → Executor; lệnh ghi có `x-ref` chưa xác minh bị **hoãn** và planner được nhắc đọc trước | `gate.py`, `executor.py` |
| Mô hình nhỏ bịa ID, thiếu tham số | Mọi kiểm tra tính hợp lệ lấy từ catalog (`required`, `enum`, `x-ref`, `x-one-of`) và dữ liệu đã đọc; không tin lời tự khai của mô hình | `gate.py` |
| R6: tool/app lạ | Không hard-code; liên kết `x-ref` ↔ tool đọc dựa vào `returns`/tên tool | `catalog.py`, `prefetch.py` |
| R2/F1: đọc thừa trừ điểm | Prefetch mặc định tắt; chỉ đọc khi cần | `prefetch.py`, `gate.py` |
| R0: luật chưa chắc | LLM/ASR qua backend đổi được api ↔ local | `llm.py`, `asr.py` |

### Luồng một mẫu

```
item
 ├─ history → danh sách lượt (user/assistant)                     [history.py]
 ├─ ASR audio hiện tại + audio các lượt user trong history          [asr.py]
 ├─ SCOPE: ngoài phạm vi? → DỪNG, tool_calls=[]                     [scope.py]  ← trước mọi env.call
 ├─ PREFETCH (off | deps | all, ≤ PREFETCH_MAX_READS)               [prefetch.py]
 ├─ StateStore.ingest(kết quả prefetch)                             [state_store.py]
 ├─ HINTS: thực thể/số/giờ từ transcript + store                    [resolver.py, vi_norm.py]
 ├─ PROMPT (+ few-shot + quy tắc chính sách nếu bật)                [prompt.py, retrieval.py, policy_text.py]
 ├─ vòng B2 (≤ MAX_TURNS):
 │    PLANNER (LLM tool-calling) → GATE → EXECUTOR (validate→call)
 │    mỗi kết quả → StateStore.ingest → hints/ids cập nhật
 └─► env.get_tool_calls(), env.get_state_hash()
```

Lỗi ở bất kỳ bước nào ⇒ `try/except` trong `infer()` ⇒ mẫu đó nộp những gì đã được ghi log, không làm sập lượt chạy.

---

## 7. Hợp đồng dữ liệu (dataclass dùng chung, đặt trong `lifemate/types.py`)

```python
from dataclasses import dataclass, field
from typing import Any

@dataclass
class Tool:
    name: str; app: str; kind: str; description: str
    app_name_vi: str; app_description: str; returns: str
    parameters: dict
    required: list[str]
    props: dict[str, dict]
    one_of: list[list[str]]          # list nhóm, mỗi nhóm list tên tham số

@dataclass
class Hyp:    text: str; score: float
@dataclass
class Hint:   kind: str; span: str; value: Any; conf: float; extra: dict = field(default_factory=dict)
              # kind: "entity" | "number" | "time" | "digits"
@dataclass
class Entity: id: str; collection: str; fields: dict; names: list; source_tool: str
@dataclass
class Call:   name: str; args: dict; call_id: str = ""       # call_id: id do LLM API cấp (nếu có)
@dataclass
class Ask:    tool_name: str; params: list

@dataclass
class GateResult:
    calls: list                      # được phép thực thi, theo thứ tự
    ask: "Ask | None"
    refuse: bool
    notes: list
    needs_read: list                 # [(tool_name, param, collection)] cho các call bị hoãn
    deferred: list                   # call bị hoãn (không thực thi ở lượt này)

class Deadline:
    def __init__(self, seconds): ...
    def expired(self) -> bool: ...
```

---

## 8. Đặc tả module

### 8.0 Các script khảo sát ở M0 (làm đầu tiên)

Mục đích: các script này tạo ra dữ kiện mà các mốc sau cần. Mỗi script lưu kết quả vào `reports/` và in tóm tắt ra màn hình. Mọi script thêm `sys.path.insert(0, repo_root)` và **chỉ nạp split `train`** (R7).

#### 8.0.1 `scripts/inspect_data.py` → `reports/inspect.json`, `reports/history_format.md`
1. Khóa của một record `train.jsonl`; cấu trúc `installed_apps`; cấu trúc `history`.
2. In **nguyên văn** (JSON, `indent=2`, cắt 2500 ký tự) `history` của 3 mẫu có history, kèm `audio_text` (nếu có). Từ đó ghi vào `reports/history_format.md`: tên khóa của mỗi lượt (vai trò: `role`/`speaker`…; nội dung: `text`/`content`; đường dẫn audio: `audio`/…), lượt trợ lý có chứa gì (câu hỏi `ask_missing_info`? lời đáp?), thứ tự.
3. Với 5 mẫu: tạo `ToolEnv`, gọi từng tool `kind=read` không có tham số bắt buộc, in kết quả (cắt 1500 ký tự). Ghi lại **khóa chứa list** của từng tool (để kiểm tra `collection`).
4. Vị trí/dạng `x-one-of`, `x-ref`, `x-match` trong catalog.
5. Tool `sys.ask_missing_info` trong catalog (có/không, schema).

#### 8.0.2 `scripts/inspect_zaic.py` → `reports/zaic_scoring.md`
- Đọc `train+public_test/<split>/zaic_tools/README.md` và liệt kê các module trong `zaic_tools/`.
- Tìm trong mã nguồn các hàm liên quan chấm điểm/so sánh call/replay/`--validate`/`canon` (tìm các từ khóa: `f1`, `score`, `compare`, `match`, `canon`, `validate`, `fuzzy`, `token`).
- Ghi vào `reports/zaic_scoring.md`: (a) công thức F1-call nếu có trong mã (so khớp tên + args như thế nào, thứ tự có quan trọng không, tham số fuzzy so thế nào, `sys.ask_missing_info` so thế nào); (b) lệnh CLI chính xác để validate submission; (c) hàm có thể import để dùng lại trong `eval/metrics.py`.
- Nếu **không tìm thấy** công thức: ghi "không có trong mã" và dùng định nghĩa mặc định mục 9.1.

#### 8.0.3 `scripts/gold_hash.py` → `cache/gold_hash.json`
Với mỗi mẫu train: tạo `ToolEnv` mới, replay `label.tool_calls` (bỏ `sys.ask_missing_info`), lưu `state_hash`. Sau đó tạo `ToolEnv` thứ hai cho 60 mẫu ngẫu nhiên, so hash khởi tạo. Nếu hash lệch hoặc replay không khớp `label.final_state` ở bất kỳ mẫu nào, dừng và báo cáo.

#### 8.0.4 `scripts/split.py` → `tune_ids.txt`, `heldout_ids.txt`, `dev300_ids.txt`
Seed 13. `tune` 75%, `heldout` 25%, phân tầng theo nhóm `act/ask/refuse`. `dev300_ids.txt` là 300 mẫu rút từ `tune`, phân tầng theo nhóm (dùng cho ablation nhanh, mục 10). **Không** dùng `heldout` để rút luật, chọn few-shot, hay quyết định cờ.

#### 8.0.5 `scripts/analyze_train.py` → `reports/policy.json`, `reports/ask_analysis.json`, `reports/refuse_analysis.json`, `reports/ref_sources.json`
1. Phân loại mỗi mẫu: `refuse` (gold `[]`), `ask` (có `sys.ask_missing_info`), `act` (còn lại).
2. **Ask:** cho từng mẫu ask: `tool_name`, `params`, tool/args phía trước, `required` và `one_of` của tool đó, `params` có bằng "tập `required` còn thiếu" không. **Với 47 mẫu ask chưa giải thích: in toàn bộ (transcript, gold calls, tool schema) vào `reports/ask_unexplained.json`**, rồi tóm tắt các kiểu nguyên nhân vào `reports/open_questions.md`.
3. **Refuse (111 mẫu):** cho mỗi mẫu in transcript, `installed_apps`, app khớp nhất trong **toàn catalog** theo BM25 (hàm tạm trong script), app đó có được cài không. Tóm tắt: bao nhiêu mẫu là "yêu cầu khớp một app không được cài", bao nhiêu là "không khớp app nào".
4. **Act:** số lệnh ghi mỗi mẫu; tỉ lệ có read trong gold; tỉ lệ nhiều write.
5. **Giả định "đọc không đổi hash":** 30 mẫu act có read trong gold, replay có/không lệnh đọc, so hash.
6. **`reports/ref_sources.json`:** với mỗi tham số `x-ref` của tool ghi trong gold, tìm tool đọc nào (trong cùng mẫu) đã chạy trước đó và có kết quả chứa ID đó. Lưu `{collection: {read_tool: count}}`. Dùng cho `prefetch` mode `deps` và `readers_for`.
7. **`scripts/check_ref_alignment.py`:** replay gold, với mọi `x-ref` trong lệnh ghi gold kiểm tra giá trị có nằm trong `StateStore.ids[coll]` sau khi nạp `label.tool_results` trước đó. In tỉ lệ khớp. **Nếu < 95% ⇒ đặt `XREF_MODE="lenient"`** và ghi nguyên nhân (tên khóa khác tên collection?) vào `open_questions.md`.
8. Từ `audio_text` + gold args: trích bộ thực thể phục vụ `eval/asr_eval.py` (mục 8.12) lưu `cache/entities_train.json`.

#### 8.0.6 `scripts/mine_policy.py` → `reports/policy_rules.json`
Với mỗi `(tool, tham số)` xuất hiện trong lệnh ghi gold, tính nguồn của giá trị: `profile.<khóa>` (trùng một giá trị trong `user_profile`), `current_location`, `current_time`, `transcript` (giá trị xuất hiện trong `audio_text`), `read_result`, `other`. Lưu `{tool: {param: {source: count}}}`. Cặp `(tool, param)` có ≥ 20 quan sát và ≥ 90% cùng một nguồn `profile.*` hoặc `current_location` là **quy tắc chính sách ứng viên** (dùng ở mục 8.9).

**Done M0:** mục 11.

---

### 8.1 `config.py`
Như mục 4.3.

### 8.2 `envloader.py`
```python
def load_toolenv_class(split: str, root: Path):
    """Chèn <root>/<split> vào sys.path, import zaic_tools, trả về ToolEnv.
    Nếu process đã nạp một split khác ⇒ raise RuntimeError (R7)."""
```
Lưu `_LOADED_SPLIT` ở mức module. Mọi nơi tạo `ToolEnv` đều đi qua hàm này.

### 8.3 `apiclient.py`
```python
class ApiClient:
    def __init__(self, base_url, api_key, timeout, max_retries): ...
    def chat(self, model, messages, tools=None, temperature=0, max_tokens=512, extra_body=None) -> dict | None
    def transcribe(self, model, wav_bytes, language="vi", temperature=0, prompt=None) -> str
```
- Dùng `openai.OpenAI(base_url, api_key, timeout, max_retries=0)` và tự retry: lỗi 429/5xx/timeout ⇒ backoff 1, 2, 4, 8, 16s (cap 30s), tối đa `max_retries` lần. Hết lần ⇒ trả `None` (chat) hoặc `""` (transcribe); **không ném lỗi ra ngoài**.
- Ghi log lỗi vào `debug/<id>.json` khi caller truyền `log`.
- `chat` truyền `extra_body` cho `chat.completions.create`.

### 8.4 `catalog.py`
```python
class Catalog:
    def __init__(self, path: str): ...
    def tools_for(self, installed_apps: dict) -> dict[str, Tool]
    def all_tools(self) -> dict[str, Tool]          # toàn catalog (dùng cho scope)
def to_llm_tools(tools: dict[str, Tool]) -> list[dict]
def resolve_tool_name(name: str, tools: dict[str, Tool]) -> str | None
def readers_for(coll: str, tools: dict[str, Tool], ref_sources: dict | None) -> list[Tool]
```
- `tools_for`: app có trong `installed_apps`; nếu `installed_apps[app]["tools"]` là list không rỗng ⇒ chỉ cho phép các tên đó (phần tử là chuỗi hoặc dict có `"name"`), ngược lại cho phép mọi tool của app. Luôn thêm `sys.ask_missing_info` (từ catalog nếu có; không thì tạo: `parameters={"type":"object","properties":{"tool_name":{"type":"string"},"params":{"type":"array","items":{"type":"string"}}},"required":["tool_name","params"]}`, `kind="meta"`).
- `one_of`: đọc `parameters["x-one-of"]` và `properties[*]["x-one-of"]`; phần tử chuỗi ⇒ nhóm `[chuỗi]`.
- `to_llm_tools`: copy `parameters`, **xóa mọi khóa bắt đầu bằng `x-`**, chuyển chú thích vào `description` của property: `x-ref` ⇒ `" (ID phải lấy từ dữ liệu ứng dụng đã đọc)"`; `x-match: fuzzy` ⇒ `" (văn bản tự do: dùng đúng từ khóa người dùng nói)"`. Tool có `one_of` ⇒ nối vào mô tả tool: `" Cần ít nhất một trong: <tên>, <tên>."`. Output: `{"type":"function","function":{"name","description","parameters"}}`.
- `resolve_tool_name`: khớp chính xác → thay `__`/`/` bằng `.` → chữ thường bỏ ký tự không phải chữ/số → `difflib.get_close_matches(cutoff=0.9)` → `None`.
- `readers_for(coll, tools, ref_sources)`: tool `kind=="read"` thỏa: (a) có trong `ref_sources[coll]` (nếu có), hoặc (b) `coll` (bỏ dấu, chữ thường, bỏ số nhiều đơn giản) xuất hiện trong `name`, `returns` hoặc `description` (bỏ dấu, chữ thường) của tool. Sắp ưu tiên (a) rồi tool không có tham số bắt buộc.

**Test (`tests/test_catalog.py`):** catalog giả; `tools_for` lọc đúng app và đúng danh sách; `x-one-of` chuẩn hóa cả hai dạng; `to_llm_tools` không còn khóa `x-` và có chú thích; `resolve_tool_name` xử lý `app__tool` và typo; `readers_for("contacts", ...)` tìm ra tool có `returns` chứa `contacts`.

### 8.5 `vi_norm.py` — phần văn bản (M1)

```python
def normalize(text) -> str          # NFC, chữ thường, thay dấu câu bằng khoảng trắng TRỪ . , : / nằm giữa hai chữ số; gộp khoảng trắng. GIỮ dấu tiếng Việt
def strip_tone(s) -> str            # chỉ bỏ 5 dấu thanh; giữ ă â ê ô ơ ư đ
def strip_accents(s) -> str         # bỏ toàn bộ dấu, đ→d, chữ thường (dùng cho BM25)
def phonetic_key(token) -> str
def token_sim(a, b) -> tuple[float, int]     # (điểm, bậc)
STOPWORDS_VI: set[str]
```

- `strip_tone`: NFD → loại các combining mark U+0300 (huyền), U+0301 (sắc), U+0309 (hỏi), U+0303 (ngã), U+0323 (nặng) → NFC. **Không** loại U+0302 (mũ), U+0306 (trăng), U+031B (râu). Ví dụ: `strip_tone("hướng") == "hương"`, `strip_tone("Thư") == "thư"`.
- `strip_accents`: NFD, bỏ mọi combining mark, `đ→d`, chữ thường.
- `phonetic_key(token)`: `t = strip_accents(token)`; áp theo thứ tự `re.sub`: `^(gi|d|r)`→`d`; `^(tr|ch)`→`c`; `^x`→`s`; `^l`→`n`; `(ng|nh)$`→`n`; `(ch|c)$`→`t`.
- `token_sim(a, b)` chấm theo **bậc** (a, b đã chữ thường, NFC):

| Bậc | Điều kiện | Điểm |
|---|---|---|
| 1 | `a == b` | 1.00 |
| 2 | `strip_tone(a) == strip_tone(b)` | 0.92 |
| 3 | `strip_accents(a) == strip_accents(b)` | 0.88 |
| 4 | `phonetic_key(a) == phonetic_key(b)` | 0.85 |
| 5 | `r = SequenceMatcher(None, strip_accents(a), strip_accents(b)).ratio()`; nếu `r ≥ 0.85` và cả hai dài ≥ 4 ký tự | `0.80 + 0.04 * (r - 0.85) / 0.15` |
| — | còn lại | 0.0, bậc 0 |

- `STOPWORDS_VI`: `cho, và, là, của, tôi, mình, em, anh, chị, bạn, một, các, những, trong, ở, đi, về, đến, lúc, giúp, hộ, nhé, nha, với, thì, mà`.

**Test (`tests/test_vi_norm.py`, phần văn bản, pass 100%):**
- `normalize("Chuyển 1.500.000 cho Thư!")` giữ `1.500.000` và dấu tiếng Việt.
- `token_sim("hướng","hương") == (0.92, 2)`; `token_sim("thư","thu") == (0.88, 3)`; `token_sim("hùng","hưng")` có bậc ≤ 5 và điểm < 0.88 (không được coi là bậc 3); `token_sim("lan","nan") == (0.85, 4)`; `token_sim("thư","thư") == (1.0, 1)`.
- `strip_tone("Hương") == "Hương"`; `strip_tone("hướng") == "hương"`.

### 8.6 `lexicon.py` và `state_store.py`

```python
# state_store.py
class StateStore:
    snapshot: dict[str, dict]            # key = f"{tool}|{json.dumps(args, sort_keys=True, ensure_ascii=False)}" → result
    entities: dict[tuple[str,str], Entity]   # key = (collection, id)
    ids: dict[str, set[str]]             # collection → các id
    collections_read: set[str]           # collection đã xuất hiện trong kết quả (kể cả list rỗng)
    executed: list[tuple[str,str]]       # (tool, args_key) mọi lệnh đã gọi (đọc + ghi)
    def ingest(self, tool: str, args: dict, result: dict) -> None
    def has_called(self, tool: str, args: dict) -> bool
    def ids_for(self, coll: str) -> set[str]       # ids[coll] nếu có, ngược lại hợp mọi tập khi XREF_MODE=="lenient", ngược lại set()
    def entity_list(self) -> list[Entity]
```

`ingest`: nếu `result.get("ok")` là True: duyệt đệ quy `result` với `parent_key`:
- Gặp `dict`: với mỗi `(k, v)`: nếu `v` là `list` ⇒ `collections_read.add(k)`; với mỗi phần tử `dict` có `"id"` (chuỗi/số ⇒ `str`): tạo/ghi đè `Entity(collection=k, id, fields=<các giá trị chuỗi cấp một trừ id>, names=<giá trị chuỗi dài 1..80, không phải ISO datetime, không phải chuỗi toàn chữ số dài > 6>, source_tool=tool)` và `ids[k].add(id)`; rồi đệ quy vào từng phần tử. Nếu `v` là `dict` ⇒ đệ quy với `parent_key=k`. Nếu bản thân `result` có `"id"` và ta biết `collection` (xem dưới) thì cũng thêm.
- Với kết quả của lệnh **ghi** có trả `id` (vd `{"ok":true,"alarm":{"id":"alm_02",...}}`): id nằm trong `dict` lồng nhau ⇒ duyệt đệ quy đã bắt được dưới `parent_key` = khóa chứa nó (`alarm`); vẫn thêm vào `ids["alarm"]` và vào một tập đặc biệt `ids["*"]` chứa mọi id gặp.
- `executed.append((tool, args_key))` luôn được ghi (thành công hay không).

`lexicon.py`:
```python
def trim_snapshot(store: StateStore, transcript: str, max_chars: int) -> str
```
- Dựng một `dict` gọn từ `store.snapshot` (nhóm theo tool, bỏ `ok`). Nếu `json.dumps(..., ensure_ascii=False)` ≤ `max_chars` ⇒ trả nguyên.
- Nếu quá: với mỗi list > 15 phần tử `dict`, giữ (a) phần tử có ít nhất một token chung với transcript (sau `strip_accents`, bỏ stopwords), (b) 10 phần tử đầu, rồi thêm `{"_note":"đã lược N mục"}`; lặp tới khi vừa; nếu vẫn quá ⇒ cắt từng tool theo thứ tự ngược độ khớp với transcript.

**Test (`tests/test_state_store.py`):** nạp kết quả giả `{"ok":true,"contacts":[{"id":"c_01","name":"Hương"},{"id":"c_02","name":"Lan"}]}` ⇒ `ids["contacts"]=={"c_01","c_02"}`, `"contacts" in collections_read`; nạp `{"ok":true,"contacts":[]}` ⇒ `contacts` vẫn thuộc `collections_read`; nạp kết quả ghi `{"ok":true,"alarm":{"id":"alm_02"}}` ⇒ `ids["*"]` chứa `alm_02`; `has_called` đúng với args khác thứ tự khóa; `trim_snapshot` giữ phần tử khớp transcript.

### 8.7 `history.py`

```python
HIST_ROLE_KEYS  = ("role", "speaker", "from")
HIST_TEXT_KEYS  = ("text", "audio_text", "content")
HIST_AUDIO_KEYS = ("audio", "audio_path")
def history_turns(item) -> list[dict]       # [{"role": "user"|"assistant", "text": str|None, "audio": str|None, "raw": dict}]
def format_history(turns, user_texts: list[str]) -> str
```
- Các khóa trên là **mặc định**; agent phải đối chiếu với `reports/history_format.md` (M0) và sửa hằng số cho khớp dữ liệu thật.
- Lượt `user` có audio ⇒ ASR (cache) ⇒ `text`; có sẵn `text` thì dùng.
- `format_history`: mỗi lượt một dòng `Người dùng: <text>` hoặc `Trợ lý: <text>`; nếu lượt trợ lý là lệnh gọi/`ask_missing_info`, hiển thị dạng `Trợ lý hỏi: <tool_name> thiếu <params>` nếu `history_format.md` cho thấy có dữ liệu đó. Giữ tối đa 6 lượt gần nhất.

### 8.8 `resolver.py`

```python
def match_entities(text_tokens: list[str], entities: list[Entity], threshold: float) -> list[Hint]
def build_hints(hyps: list[Hyp], store: StateStore, now: datetime) -> list[Hint]
def format_hints(hints: list[Hint]) -> str
```

`match_entities` (dùng `token_sim` theo bậc):
- Với mỗi `Entity` và mỗi `name`: `name_tokens = tokenize(name)` (chữ thường, tách khoảng trắng).
- **Khớp toàn tên:** trượt cửa sổ độ dài `len(name_tokens)` trên `text_tokens`; điểm = trung bình điểm `token_sim` từng cặp; mọi cặp phải ≥ `threshold`.
- **Khớp tên gọi (token cuối):** nếu `len(name_tokens) ≥ 2`: so token cuối của tên với từng token transcript; chấp nhận khi điểm ≥ 0.88 (bậc ≤ 3) và token transcript không thuộc `STOPWORDS_VI`. Hint có `extra["partial"]=True`.
- Tên một từ: yêu cầu điểm ≥ 0.88 và token không thuộc `STOPWORDS_VI`.
- Trả `Hint(kind="entity", span=<chuỗi khớp>, value=entity.id, conf=điểm, extra={"collection","name","tier","partial"})`.
- Nhiều entity cùng điểm cao cho cùng span ⇒ phát hết (gate phát hiện mơ hồ).
- **Ưu tiên bậc:** nếu cùng span có ứng viên bậc 1 duy nhất ⇒ chỉ giữ ứng viên đó.

`build_hints`:
- Chạy `match_entities` trên **từng** ứng viên n-best, gộp theo `(span, entity.id)` giữ điểm cao nhất.
- **M1:** chỉ thực thể. **M2/M3:** thêm `parse_numbers`/`parse_times` trên top-1 (mục 8.11); với mỗi ứng viên top-2/3 mà `parse_numbers` ra giá trị khác ⇒ ghi `extra["alt_values"]`.
- Hint số nằm trong khoảng một biểu thức giờ/ngày bị loại (đã xử lý trong `parse_numbers`).

`format_hints`: mỗi hint một dòng:
```
TÊN "chị thu" ≈ Thư (id c_03, tin cậy 0.88)
TÊN "lan" ≈ Nguyễn Thị Lan (id c_05, tin cậy 0.92, khớp tên gọi)
SỐ "năm trăm nghìn" = 500000
GIỜ "ba giờ chiều mai" = 2026-11-17T15:00:00+07:00
GIỜ "ba giờ" = 2026-11-17T15:00:00+07:00 hoặc 2026-11-17T03:00:00+07:00
```

**Test (`tests/test_resolver.py`):**
1. Contacts `Thư`, `Thu`, `Hương`; transcript "chuyển cho chị thư năm trăm nghìn" ⇒ ứng viên bậc 1 duy nhất là `Thư`.
2. Transcript "chuyển cho chị thu" ⇒ ứng viên là `Thu` (bậc 1), không phải `Thư`.
3. "chị hướng" ⇒ `Hương` (bậc 2).
4. Contact `Nguyễn Thị Lan`, transcript "gọi cho Lan" ⇒ hint partial `Lan`.
5. Hai contact tên `Lan` (id khác nhau) ⇒ hai hint cùng điểm.
6. Từ `cho`/`chị` không bao giờ thành hint.

### 8.9 `prompt.py`, `retrieval.py`, `policy_text.py`

**System prompt (cố định, dùng nguyên văn):**
```
Bạn là trợ lý điều khiển ứng dụng trên thiết bị bằng giọng nói. Người dùng nói tiếng Việt.
Nhiệm vụ: biến yêu cầu thành các lời gọi công cụ đúng.
Quy tắc:
1. Chỉ dùng các công cụ được cung cấp. Không bịa tên công cụ hay tham số.
2. Mọi ID (thiết bị, liên hệ, tài khoản...) phải lấy đúng từ "Dữ liệu ứng dụng" hoặc từ kết quả công cụ đọc. Không tự đặt ID. Nếu chưa có dữ liệu để lấy ID, hãy gọi công cụ đọc phù hợp trước.
3. Số tiền, giờ, ngày: ưu tiên dùng đúng giá trị trong mục "Gợi ý". Giờ dùng định dạng ISO có múi giờ.
4. Khi người dùng nói "nhà tôi", "chỗ tôi", "văn phòng" hãy dùng hồ sơ và vị trí hiện tại.
5. Nếu thiếu thông tin bắt buộc mà không thể suy ra từ yêu cầu, hồ sơ, vị trí hay dữ liệu ứng dụng: gọi sys.ask_missing_info với tool_name là công cụ định gọi và params là danh sách tên tham số còn thiếu. Không đoán.
6. Nếu không công cụ nào xử lý được yêu cầu: không gọi công cụ nào, chỉ trả lời KHONG_HO_TRO.
7. Chỉ gọi công cụ đọc khi cần dữ liệu để thực hiện yêu cầu hoặc khi yêu cầu chính là hỏi thông tin. Không gọi lại công cụ đã gọi. Chỉ gọi công cụ ghi khi chắc chắn.
8. Với tham số văn bản tự do (nội dung, tiêu đề, ghi chú, truy vấn): dùng đúng từ khóa người dùng nói, ngắn gọn, không thêm từ.
9. Khi đã hoàn tất mọi việc người dùng yêu cầu, trả lời XONG và không gọi thêm công cụ.
```

**User message** (các mục nối bằng dòng trống, đúng thứ tự; bỏ mục không có dữ liệu):
```
Thời gian hiện tại: {current_time} ({timezone}); thứ {weekday_vi}
Vị trí hiện tại: {current_location}
Hồ sơ: {json user_profile}
Lịch sử: {format_history(...)}
Quy tắc bổ sung: {policy_text}                           # nếu ENABLE_POLICY_RULES
Ví dụ tương tự: {few-shot}                               # nếu ENABLE_FEWSHOT
Yêu cầu: {hyps[0].text}
Cách nghe khác: {hyps[1].text} | {hyps[2].text}          # chỉ khi khác top-1
Gợi ý: {format_hints(hints)}
Dữ liệu ứng dụng:
{trim_snapshot(...)}
```
`weekday_vi = ["hai","ba","tư","năm","sáu","bảy","chủ nhật"][now.weekday()]`.

**`retrieval.py` (few-shot, bật bằng `ENABLE_FEWSHOT`):**
```python
class FewShotIndex:
    def __init__(self, samples: list[dict], catalog: Catalog): ...   # samples = các mẫu train trong tune_ids
    def query(self, transcript: str, installed_tools: set[str], k: int) -> list[dict]
def format_fewshot(examples, catalog) -> str
```
- Chỉ mục BM25 (tự cài, k1=1.5, b=0.75) trên `strip_accents(audio_text)` (bỏ stopwords).
- Chỉ nhận ví dụ mà mọi tool trong gold của nó thuộc `installed_tools` của mẫu hiện tại (để không gợi ý tool không có). Loại chính mẫu hiện tại khi đánh giá train.
- Khi chạy `public_test`: chỉ mục dựng từ **toàn bộ train**. Khi đánh giá trên train: dựng từ `tune_ids` (không gồm `heldout`).
- Lấy top `FEWSHOT_K`; nếu trong top-10 có ví dụ `ask` hoặc `refuse` mà top-K chưa có loại đó, thay ví dụ thấp điểm nhất bằng nó (tối đa một ví dụ mỗi loại).
- Định dạng mỗi ví dụ (ID ở tham số `x-ref` thay bằng `<id lấy từ dữ liệu>`):
```
Yêu cầu: "chuyển cho Lan năm trăm nghìn"
Gọi: contacts.search(query="Lan"); banking.transfer(contact_id=<id lấy từ dữ liệu>, amount=500000)
---
Yêu cầu: "đặt xe đón tôi"
Gọi: sys.ask_missing_info(tool_name="ride.book", params=["to"])
---
Yêu cầu: "mua vé máy bay"
Gọi: (không gọi công cụ nào)
```
Thêm dòng cuối: `Các ID trong ví dụ thuộc người dùng khác; chỉ dùng ID từ "Dữ liệu ứng dụng".`

**`policy_text.py` (bật bằng `ENABLE_POLICY_RULES`):** đọc `reports/policy_rules.json`; với mỗi `(tool, param)` ứng viên, nếu `tool` thuộc `installed_tools` của mẫu hiện tại, sinh một câu theo mẫu:
- nguồn `profile.<khóa>`: `Khi gọi {tool}, nếu người dùng không nói rõ {param}, dùng hồ sơ: {khóa}.`
- nguồn `current_location`: `Khi gọi {tool}, nếu người dùng không nói rõ {param}, dùng vị trí hiện tại.`
Tối đa 6 câu mỗi mẫu. Không tự viết quy tắc ngoài mẫu này.

### 8.10 `llm.py`

```python
class LLM:
    def __init__(self, base_url, api_key, model, extra_body, temperature=0, timeout=60, max_retries=5): ...
    def generate(self, messages, tools=None, max_tokens=512, log=None) -> tuple[list[Call], str, dict]   # (calls, text, assistant_message)
def parse_tool_calls(message: dict) -> list[Call]
def parse_tool_calls_text(text: str) -> list[Call]
def extract_text(message: dict) -> str
```
- `client.chat(model, messages, tools=tools, tool_choice="auto", temperature=0, max_tokens, extra_body=extra_body)`.
- **Structured (ưu tiên):** `message.tool_calls` → `.id`, `.function.name`, `.function.arguments` (JSON string ⇒ `json.loads` trong `try/except`; lỗi ⇒ bỏ qua). Giữ `.id` ⇒ `Call.call_id`; nếu rỗng thì tự sinh `f"call_{n}"`.
- **Fallback text:** nếu `tool_calls` rỗng mà `content` chứa `<tool_call>…</tool_call>` hoặc một JSON có `name` và `arguments` ⇒ `parse_tool_calls_text` (regex `<tool_call>\s*(\{.*?\})\s*</tool_call>` với `re.S`, `json.loads`). Không có ⇒ `[]`.
- `extract_text`: `message.content` bỏ các khối tool call; dùng phát hiện `KHONG_HO_TRO` / `XONG`.
- Lỗi API (nhận `None`) ⇒ `([], "", {})`.

**Test:** `parse_tool_calls` trên message giả có `tool_calls`; trên text có `<tool_call>`; trên JSON hỏng ⇒ `[]`.

### 8.11 `vi_norm.py` — số và giờ (M2)

```python
def parse_numbers(text: str) -> list[Hint]            # kind="number" | "digits"
def parse_times(text: str, now: datetime) -> list[Hint]   # kind="time"; extra={"kind","alternatives"}
```

**Số (thuật toán):**
1. Dùng tokenizer nhẹ giữ `, . :` giữa chữ số; **không** dùng `normalize()` cho bước regex số.
2. Từ điển: `không/0, một/1, mốt/1, hai/2, ba/3, bốn/4, tư/4, năm/5, lăm/5, sáu/6, bảy/7, bẩy/7, tám/8, chín/9, mười/10`; nhân: `mươi/chục` (×10), `trăm` (100); đơn vị: `nghìn/ngàn` (1e3), `triệu` (1e6), `tỷ/tỉ` (1e9); đặc biệt: `lẻ/linh` (bỏ qua, chỉ đánh dấu chữ số 0 hàng chục), `rưỡi`.
3. Gom span liên tiếp gồm token số/đơn vị; tích lũy `total, cur, pending, last_unit`:
   - token chữ số (từ hoặc `500`): `pending = giá trị`;
   - `trăm`: `cur += (pending or 1) * 100`; `pending = None`;
   - `mười`: `cur += 10`;
   - `mươi/chục`: `cur += (pending or 1) * 10`; `pending = None`;
   - đơn vị: `cur += pending or 0`; nếu `cur == 0` thì `cur = 1`; `total += cur * unit`; `last_unit = unit`; `cur = 0; pending = None`;
   - `rưỡi`: nếu có `last_unit` ⇒ `total += last_unit / 2`;
   - kết thúc span: `cur += pending or 0`; phần dư không có đơn vị sau `last_unit`: nếu `cur < 10` ⇒ `total += cur * last_unit / 10`; nếu `cur < 1000` và `cur % 100 == 0` ⇒ `total += cur * last_unit / 1000`; ngược lại `total += cur`.
4. Dạng chữ số + đơn vị: regex `(\d+(?:[.,]\d+)?)\s*(k|ka|nghìn|ngàn|tr|triệu|tỷ|đ|đồng|vnd)\b`. Dấu phẩy là thập phân khi sau 1–2 chữ số rồi tới đơn vị; `\d{1,3}(\.\d{3})+` là phân tách hàng nghìn. Span nào regex này khớp thì bỏ kết quả đường chữ trên span đó.
5. **Chuỗi chữ số rời:** ≥ 6 token chữ số đơn liên tiếp ⇒ `Hint(kind="digits", value="chuỗi chữ số")`, không phát `number`.
6. **Loại trừ giờ/ngày:** bỏ span nếu token kế tiếp ∈ {`giờ, phút, tiếng, ngày, tháng, tuần, h`} hoặc token liền trước ∈ {`ngày, tháng, lúc, thứ`}.
7. `conf = 0.95` nếu span có đơn vị tiền/đơn vị lớn; `0.8` nếu số trần.

**Giờ/ngày:** định dạng `YYYY-MM-DDTHH:MM:SS+07:00` (offset từ `now.tzinfo`, luôn có giây `:00`); chỉ có ngày ⇒ `YYYY-MM-DD`.
1. **Khoảng thời gian:** `sau X (phút|tiếng|giờ|ngày)`, `X (phút|tiếng|giờ|ngày) nữa`, `nửa tiếng`, `X tiếng rưỡi` ⇒ `now + delta`, làm tròn phút, `conf=0.9`.
2. **Ngày:** `hôm nay|nay` (+0), `ngày mai|mai` (+1), `ngày mốt|ngày kia|mốt` (+2), `hôm qua` (−1); `thứ hai..thứ bảy|chủ nhật` ↔ weekday 0..6 (`thứ tư`=2, `thứ năm`=3, `thứ sáu`=4); `ngày D`, `ngày D tháng M`, `D/M`, `D tháng M`.
   - Có `tuần sau|tuần tới` ⇒ `thứ_hai_tuần_sau + wd` với `thứ_hai_tuần_sau = today + (7 - today.weekday())`; có `tuần này` ⇒ `thứ_hai_tuần_này + wd`; không có ⇒ `delta = (wd - today.weekday()) % 7`, nếu `delta == 0` ⇒ 7 (trừ khi có `hôm nay`).
   - `ngày D` không tháng: tháng này nếu `D ≥ today.day`, ngược lại tháng sau.
3. **Giờ trong ngày:** `X giờ`, `X giờ rưỡi`, `X giờ Y (phút)`, `X giờ kém Y`, `Xh`, `XhYY`, `X:YY`. **Áp từ chỉ buổi lên `h` gốc trước, rồi mới xử lý `kém`/`rưỡi`/phút.** `kém Y` ⇒ `(h-1):(60-Y)`; `rưỡi` ⇒ `:30`.
   - Từ chỉ buổi trong cửa sổ 3 token quanh biểu thức giờ: `sáng` ⇒ giữ `h`; `trưa` ⇒ `h` nếu `h ≥ 10` ngược lại `h+12`; `chiều`, `tối` ⇒ `h+12` nếu `h < 12`; `đêm` ⇒ `h+12` nếu `6 ≤ h < 12`, `0` nếu `h == 12`, ngược lại `h`.
   - Không có từ chỉ buổi và `h ≤ 12` ⇒ hai ứng viên `h` và `h+12`. Ứng viên chính: ngày ≠ hôm nay ⇒ `h+12` nếu `1 ≤ h ≤ 6`, `h` nếu `7 ≤ h ≤ 11`, `12` nếu `h == 12`; ngày = hôm nay ⇒ ứng viên sớm nhất lớn hơn `now`. `conf = 0.6`, ứng viên còn lại để trong `extra["alternatives"]`. `h ≥ 13` hoặc `h == 0` ⇒ `conf = 0.9`.
4. **Kết hợp:** có giờ mà không có ngày ⇒ hôm nay; kết quả ≤ `now` ⇒ +1 ngày. Có ngày không có giờ ⇒ `Hint(kind="time")` chỉ có ngày.

**Bảng test bắt buộc pass 100% (`tests/test_vi_norm.py`), `now = 2026-11-16T17:00:00+07:00` (thứ Hai):**

| Đầu vào | Kết quả mong đợi |
|---|---|
| "năm trăm nghìn" | 500000 |
| "500 nghìn" / "500k" | 500000 |
| "hai triệu rưỡi" | 2500000 |
| "một triệu rưỡi" | 1500000 |
| "hai nghìn rưỡi" | 2500 |
| "ba mươi lăm nghìn" | 35000 |
| "một tỷ hai" | 1200000000 |
| "một triệu hai trăm" | 1200000 |
| "một trăm lẻ năm" | 105 |
| "hai mươi mốt" | 21 |
| "mười lăm" | 15 |
| "năm chục nghìn" | 50000 |
| "1,5 triệu" | 1500000 |
| "không chín bảy không một chín năm bảy tám ba chín" | digits "09701957839" |
| "nhắc tôi họp lúc ba giờ chiều mai" | time 2026-11-17T15:00:00+07:00; `parse_numbers` trả `[]` |
| "năm giờ rưỡi sáng mai" | 2026-11-17T05:30:00+07:00 |
| "họp thứ sáu tuần sau lúc 9 giờ sáng" | 2026-11-27T09:00:00+07:00 |
| "thứ sáu lúc 8 giờ tối" | 2026-11-20T20:00:00+07:00 |
| "hai tiếng nữa" | 2026-11-16T19:00:00+07:00 |
| "ba mươi phút nữa" | 2026-11-16T17:30:00+07:00 |
| "tám giờ tối nay" | 2026-11-16T20:00:00+07:00 |
| "bảy giờ kém mười lăm sáng mai" | 2026-11-17T06:45:00+07:00 |
| "bảy giờ kém mười lăm chiều mai" | 2026-11-17T18:45:00+07:00 |
| "mười lăm giờ" | 2026-11-17T15:00:00+07:00 (đã qua giờ hôm nay) |
| "ngày 20 tháng 12 lúc 10 giờ" | 2026-12-20T10:00:00+07:00, `conf` 0.6, alternatives có 22:00 |
| "ngày mốt" | "2026-11-18" |

### 8.12 `asr.py` và `eval/asr_eval.py`

```python
class ASR:
    def __init__(self, mode="api"|"gold"|"local", ...): ...
    def transcribe(self, wav_path, prompt=None) -> list[Hyp]
def transcribe_sample(item, asr, split_dir, log) -> tuple[list[Hyp], list[str]]    # (hyps lượt hiện tại, văn bản các lượt user trong history)
def is_degenerate(text: str, duration_s: float) -> bool
def trim_silence(samples, sr=16000) -> samples
```

- Đọc WAV bằng `soundfile`, mono float32 16 kHz.
- **Cắt lặng** (`ASR_SILENCE_TRIM`): RMS theo khung 20 ms; giữ từ khung đầu tới khung cuối có RMS > `0.02 * max_rms` (đệm 150 ms mỗi đầu). Cắt còn < 0.3 s ⇒ giữ bản gốc.
- **`mode="gold"`:** dùng `label.audio_text` (chỉ train; mẫu không có label ⇒ raise lỗi rõ ràng). Với history: dùng `audio_text` của lượt nếu có.
- **`mode="api"`:** `client.audio.transcriptions.create(model=STT_MODEL, file=bytes, language="vi", temperature=0)` ⇒ `text`. N-best: nếu provider hỗ trợ `temperature > 0`, gọi `ASR_NBEST` lần, giữ các bản khác nhau; không thì `[Hyp(top1, 1.0)]` và ghi `debug["asr_nbest"]="single"`.
- **`mode="local"`:** `WhisperForConditionalGeneration` + `WhisperProcessor` từ `ASR_LOCAL_MODEL`; nạp **một lần** ở mức module; `language="vi"`, `task="transcribe"`, `num_beams=ASR_BEAMS`, `num_return_sequences=ASR_NBEST`, `return_dict_in_generate=True`, `output_scores=True`; điểm = `sequences_scores`. Hotwords (khi `ENABLE_HOTWORD_REASR` và có entity): `prompt_ids = processor.get_prompt_ids(hotwords)` truyền vào `generate(prompt_ids=...)`; khi giải mã bỏ phần prompt khỏi văn bản. Thiết bị: `cuda` nếu có, ngược lại `mps`, ngược lại `cpu`.
- **`is_degenerate(text, duration_s)`:** rỗng; hoặc số token / `duration_s` > 6; hoặc n-gram (n = 1..3) lặp liên tiếp ≥ 4 lần. Ứng viên suy biến bị loại; nếu loại hết ⇒ gọi lại một lần không có prompt; vẫn hỏng ⇒ `[Hyp("", -inf)]`.
- Mọi ứng viên đi qua `normalize()`.
- Cache theo đường dẫn audio trong `cache/asr_<mode>_<model>_<split>.json` (khóa là đường dẫn tương đối của audio).
- `transcribe_sample`: lượt hiện tại ⇒ `transcribe(item["audio"])`; mỗi lượt user trong `history` (xem `history.py`) có audio ⇒ `transcribe` top-1; có sẵn `text` thì dùng.

**`eval/asr_eval.py`:**
```
python eval/asr_eval.py --backend api|local --model <tên> --ids tune_ids.txt --limit 200 --out runs/asr_<tên>
```
- WER: tự cài khoảng cách chỉnh sửa trên token (sau `normalize`).
- **Lỗi thực thể** (từ `cache/entities_train.json`): với mỗi mẫu, thực thể gold gồm (a) chuỗi tên/từ khóa trong gold `arguments` (không phải ID/enum/ISO); (b) số trong gold args; (c) giá trị giờ ISO trong gold args. Một thực thể gọi là **đúng** nếu: (a) chuỗi gold (sau `normalize`) là dãy token con của transcript; (b) `parse_numbers(transcript)` chứa giá trị đó; (c) `parse_times(transcript, now)` chứa giá trị đó (chính hoặc `alternatives`).
- **Phân loại lỗi** cho mỗi thực thể loại (a) sai: `chi_sai_dau_thanh` (đúng sau `strip_tone`), `sai_vung_mien` (đúng sau `phonetic_key`), `sai_khac`, `mat_hoan_toan`. In bảng đếm.
- Chọn ASR: tỉ lệ lỗi thực thể thấp nhất; hòa thì WER thấp hơn.

### 8.13 `scope.py`

```python
def in_scope(llm, hyps, installed_tools, all_tools, ctx, log) -> tuple[bool, dict]
```
**Đặc trưng (từ vựng):**
1. BM25 (tự cài, k1=1.5, b=0.75) giữa transcript top-1 (bỏ dấu, bỏ stopwords) và "tài liệu" của mỗi tool trong **toàn catalog** = `app + app_name_vi + app_description + tên tool + mô tả tool` (bỏ dấu). Tính IDF trên toàn catalog.
2. `best_all = max điểm trên mọi tool`; `best_installed = max điểm trên tool thuộc app đã cài`.
3. `ratio = best_installed / max(best_all, ε)` (ε = 1e-6).
4. `coverage` = tỉ lệ token nội dung (không stopword) của transcript xuất hiện trong "tài liệu" của tool installed có điểm cao nhất.

**Quyết định:**
- Nếu `ratio ≥ SCOPE_SKIP_LLM_IF_RATIO_GE` và `coverage ≥ SCOPE_COVERAGE_THRESHOLD` ⇒ in-scope, **không gọi LLM**.
- Ngược lại gọi LLM (prompt ngắn, không snapshot): danh sách `tool.name: mô tả` của **tool đã cài** + `Yêu cầu: {transcript}`; chỉ thị: *"Trả lời đúng một từ. CO nếu có công cụ nào thực hiện được yêu cầu, hoặc yêu cầu thiếu thông tin nhưng thuộc phạm vi của công cụ. KHONG nếu không công cụ nào liên quan."* `max_tokens=3`, `temperature=0`.
- Ngoài phạm vi **khi và chỉ khi** `LLM == KHONG` **và** (`ratio < SCOPE_RATIO_THRESHOLD` **hoặc** `coverage < SCOPE_COVERAGE_THRESHOLD`).
- Transcript rỗng ⇒ ngoài phạm vi.

**Tune:** `eval/run.py --tune-scope` quét lưới `SCOPE_RATIO_THRESHOLD ∈ {0.2..0.9 bước 0.1}` × `SCOPE_COVERAGE_THRESHOLD ∈ {0.0..0.6 bước 0.1}` trên `tune_ids`, chọn cặp tối đa hóa F1 của lớp `refuse` với ràng buộc recall của `act+ask` ≥ 99%. Ghi vào `reports/scope_tune.json`. **Trước khi code**, đọc `reports/refuse_analysis.json`: nếu đa số refuse là "khớp một app không được cài" thì `ratio` là tín hiệu chính; nếu là "không khớp app nào" thì `coverage` là tín hiệu chính; ghi nhận xét vào `open_questions.md`.

**M1:** `in_scope` là stub `return True, {}`.

**Test (`tests/test_scope.py`):** catalog giả có 2 app (`ride`, `weather`), chỉ cài `ride`; "đặt xe về nhà" ⇒ in-scope không cần LLM; "thời tiết ngày mai thế nào" (app `weather` không cài) ⇒ `ratio` thấp; FakeLLM trả KHONG ⇒ ngoài phạm vi; FakeLLM trả CO ⇒ in-scope.

### 8.14 `prefetch.py`

```python
def select_prefetch_tools(tools, transcript, ref_sources, mode, max_reads) -> list[Tool]
def run_prefetch(env, store: StateStore, tools_to_call: list[Tool], log) -> None
```
- `mode == "off"` ⇒ trả `[]`.
- `mode == "deps"`: (1) xếp hạng tool **ghi** đã cài theo BM25 với transcript, lấy top 3; (2) với mỗi tool, lấy các tham số có `x-ref` ⇒ tập `coll`; (3) với mỗi `coll`: `readers_for(coll, tools, ref_sources)` và chọn tool đọc **không có tham số bắt buộc** đầu tiên; (4) khử trùng, cắt còn `max_reads`.
- `mode == "all"`: mọi tool `kind=="read"` không tham số bắt buộc và không `one_of`, sắp theo tên, cắt `max_reads`. Chỉ dùng cho ablation.
- `run_prefetch`: `res = safe_call(env, tool.name, {}, log)`; `store.ingest(...)`.
- **Luôn chạy sau `scope`** (R3).

### 8.15 `gate.py` — **module quan trọng nhất**

```python
def gate(raw_calls, text, ctx, tools, store, hints, env, state, transcript) -> GateResult
```
`state` là một đối tượng đơn giản chứa: `nudges_used`, `writes_done`, `executed` (từ `store.executed`).

Duyệt `raw_calls` theo thứ tự. Với mỗi `call`:

1. `name = resolve_tool_name(call.name, tools)`; `None` ⇒ note, bỏ.
2. `name == "sys.ask_missing_info"` ⇒ `model_ask = sanitize_ask(call.args, tools)`; `continue`. `sanitize_ask`: `tool_name` phải thuộc `tools` (dùng `resolve_tool_name`; không được ⇒ bỏ); `params` chỉ giữ tên thuộc `required` ∪ (mọi tham số trong `one_of`) của tool đó; rỗng ⇒ ask bị bỏ.
3. `tool = tools[name]`. Nếu `tool.kind == "read"` và `DROP_DUPLICATE_READS` và `store.has_called(name, args)` hoặc đã có trong chính danh sách này ⇒ bỏ (note). (Đọc có args khác thì giữ.)
4. `raw_args = dict(call.args)`; `args = coerce_args(tool, raw_args)`:
   - bỏ khóa không có trong `props`;
   - ép kiểu theo `type`: `"500000"`→int, `500000.0`→int khi type là integer, `"true"`→bool, chuỗi số thực→float; strip khoảng trắng thừa;
   - `enum`: không thuộc ⇒ thử khớp không phân biệt hoa thường, rồi `difflib.get_close_matches(cutoff=0.8)`; không được ⇒ **xóa tham số**.
5. **`fix_refs(tool, args)`** — với mỗi tham số `p` có `x-ref` (`coll = x_ref.split(".")[-1]`), giá trị `v`:
   - `v ∈ store.ids_for(coll)` hoặc `v ∈ store.ids["*"]` ⇒ giữ.
   - Ngược lại nếu `coll ∈ store.collections_read`:
     - `XREF_MODE == "strict"`: tìm ứng viên bằng `match_entities([v đã chuẩn hóa], entities cùng collection)` rồi bằng `hints` entity cùng collection; đúng **một** ứng viên cao nhất (hơn ứng viên kế ≥ `ENTITY_AMBIGUITY_GAP`) ⇒ thay bằng `entity.id`; còn lại ⇒ **xóa tham số**.
     - `lenient`: chỉ thay khi có ứng viên duy nhất; không thì giữ nguyên.
   - Ngược lại (**`coll` chưa từng được đọc**): giá trị **chưa xác minh**.
     - Nếu `tool.kind == "write"` và `DEFER_UNVERIFIED_REF_WRITES` và `state.nudges_used < MAX_NUDGES` và `readers_for(coll, tools, ref_sources)` không rỗng ⇒ **hoãn call**: thêm vào `deferred`, thêm `(name, p, coll)` vào `needs_read`; `continue` sang call kế.
     - Ngược lại giữ nguyên giá trị (để `env.validate`/`env.call` quyết định).
6. **`autofill_refs`** (`ENABLE_AUTOFILL_REF`): với mỗi tham số `x-ref` **vắng** mà thuộc `required` hoặc `one_of`: nếu `hints` có đúng một entity cùng `coll` với `conf ≥ ENTITY_UNIQUE_MIN_CONF` (và cùng collection được `collections_read`) ⇒ điền `entity.id` (note).
7. `missing = missing_params(tool, args)`:
   - tham số `required` vắng ⇒ thiếu;
   - `x-one-of`: nếu không nhóm nào đủ ⇒ thiếu. **Chọn nhóm để hỏi** (`ONE_OF_ASK_MODE == "auto"`), theo thứ tự ưu tiên: (a) nhóm có tham số xuất hiện trong `raw_args` (LLM định dùng); (b) nhóm có tham số mang `x-ref` mà `hints` có entity cùng collection; (c) nhóm có tên tham số/mô tả (bỏ dấu) xuất hiện trong `transcript`; (d) nhóm đầu tiên. Hỏi **đúng 1 tham số** của nhóm đã chọn (mỗi nhóm trong catalog đúng 1 tham số).
   - Có `missing` ⇒ `gate_ask = Ask(tool.name, missing)` (nếu chưa có), **bỏ call này, rồi tiếp tục** duyệt các call sau (gold cho thấy `ask` luôn ở cuối, phía trước có thể có read/write đã thực hiện).
8. `env.validate(name, args)`: `ok:false` ⇒ sửa **một** lần: nếu lỗi nhắc tên tham số `P` và `P` không bắt buộc thì xóa `P` rồi validate lại; không được ⇒ bỏ call (note).
9. Giữ call.

**Sau vòng lặp:**
- **Ask cuối cùng:** nếu có `gate_ask` ⇒ dùng nó; ngược lại nếu có `model_ask` hợp lệ ⇒ dùng `model_ask`. Chỉ một ask mỗi mẫu (giữ cái đầu).
- `ENABLE_OVERRIDE`: với call đã giữ, tham số thời gian (property có `format` chứa `date`, hoặc tên/mô tả chứa `time|giờ|ngày|thời gian|at|date`) mà đúng **một** hint `time` có `conf ≥ 0.9` và khác giá trị hiện tại ⇒ ghi đè; tham số tiền (tên/mô tả chứa `amount|tiền|giá|price`) mà đúng **một** hint `number` có `conf ≥ 0.9` ⇒ ghi đè. Ghi mọi ghi đè vào `notes`.
- `ENABLE_AMBIG_ASK`: call có tham số `x-ref` mà các hint entity cùng collection có ≥ 2 ứng viên cách nhau < `ENTITY_AMBIGUITY_GAP` và giá trị đã chọn nằm trong số đó ⇒ `ask = Ask(tool.name, [p])` thay cho call. (Mặc định tắt vì gold không có ask do mơ hồ.)
- **Chống lặp:** trong cùng `raw_calls`, hai call giống hệt tên + args ⇒ bỏ call sau. (Gold có 163 mẫu gọi trùng *tên* nhưng khác args ⇒ chỉ khử khi giống hệt.)
- **Quyết định cuối:** nếu có `ask` và có `calls` ⇒ theo `ASK_AFTER_PARTIAL`: `True` ⇒ giữ cả hai; `False` ⇒ chỉ `ask`. Nếu không có `calls`, không có `ask`, không có `deferred` ⇒ `refuse = True` (note `silent` nếu `text` không chứa `KHONG_HO_TRO`).

**Test (`tests/test_gate.py`, dùng `FakeEnv` với `validate` trả `ok:True`):**
1. ID bịa, collection **đã đọc**, có đúng một ứng viên theo tên ⇒ thay đúng ID.
2. ID bịa, collection đã đọc, không ứng viên ⇒ tham số bị xóa ⇒ thành `Ask`.
3. ID mới đọc ở lượt trước (đã `store.ingest`) ⇒ **giữ nguyên** (regression cho lỗi xóa nhầm).
4. Collection **chưa đọc**, tool ghi, có `readers_for` ⇒ call bị hoãn, `needs_read` đúng; khi `nudges_used == MAX_NUDGES` ⇒ giữ nguyên giá trị.
5. Thiếu `required` ⇒ `Ask` đúng `tool_name`/`params`.
6. `x-one-of` thiếu ⇒ `Ask` **đúng 1 tham số** của nhóm LLM định dùng.
7. Tool ngoài `installed_apps` bị loại.
8. `enum` sai hoa/thường được sửa.
9. Hai call giống hệt trong cùng danh sách còn một.
10. Read đã gọi với **cùng args** bị bỏ; read với args khác được giữ.
11. Call thiếu tham số **không làm dừng** các call sau.
12. `autofill_refs`: tham số `contact_id` vắng, hint duy nhất `conf ≥ 0.9` ⇒ được điền; có hai hint ⇒ không điền ⇒ `Ask`.
13. Danh sách rỗng và `text` có `KHONG_HO_TRO` ⇒ `refuse=True`.

### 8.16 `planner.py`, `executor.py`, `agent.py`, `infer.py`

**`planner.py`:**
```python
def plan(llm, tools, messages, log) -> tuple[list[Call], str, dict]:
    return llm.generate(messages, tools=to_llm_tools(tools), log=log)
```
Truyền **toàn bộ** tools (kể cả tool đọc) để planner gọi được read tool có tham số ở lượt sau.

**`executor.py`:**
```python
def safe_call(env, name, args, log) -> dict     # try/except quanh env.call; lỗi ⇒ {"ok": False, "error": str(e)}; không ném ra ngoài
def run_plan(env, llm, tools, messages, store, ctx, transcript, hints_fn, deadline, log) -> None
```
Vòng lặp B2, `turn` từ 1 đến `MAX_TURNS` (dừng sớm nếu `deadline.expired()`):
1. `calls, text, amsg = plan(llm, tools, messages, log)`.
2. **Im lặng ở lượt 1:** nếu `calls` rỗng, `text` không chứa `KHONG_HO_TRO`/`XONG` và `turn == 1` và `silent_retries < SILENT_RETRY` ⇒ thêm vào `messages` một user message `"Yêu cầu nằm trong phạm vi các công cụ. Hãy gọi công cụ phù hợp, hoặc gọi sys.ask_missing_info nếu thiếu thông tin."`, tăng `silent_retries`, lặp lại bước 1.
3. `res = gate(calls, text, ctx, tools, store, hints_fn(), env, state, transcript)`.
4. `res.refuse` ⇒ kết thúc (ở lượt 1 nghĩa là từ chối; không gọi tool nào).
5. Ở `turn ≥ 2`: bỏ mọi lệnh ghi **giống hệt** (tên + args) một lệnh đã thực thi, trừ khi `transcript` chứa một từ trong `REPEAT_MARKERS`.
6. Thực thi lần lượt `res.calls`: nếu `tool.kind == "write"` thì tăng bộ đếm ghi, vượt `MAX_WRITES` ⇒ dừng; `result = safe_call(...)`; `store.ingest(...)`. Gom các call đã thực thi và kết quả của chúng.
7. Cập nhật `messages`: nếu có call đã thực thi ⇒ thêm **một** assistant message `{"role":"assistant","content": text or "", "tool_calls":[{"id":call_id,"type":"function","function":{"name":...,"arguments": json.dumps(args, ensure_ascii=False)}}, ...]}` (chỉ gồm call **đã thực thi**) và một message `{"role":"tool","tool_call_id":call_id,"content": json.dumps(result, ensure_ascii=False)[:3000]}` cho từng call.
8. **Hoãn (needs_read):** nếu `res.deferred` không rỗng ⇒ `state.nudges_used += 1`; thêm user message: `"Các giá trị ID sau chưa được xác minh vì chưa đọc dữ liệu: {danh sách "param của tool (collection)"}. Hãy gọi công cụ đọc phù hợp để lấy ID rồi mới gọi lại công cụ ghi."`; sang lượt kế.
9. Nếu `res.ask`: thực thi `safe_call(env, "sys.ask_missing_info", {"tool_name":..., "params":[...]})` **sau** các call của lượt này; kết thúc vòng lặp.
10. Không có call nào được thực thi, không ask, không deferred ⇒ kết thúc.
11. `text` chứa `XONG` ⇒ kết thúc. Ngược lại sang lượt kế (planner thấy kết quả tool).

**`agent.py`:**
```python
class Agent:
    def __init__(self, catalog, asr, llm, ref_sources, fewshot_index=None): ...
    def run(self, item, env, split_dir, deadline, log):
        installed = item["context"]["installed_apps"]
        tools = catalog.tools_for(installed)
        hyps, hist_texts = transcribe_sample(item, asr, split_dir, log)
        transcript = hyps[0].text
        ok, scope_dbg = in_scope(llm, hyps, tools, catalog.all_tools(), item["context"], log)
        if not ok: return                                   # chưa gọi tool nào
        store = StateStore()
        run_prefetch(env, store, select_prefetch_tools(tools, transcript, ref_sources, PREFETCH_MODE, PREFETCH_MAX_READS), log)
        now = datetime.fromisoformat(item["context"]["current_time"])
        hints_fn = lambda: build_hints(hyps, store, now)
        messages = build_messages(item, hyps, hist_texts, hints_fn(), store, fewshot_index, tools)
        run_plan(env, llm, tools, messages, store, item["context"], transcript, hints_fn, deadline, log)
```
`hints_fn` tính lại mỗi lượt vì `store` đã thay đổi. Ghi `debug/<id>.json` (tối đa `DEBUG_MAX_BYTES`): `hyps`, `scope`, `snapshot_keys`, `hints`, `planner_raw`, `gate_notes`, `executed`, `nudges_used`, `asr_nbest`.

**`infer.py`** (theo template README):
```python
def infer(item):
    EnvCls = load_toolenv_class(SPLIT, DATA_ROOT)
    env = EnvCls(SPLIT, item["id"], root=DATA_ROOT)        # đúng 1 lần
    try:
        AGENT.run(item, env, DATA_ROOT / SPLIT, Deadline(SAMPLE_DEADLINE_S), log)
    except Exception as e:
        log_exception(item["id"], e)                        # vẫn xuất dòng cho mẫu này
    return env.get_tool_calls(), env.get_state_hash()
```
`AGENT` (ASR, LLM, Catalog, ref_sources, few-shot index) khởi tạo **một lần** ở mức module. Vòng ghi `submission.jsonl` bọc `try/except` từng mẫu (nếu `infer` ném lỗi trước khi có `env`, ghi `tool_calls=[]` và hash lấy từ một `ToolEnv` mới **chỉ trong trường hợp `ToolEnv` chưa được tạo**). CLI:
```
python infer.py --split public_test --out submission.jsonl [--workers 1] [--ids file]
```
Mặc định `--workers 1`. Chỉ dùng `--workers > 1` sau khi kiểm tra: chạy 20 mẫu với `workers=1` và `workers=4`, hai kết quả phải **giống hệt** (tool_calls và hash).

### 8.17 Backend local và đóng gói (R0)

**LLM cục bộ** (cùng giao diện OpenAI-compatible, chỉ đổi `.env`):
```
vllm serve Qwen/Qwen3-4B --enable-auto-tool-choice --tool-call-parser hermes --max-model-len 8192 --port 8000
LIFEMATE_LLM_BASE_URL=http://localhost:8000/v1
LIFEMATE_LLM_MODEL=Qwen/Qwen3-4B
LIFEMATE_LLM_EXTRA_BODY={"chat_template_kwargs":{"enable_thinking":false}}
```
(Kiểm tra cờ theo tài liệu vLLM hiện hành; server tương thích khác như llama.cpp/Ollama dùng được nếu hỗ trợ `tools`.) `llm.py` vẫn có nhánh fallback text-JSON phòng khi server không parse tool call.

**ASR cục bộ:** `ASR_MODE="local"` (mục 8.12).

**Ngân sách tham số (chờ xác nhận R0):** tổng tham số ASR + LLM phải < 6B (ví dụ PhoWhisper-medium ≈ 0.77B + Qwen3-4B ≈ 4B). Ghi cấu hình cuối vào `reports/final_config.md`.

**Đóng gói (M7):** `infer.py` phải chạy không cần mạng khi `LIFEMATE_LLM_BASE_URL` trỏ server cục bộ và `ASR_MODE="local"`. Entry point: `python infer.py --split <split> --out <file>` đọc `DATA_ROOT` từ biến môi trường. Trọng số mô hình nằm ngoài git (`models/`).

---

## 9. Metric và đánh giá

### 9.1 Định nghĩa (nếu `reports/zaic_scoring.md` có công thức BTC thì **dùng nguyên văn** và bỏ mục này)
- **F1-call (chính):** với mỗi mẫu, so **multiset** call dự đoán với gold:
  - **strict:** cùng `name` và `arguments` bằng nhau (so sâu, bỏ qua thứ tự khóa; số `500000` và `500000.0` coi là bằng nhau);
  - **fuzzy-aware:** cùng `name`; tham số `x-match: fuzzy` so token-F1 ≥ 0.8 (sau `normalize`), mọi tham số khác bằng nhau;
  - **soft:** chỉ cần cùng `name`.
  - `sys.ask_missing_info`: khớp khi `tool_name` bằng nhau và `set(params)` bằng nhau.
  - `precision = TP/|pred|`, `recall = TP/|gold|`, `F1 = 2PR/(P+R)`; mẫu cả hai bên đều rỗng ⇒ F1 = 1.0. **Macro-average theo mẫu.**
- **Hash match:** `env.get_state_hash() == gold_hash` (từ `cache/gold_hash.json`).
- **Ask accuracy:** % mẫu ask có `tool_name` đúng **và** `set(params)` đúng.
- Báo cáo theo nhóm `act/ask/refuse`, theo app, và theo số lệnh đọc thừa (đọc dự đoán không có trong gold).

### 9.2 Taxonomy lỗi (mỗi mẫu sai gán **một** nhãn, theo thứ tự ưu tiên)
`exception` (debug có lỗi) → `scope_false_refuse` (pred rỗng, gold không rỗng) → `scope_missed_refuse` (gold rỗng, pred không rỗng) → `ask_vs_act` (pred có ask, gold không) → `act_vs_ask` (gold có ask, pred không) → `gate_dropped_valid` (`debug.gate_notes` cho thấy gate bỏ một call trùng một call gold) → `wrong_tool` (multiset tên khác nhau) → `wrong_id` (tham số `x-ref` khác) → `wrong_arg_entity` (tham số fuzzy/chuỗi khác) → `wrong_arg_number` (tham số số khác) → `wrong_arg_time` (tham số thời gian khác) → `wrong_arg_other`.

### 9.3 `eval/run.py` và `eval/metrics.py`
```
python eval/run.py --split train --ids <file> --asr gold|api|local --out runs/<tên>
                   [--set KEY=VALUE ...] [--workers 1] [--limit N] [--tune-scope] [--debug]
```
- `--set KEY=VALUE`: ghi đè một giá trị trong `config` cho lần chạy này (ép kiểu theo giá trị mặc định); ghi các giá trị đã ghi đè vào `runs/<tên>/overrides.json`. Dùng cho ablation.
- Mỗi mẫu: tạo `ToolEnv`, chạy `Agent.run`, lưu `tool_calls`, `state_hash`, so với gold.
- Xuất trong `runs/<tên>/`: `metrics.json` (mục 9.1), `per_sample.jsonl`, `errors.json` (đếm theo taxonomy), `submission.jsonl`, `overrides.json`.
- Mỗi process chỉ chạy một split (R7).

**Test (`tests/test_metrics.py`):** F1 với multiset trùng tên khác args; mẫu rỗng cả hai bên ⇒ 1.0; ask khớp theo tập params không phụ thuộc thứ tự; fuzzy token-F1.

**Test (`tests/test_executor.py`, dùng `FakeEnv` và `FakeLLM` có kịch bản):**
1. Lượt 1: LLM gọi `contacts.search`; lượt 2: gọi `banking.transfer` với `contact_id` vừa đọc ⇒ **cả hai được thực thi, không bị xóa**.
2. Lượt 1: LLM gọi `banking.transfer` với ID bịa khi `contacts` chưa đọc ⇒ call bị hoãn, `nudges_used==1`, lượt 2 LLM đọc rồi ghi đúng.
3. Write rồi ask ở cuối: thứ tự `tool_calls` = [write, ask].
4. Im lặng ở lượt 1 ⇒ nhắc một lần; vẫn im ⇒ `tool_calls == []`.
5. `MAX_TURNS` chặn vòng lặp vô hạn.
6. Lệnh ghi lặp y hệt ở lượt ≥ 2 bị bỏ, trừ khi transcript có "thêm".

---

## 10. Quy trình ablation

Mọi quyết định bật/tắt cờ dựa trên `dev300_ids.txt` (ablation) rồi xác nhận **một lần** trên `heldout_ids.txt`.

| Thí nghiệm | Lệnh (`--asr gold` trước, rồi `--asr <đã chọn>`) |
|---|---|
| Cơ sở | không `--set` |
| Prefetch | `--set PREFETCH_MODE=deps`, `--set PREFETCH_MODE=all` |
| Autofill ID | `--set ENABLE_AUTOFILL_REF=False` |
| Hoãn write chưa xác minh | `--set DEFER_UNVERIFIED_REF_WRITES=False` |
| XREF | `--set XREF_MODE=lenient` |
| Few-shot | `--set ENABLE_FEWSHOT=True` |
| Chính sách | `--set ENABLE_POLICY_RULES=True` |
| Ghi đè số/giờ | `--set ENABLE_OVERRIDE=True` |
| Hotwords ASR | `--set ENABLE_HOTWORD_REASR=True` (chỉ `local`) |
| Hỏi khi mơ hồ | `--set ENABLE_AMBIG_ASK=True` |
| Thứ tự `ask` | `--set ASK_AFTER_PARTIAL=False` |

**Quy tắc giữ cờ:** giữ khi F1-call (fuzzy-aware) tăng ≥ 0.5 điểm phần trăm **và** hash-match không giảm trên `dev300`; xác nhận trên `heldout`. Ghi mọi kết quả vào `reports/ablation.md` (bảng: thí nghiệm, F1-call, hash, ask accuracy, số mẫu lỗi theo taxonomy). Cờ không đạt thì để mặc định.

---

## 11. Lộ trình và nghiệm thu

| Mốc | Việc | Done khi (và lệnh nghiệm thu) |
|---|---|---|
| **M0** | Mục 8.0 | `reports/inspect.json`, `history_format.md`, `zaic_scoring.md`, `policy.json`, `ask_analysis.json`, `ask_unexplained.json`, `refuse_analysis.json`, `ref_sources.json`, `policy_rules.json`, `open_questions.md` tồn tại; `cache/gold_hash.json` đủ 1545 mẫu; `tune/heldout/dev300_ids.txt` tồn tại; kiểm tra `ToolEnv` lần hai không rò trạng thái đạt; **kết quả `check_ref_alignment.py` đã ghi** và `XREF_MODE` đã chốt; hằng số `history.py` đã đối chiếu |
| **M1** | Mục 3 (M1) | `pytest tests/ -q` xanh (catalog, state_store, vi_norm văn bản, resolver, gate, executor, metrics); `python eval/run.py --split train --ids dev300_ids.txt --asr gold --out runs/m1_gold` cho `metrics.json` có F1-call và hash; `submission.jsonl` mẫu đúng format. **Đây là trần của harness với transcript vàng** |
| **M2** | Số/giờ; `asr.py`; `asr_eval.py` | **100% bảng test 8.11 pass**; có `reports/asr_compare.md` (WER, lỗi thực thể, phân loại lỗi cho ≥ 2 ứng viên); chốt `ASR_MODE` và model |
| **M3** | `scope.py`, `build_hints` đủ số/giờ, nối ASR thật, `retrieval.py`, `policy_text.py` | `tests/test_scope.py` xanh; `reports/scope_tune.json`; chạy `--asr <đã chọn>` trên `heldout`: **mọi mẫu refuse có `tool_calls == []` khi scope đúng**; có số so sánh `gold` vs thật |
| **M4** | Ablation mục 10 | `reports/ablation.md` đầy đủ; `config.py` đã chốt các cờ |
| **M5** | Backend local; che/đổi tên tool; thời gian | Chạy được `dev300` với Qwen3-4B cục bộ + ASR cục bộ; ghi chênh lệch so với backend API; đổi tên tool trong catalog dev (bản sao, **không sửa gói gốc**) và đo độ sụt điểm; đo thời gian 1 split; `reports/final_config.md` |
| **M6** | Chạy `public_test` | `submission.jsonl` đúng **634 dòng**, JSON hợp lệ, `state_hash` không rỗng; lệnh validate trong `reports/zaic_scoring.md` (hoặc `python -m zaic_tools --split public_test --root <DATA_ROOT> --validate submission.jsonl`) pass |
| **M7** | Mục 8.17 | `infer.py` chạy được không cần mạng với backend local |

**Git:** `git init`; mỗi mốc một commit `M<n>: <mô tả>`.

---

## 12. Danh sách KHÔNG làm

- Không sửa `train+public_test/**`.
- Không đọc `state.json` trong code agent (chỉ `scripts/` replay gold bằng `ToolEnv`).
- Không hard-code tên app/tool/`x-ref`/collection cụ thể ở bất cứ module nào trong `lifemate/`.
- Không fine-tune hay train lại mô hình.
- Không thêm tính năng ngoài danh sách (multi-agent, memory, web search, sinh lời đáp cho người dùng).
- Không gọi thêm tool đọc vô nghĩa để "tối ưu hash".
- Không dùng `label` khi chạy `public_test` (không có), không đoán nhãn từ `history`.
- Không dùng `heldout` để rút luật hoặc chọn cờ.
- Không commit key API, không in key ra log.
- Không chạy full 1545 mẫu ở mỗi lần thử (dùng `dev300`), trừ một lần xác nhận cuối M3 và một lần cuối M5.
- Không nạp hai split trong cùng một process.

---

## 13. Rủi ro và xử lý

| Rủi ro | Dấu hiệu | Xử lý |
|---|---|---|
| Luật không cho gọi API lúc chấm (R0) | `reports/open_questions.md` ghi chưa xác nhận | Làm M5 sớm (ngay sau M1 nếu có thể), so sánh API vs local để đo mức chênh |
| Server không parse tool call | `message.tool_calls` luôn rỗng | Nhánh `parse_tool_calls_text`; kiểm tra cờ server |
| STT chỉ trả 1 transcript | `debug.asr_nbest == "single"` | Chấp nhận; chuyển `local` để có n-best thật |
| Tên khóa kết quả ≠ tên collection của `x-ref` | `check_ref_alignment` < 95% | `XREF_MODE="lenient"`; ghi nguyên nhân |
| Prefetch làm tụt F1-call | F1 giảm khi bật | Giữ `PREFETCH_MODE="off"` |
| Hoãn write làm tăng số lượt/độ trễ | `nudges_used` cao | Đo ở ablation; tắt `DEFER_UNVERIFIED_REF_WRITES` nếu không có lợi |
| Model bịa ID | `wrong_id` nhiều | `fix_refs`, hoãn write, few-shot có ID che |
| LLM im lặng ở yêu cầu hợp lệ | `silent` nhiều trong `gate_notes` | `SILENT_RETRY`; xem lại prompt |
| Few-shot làm model chép ID | `wrong_id` tăng khi bật | Kiểm tra ID đã được che; tắt cờ nếu cần |
| `ToolEnv` không thread-safe | kết quả lệch giữa `workers=1` và `4` | Chạy `workers=1` |
| API lỗi/timeout | mẫu trống | `apiclient` retry + trả `None`; `infer.py` bọc `try/except`; `Deadline` |
| Prompt quá dài | chậm/tốn token | `trim_snapshot`, `FEWSHOT_K` nhỏ, `PREFETCH_MODE="off"` |

---

## 14. Việc còn mở và mặc định khi chưa có câu trả lời

| # | Câu hỏi | Mặc định |
|---|---|---|
| O1 | Công thức F1-call của BTC | Đọc `zaic_tools` (8.0.2); nếu không có, dùng mục 9.1 và báo cả strict/fuzzy-aware/soft, ưu tiên fuzzy-aware |
| O2 | LLM endpoint có tool-calling? | Code cả hai nhánh (structured trước, text-JSON sau) |
| O3 | STT có `temperature>0` (n-best)? | Giả định không ⇒ 1 transcript |
| O4 | STT có trường `prompt` (hotwords)? | Giả định không ⇒ `ENABLE_HOTWORD_REASR` chỉ áp dụng với `local` |
| O5 | Rate limit API? | `--workers 1`; nếu muốn song song, kiểm tra như mục 8.16 |
| O6 | Định dạng `history` (vai trò, có lượt trợ lý, có audio) | Đọc `reports/history_format.md`; nếu thiếu thì chỉ dùng các lượt user có `text`/`audio` |
| O7 | 47 mẫu ask chưa giải thích | Phân loại ở M0; chưa có luật thì không xử lý riêng (để LLM/gate xử lý theo `required`/`one_of`) |
| O8 | Đọc thừa/lệnh lỗi có bị trừ điểm riêng ngoài F1? | Giả định chỉ qua F1; vẫn giảm đọc thừa |
| O9 | Giới hạn thời gian/phần cứng khi chấm | Chưa biết; đo ở M5 và ghi vào `reports/final_config.md` |
| O10 | Luật mô hình < 6B tính thế nào (ASR + LLM cộng lại hay riêng lẻ) | Giả định cộng lại; chọn cấu hình tổng < 6B |