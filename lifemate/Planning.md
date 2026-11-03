# Kế hoạch thực thi LifeMate

Tài liệu này đủ chi tiết để một LLM implement mà không cần tự suy luận thiết kế. Làm theo thứ tự mục 6. Mỗi module có: chữ ký hàm, thuật toán từng bước, test bắt buộc.

---

## 0. Kiến trúc bên trong và lý do của từng khối

Đừng bỏ khối nào mà chưa hiểu nó giải quyết ràng buộc nào của đề.

| Ràng buộc từ đề | Hệ quả thiết kế | Khối thực thi |
|---|---|---|
| Mọi lời gọi `env.call` đều bị ghi log và nộp. Ngoài phạm vi phải trả `[]` | **Không gọi tool nào, kể cả tool đọc, trước khi biết yêu cầu nằm trong phạm vi** | `scope.py` chạy trước `prefetch.py` |
| Cấm đọc `state.json`. ID thiết bị, danh bạ chỉ có qua tool đọc | Phải đọc trước (prefetch) rồi mới lập kế hoạch | `prefetch.py`, `lexicon.py` |
| Chấm bằng state hash **và/hoặc** F1 trên call — công thức chưa chốt (mục 1.1). Sai một tên, số tiền, giờ là sai | Sửa lỗi nghe bằng từ vựng thật của môi trường; parser số/giờ bằng luật | `asr.py`, `resolver.py`, `vi_norm.py` |
| Mỗi mẫu chỉ một `ToolEnv`, lệnh ghi không hoàn tác | Planner sinh kế hoạch → code kiểm tra → mới thực thi. Không có "thử rồi sửa" trên lệnh ghi | `planner.py`, `gate.py`, `executor.py` |
| Mô hình 4B không fine-tune dễ bịa ID, thiếu tham số, hỏi/làm sai | Mọi kiểm tra tính hợp lệ lấy từ catalog (`required`, `enum`, `x-ref`, `x-one-of`) và dữ liệu đã đọc, **không** dựa vào việc mô hình tự khai | `gate.py` |
| Test có thể có tool/app lạ | Không hard-code tên tool/app. Mọi thứ đi qua catalog | `catalog.py` |
| Nhãn hỏi/làm/từ chối chỉ biết qua train | Pha 0 khảo sát nhãn thật trước khi cố định luật | `scripts/analyze_train.py` |

### Luồng dữ liệu (một mẫu)

```
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

ASR chạy **trước** prefetch để mẫu ngoài phạm vi không để lại log đọc nào. Hotwords lấy từ snapshot chỉ là bước tùy chọn (mục 5.5).

---

## 1. Quy ước chung

- Python ≥ 3.10 (dùng **3.12** trong venv: `torch`/`transformers` chưa chắc có wheel cho 3.15). Thư viện: `numpy`, `soundfile`, `torch`, `transformers`. Không dùng mạng khi chạy inference.
- **Cấm** đọc, copy, parse bất cứ file nào dưới `<split>_environment/`. Dữ liệu app chỉ lấy qua `env.call`.
- Mỗi mẫu tạo `ToolEnv` **đúng một lần**, trong `infer()`. Truyền `env` xuống các hàm khác, không tạo lại.
- Mọi lời gọi `env.call` phải đi qua `executor.safe_call()` hoặc `prefetch`, không có lời gọi nào ngoài tầm kiểm soát.
- Mọi hàm xử lý dữ liệu từ JSON/LLM phải chịu được khóa thiếu và kiểu sai (dùng `.get`, `isinstance`). Một mẫu lỗi không được làm sập cả lượt chạy.
- Trong prompt cho LLM **giữ nguyên dấu tiếng Việt**; bản bỏ dấu (`strip_accents`) chỉ dùng để so khớp tên. `parse_numbers`/`parse_times` chạy trên **text gốc** (không dùng `normalize()` của 5.4a vì nó bỏ dấu câu và làm méo `500.000` / `1,5 triệu`).
- Mỗi mẫu ghi file debug `debug/<id>.json` gồm: `hyps`, `scope`, `snapshot_keys`, `hints`, `planner_raw`, `gate_notes`, `executed`. Bắt buộc, vì phân tích lỗi cần nó.
- Seed cố định; LLM dùng greedy (`temperature=0`).

### 1.1 Metric chấm: chưa chốt — mọi quyết định liên quan phải đo cả hai chỉ số

Gói dữ liệu nói BTC "replay `tool_calls` ... rồi so state với đáp án và **tính F1 trên call**" (`<split>/zaic_tools/README.md`), còn bản plan này giả định chấm bằng `state_hash`. Hai cách tối ưu hành vi khác nhau:

| | `state_hash` | F1 trên call |
|---|---|---|
| Call đọc thừa (`env.call` luôn ghi log, kể cả call bị từ chối) | vô hại | mất precision |
| Sai nội dung text (`content`, `body`, `title`, `note`… bị `canon()` loại khỏi hash) | không lộ | lộ |
| Sai tên / số / giờ / ID | lộ | lộ |

Quy tắc bắt buộc cho tới khi chốt được công thức:

1. `eval/metrics.py` phải xuất **cả hai**: F1 call (macro trên mẫu; khớp theo `(name, arguments)`; thêm biến thể chỉ khớp `name` vì chưa biết BTC khớp mềm hay cứng) **và** tỉ lệ khớp `state_hash` (kèm khớp state từng app). Không được chỉ báo cáo hash.
2. Mọi thao tác liên quan tới read tool phải là **knob** (`PREFETCH_MAX_READS`, `BLOCK_READ_ALREADY_PREFETCHED`), không hard-code theo hướng nào.
3. Ưu tiên theo mẫu, không theo số lượng call: một mẫu `ask` chỉ có **đúng 1 call** `sys.ask_missing_info` nên sai `tool_name`/`params` là mất trọn điểm mẫu đó; `refuse` chỉ ~7% dữ liệu nên false-refuse (chặn nhầm một mẫu `act`) tệ hơn refuse thiếu.

---

## 2. Cấu trúc repo

```
lifemate/
  config.py
  catalog.py   prefetch.py   lexicon.py
  vi_norm.py   resolver.py   asr.py     scope.py
  llm.py       prompt.py     planner.py gate.py   executor.py
  retrieval.py             # có điều kiện (mục 5.15)
  agent.py     infer.py
scripts/
  inspect_data.py   analyze_train.py   gold_hash.py   split.py
eval/
  run.py   metrics.py   asr_eval.py
tests/
  test_vi_norm.py   test_catalog.py   test_gate.py   test_resolver.py
```

---

## 3. Pha 0: khảo sát dữ liệu (làm đầu tiên, trước mọi code khác)

Mục đích: dữ liệu thật quyết định nhiều chi tiết (định dạng `history`, `x-one-of`, kết quả của `env.call`, hành vi nhãn hỏi/từ chối). Không đoán các thứ này.

### `scripts/inspect_data.py`

In ra và lưu `reports/inspect.json`:

1. Khóa của một record trong `train.jsonl`; cấu trúc `context.installed_apps` (value là danh sách tên tool hay danh sách schema); cấu trúc `history` (khóa của từng turn, turn nào có đường dẫn audio).
2. Với 5 mẫu: tạo `ToolEnv`, gọi từng tool `kind=read` không có tham số bắt buộc, in nguyên kết quả (`json.dumps(indent=2, ensure_ascii=False)`, cắt 1500 ký tự). Mục đích: biết khóa nào chứa dữ liệu (`result`, `data`, ...).
3. Vị trí và dạng của `x-one-of`, `x-ref`, `x-match` trong catalog (ở mức `parameters` hay từng `property`; list-of-list hay list-of-string).
4. Tool `sys.ask_missing_info` có trong catalog không, schema ra sao.

### `scripts/analyze_train.py`

In ra `reports/policy.json` và bảng tóm tắt:

1. Phân loại mỗi mẫu train: `refuse` (gold `tool_calls == []`), `ask` (có `sys.ask_missing_info`), `act` (còn lại). Đếm từng loại.
2. Với `refuse`: gold có đúng `[]` không (không có lệnh đọc nào).
3. Với `ask`: (a) phân phối `tool_name` và `params`; (b) trước `ask` có tool nào khác không; (c) khi tool có `x-one-of`, `params` liệt kê cả hai nhóm hay một nhóm; (d) có tool đọc trước `ask` không.
4. Với `act`: số lệnh ghi mỗi mẫu; tỉ lệ mẫu có tool đọc trong gold; tỉ lệ mẫu có > 1 lệnh ghi.
5. **Kiểm tra giả định đọc không đổi hash:** với 30 mẫu `act` có tool đọc trong gold, replay hai lần (có/không có lệnh đọc), so hash.
6. Từ `audio_text` + gold: trích thực thể (tên liên hệ, số, giờ) để làm bộ đo lỗi thực thể cho ASR (mục 5.14).

### `scripts/gold_hash.py`

Với mỗi mẫu train: tạo `ToolEnv` mới, replay `label.tool_calls` (bỏ `sys.ask_missing_info`), lưu `cache/gold_hash.json`. Kiểm tra: tạo `ToolEnv` thứ hai cho cùng id phải ra hash ban đầu (chứng tỏ không rò trạng thái giữa các lần tạo). Nếu không, dừng và báo cáo.

### `scripts/split.py`

Tạo `tune_ids.txt` (75%) và `heldout_ids.txt` (25%) bằng seed cố định. **Không** dùng held-out để rút luật hay chọn few-shot.

**Cách dùng kết quả:** điền vào `config.py` các giá trị đánh dấu `[M0]`.

---

## 4. `config.py` và hợp đồng dữ liệu

```python
# config.py
SPLIT_DEFAULT = "public_test"
ASR_MODEL = "vinai/PhoWhisper-medium"      # [M2] chọn lại theo số đo
LLM_MODEL = "Qwen/Qwen3-4B"
ASR_BEAMS, ASR_NBEST = 5, 3
ENTITY_MATCH_THRESHOLD = 0.82
SCOPE_LEX_THRESHOLD = 1.0                  # [M3] tune bằng eval/run.py --tune-scope
PREFETCH_MODE = "after_scope"              # [M0] "after_scope" | "always"
PREFETCH_MAX_READS = 2                     # [M0] số read tool tối đa gọi trước (0 = không prefetch); xem mục 1.1
BLOCK_READ_ALREADY_PREFETCHED = True        # [M0] gate có bỏ read tool đã prefetch không; tắt nếu metric tính F1-call
ASK_AFTER_PARTIAL = True                   # [M0] làm các bước đủ thông tin rồi mới hỏi?
ONE_OF_ASK_MODE = "all"                    # [M0] "all" | "first_group"
ENABLE_OVERRIDE = False                    # [M4] ghi đè số/giờ bằng parser
ENABLE_FEWSHOT = False                     # [M4]
ENABLE_HOTWORD_REASR = False               # [M4]
ENABLE_AMBIG_ASK = False                   # [M4]
MAX_TURNS, MAX_WRITES = 6, 8
SNAPSHOT_MAX_CHARS = 6000
REPEAT_MARKERS = ("thêm", "nữa", "lại", "tiếp")
```

```python
from dataclasses import dataclass
from typing import Any

@dataclass
class Tool:
    name: str; app: str; kind: str; description: str
    parameters: dict          # JSON Schema gốc
    required: list[str]
    props: dict[str, dict]
    one_of: list[list[str]]   # đã chuẩn hóa: list các nhóm

@dataclass
class Hyp:    text: str; score: float
@dataclass
class Hint:   kind: str; span: str; value: Any; conf: float; extra: dict   # kind: entity|number|time|digits
@dataclass
class Entity: id: str; collection: str; fields: dict[str, str]; names: list[str]; source_tool: str
@dataclass
class Call:   name: str; args: dict
@dataclass
class Ask:    tool_name: str; params: list[str]
```

---

## 5. Thực thi từng module (theo thứ tự xây)

### 5.1 `catalog.py`

```python
class Catalog:
    def __init__(self, path: str): ...
    def tools_for(self, installed_apps: dict) -> dict[str, Tool]: ...
```

Thuật toán `tools_for`:

1. `app_ids = set(installed_apps.keys())`.
2. Nếu `installed_apps[app]` là dict có khóa `"tools"` và danh sách không rỗng: tên tool cho phép = các phần tử (chuỗi, hoặc dict có `"name"`). Ngược lại cho phép mọi tool của app trong catalog.
3. Trả về `{name: Tool}` cho các tool catalog có `app in app_ids` và tên được phép. Thêm `sys.ask_missing_info`: lấy từ catalog nếu có, nếu không thì tạo với
   `parameters = {"type":"object","properties":{"tool_name":{"type":"string"},"params":{"type":"array","items":{"type":"string"}}},"required":["tool_name","params"]}`, `kind="meta"`.
4. `one_of`: tìm `parameters.get("x-one-of")`, rồi `x-one-of` ở từng property. Chuẩn hóa: phần tử là chuỗi thì thành nhóm `[chuỗi]`; là list thì giữ làm nhóm.

Hàm `to_llm_tools(tools) -> list[dict]`: mỗi tool thành `{"type":"function","function":{"name","description","parameters"}}`. Trước khi đưa vào: sao chép `parameters`, **xóa mọi khóa bắt đầu bằng `x-`**, và nối vào `description` của property tương ứng: nếu có `x-ref` thì thêm `" (ID phải lấy từ dữ liệu ứng dụng đã đọc)"`. Nếu tool có `one_of`, nối vào mô tả tool: `" Cần ít nhất một trong các nhóm: ..."`.

Hàm `resolve_tool_name(name, tools) -> str | None`: khớp chính xác → khớp sau khi thay `__` hoặc `/` bằng `.` → khớp chữ thường bỏ ký tự không phải chữ/số → `difflib.get_close_matches(cutoff=0.9)` → `None`.

**Test (`tests/test_catalog.py`):** catalog nhỏ giả lập; `tools_for` lọc đúng app; `x-one-of` chuẩn hóa đúng cả hai dạng; `to_llm_tools` không còn khóa `x-`.

### 5.2 `prefetch.py`

```python
def select_prefetch_tools(tools: dict[str, Tool], max_reads: int = PREFETCH_MAX_READS) -> list[Tool]:
    # kind == "read" and not required and not one_of; sắp theo tên; cắt còn max_reads
def run_prefetch(env, tools) -> dict[str, dict]:
    # với mỗi tool: res = env.call(t.name, {}); nếu res.get("ok") thì snapshot[t.name] = res
```

Không gọi tool đọc có tham số bắt buộc ở đây (B2 gọi sau khi đã biết ID). Chỉ gọi hàm này sau khi `scope` cho phép (trừ khi `PREFETCH_MODE == "always"`).

Lưu ý: **mọi lời gọi `env.call` đều nằm trong `tool_calls` được nộp** (`zaic_tools/executor.py` ghi log trước cả khi call bị từ chối). Mỗi mẫu trung bình có ~10 read tool không bắt buộc tham số trong khi gold chỉ có ~1 read call ⇒ prefetch toàn bộ tụt precision nếu metric tính F1-call. Vì vậy `PREFETCH_MAX_READS` mặc định nhỏ và phải ablation (mục 5.15).

### 5.3 `lexicon.py`

```python
def build_entities(snapshot: dict) -> list[Entity]
def collect_ids(snapshot: dict) -> dict[str, set[str]]   # collection_key -> tập id
def trim_snapshot(snapshot, transcript, max_chars) -> str   # chuỗi JSON gọn cho prompt
```

`build_entities`: duyệt đệ quy mọi JSON trong snapshot, truyền `parent_key`. Khi gặp list, với mỗi phần tử là dict có `"id"` (chuỗi hoặc số, ép sang `str`): tạo `Entity` với `collection = parent_key`, `fields` = mọi giá trị chuỗi ở cấp một của dict (trừ `id`), `names` = các giá trị chuỗi độ dài 1..80, không phải chuỗi ISO datetime, không phải chuỗi toàn chữ số dài > 6. Bỏ qua phần tử không có `id`. Vẫn đệ quy vào các value là dict/list khác.

`collect_ids`: cùng cách duyệt, gom `id` theo `collection_key`.

`trim_snapshot`: nếu `json.dumps(snapshot, ensure_ascii=False)` ≤ `max_chars` thì trả nguyên. Nếu quá: với mỗi list có > 15 phần tử dict, giữ (a) phần tử có ít nhất một giá trị chuỗi chia sẻ token (bỏ dấu, chữ thường) với transcript, (b) 10 phần tử đầu; thêm phần tử cuối `{"_note": "đã lược N mục"}`. Lặp tới khi vừa `max_chars`; nếu vẫn quá thì cắt theo tool, ưu tiên giữ app có tên xuất hiện trong transcript.

**Test:** snapshot ví dụ (`contacts`, `devices`) → entities đúng id và collection; `collect_ids` đúng; `trim_snapshot` giữ phần tử khớp transcript.

### 5.4 `vi_norm.py`

Khối nhiều test nhất. Viết xong và qua hết bảng test dưới đây rồi mới làm tiếp.

#### (a) Văn bản

```python
def normalize(text) -> str          # NFC, chữ thường, bỏ dấu câu trừ chữ/số và khoảng trắng; GIỮ dấu tiếng Việt
def strip_accents(s) -> str         # NFD, bỏ combining marks, đ->d, chữ thường
def phonetic_key(token) -> str
def token_sim(a, b) -> float        # max(SequenceMatcher(strip(a),strip(b)).ratio(), 0.95 nếu phonetic_key bằng nhau)
```

`normalize()` **giữ dấu tiếng Việt** và chỉ dùng để đưa vào prompt / so khớp; bản bỏ dấu là `strip_accents`. Không parse số từ bản đã bỏ dấu câu (mất `,`/`.` trong `500.000`, `1,5 triệu`).

`phonetic_key`: `t = strip_accents(token)`; áp theo thứ tự: `re.sub(r'^(gi|d|r)','d',t)`, `re.sub(r'^(tr|ch)','c',t)`, `re.sub(r'^x','s',t)`, `re.sub(r'^l','n',t)`, `re.sub(r'(ng|nh)$','n',t)`, `re.sub(r'(ch|c)$','t',t)`.

#### (b) Số

```python
def parse_numbers(text: str) -> list[Hint]   # kind="number" hoặc "digits"
```

Thuật toán:

1. Chuẩn hóa nhẹ (chữ thường, NFC, giữ `,` `.` `:` khi nằm giữa chữ số), tách token. **Không** dùng `normalize()` của (a).
2. Từ điển: `không/0, một/1, mốt/1, hai/2, ba/3, bốn/4, tư/4, năm/5, lăm/5, sáu/6, bảy/7, bẩy/7, tám/8, chín/9, mười/10`; nhân: `mươi/chục` (×10), `trăm` (100); đơn vị: `nghìn/ngàn` (1e3), `triệu` (1e6), `tỷ/tỉ` (1e9); đặc biệt: `lẻ/linh` (giữ phần trăm, xoá phần chục: `cur = (cur // 10) * 10`), `rưỡi`.
3. Tìm các đoạn (span) liên tiếp gồm token số/đơn vị/chữ số. Với mỗi đoạn dùng bộ tích lũy `total, cur, pending, last_unit`:
   - Token chữ số (từ hoặc dạng số như `500`): `pending = giá trị`.
   - `trăm`: `cur += (pending or 1) * 100`; `pending = None`.
   - `mười`: `cur += 10`.
   - `mươi/chục`: `cur += (pending or 1) * 10`; `pending = None`.
   - Đơn vị (`nghìn/triệu/tỷ`): `cur += pending or 0`; nếu `cur == 0` thì `cur = 1`; `total += cur * unit`; `last_unit = unit`; `cur = 0; pending = None`.
   - `rưỡi`: nếu có `last_unit`: `total += last_unit / 2`.
   - Kết thúc đoạn: `cur += pending or 0`. Phần dư không có đơn vị sau `last_unit`: nếu `cur < 10`: `total += cur * last_unit / 10`; nếu `cur < 1000` và `cur % 100 == 0`: `total += cur * last_unit / 1000`; ngược lại `total += cur`.
4. Dạng chữ số kèm đơn vị: regex `(\d+(?:[.,]\d+)?)\s*(k|ka|nghìn|ngàn|tr|triệu|tỷ|đ|đồng|vnd)\b`. Dấu phẩy là thập phân nếu theo sau 1-2 chữ số rồi tới đơn vị; chuỗi `\d{1,3}(\.\d{3})+` là phân tách hàng nghìn (xóa dấu chấm). **Ưu tiên:** span nào regex này khớp thì bỏ kết quả của đường chữ (bước 3) trên span đó, tránh `1,5 triệu` ra 5.000.000.
5. **Chuỗi chữ số rời** (số điện thoại): nếu có ≥ 6 token chữ số đơn liên tiếp (`không..chín` hoặc `0-9`), phát `Hint(kind="digits", value="chuỗi chữ số")`, không phát `number`.
6. `conf = 0.95` nếu đoạn có từ đơn vị tiền/đơn vị lớn (`nghìn, triệu, tỷ, k, đồng, ...`); `0.8` nếu chỉ là số trần.

#### (c) Giờ/ngày

```python
def parse_times(text: str, now: datetime) -> list[Hint]   # kind="time", value=ISO, extra={"kind":..., "alternatives":[...]}
```

Định dạng đầu ra: `YYYY-MM-DDTHH:MM:SS+07:00` (offset lấy từ `now.tzinfo`, luôn có `:00` giây). Nếu chỉ có ngày: `YYYY-MM-DD`.

Quy tắc (áp dụng theo thứ tự):

1. **Khoảng thời gian:** `sau X (phút|tiếng|giờ|ngày)` hoặc `X (phút|tiếng|giờ|ngày) nữa`, `nửa tiếng`, `X tiếng rưỡi`; X dùng `parse_numbers`. Kết quả `now + delta`, làm tròn về phút, `conf = 0.9`.
2. **Ngày:** `hôm nay|nay` (+0), `ngày mai|mai` (+1), `ngày mốt|ngày kia|mốt` (+2), `hôm qua` (-1); `thứ hai..thứ bảy|chủ nhật` ↔ `weekday` 0..6 (`thứ tư` = 2, `thứ năm` = 3, `thứ sáu` = 4); `ngày D`, `ngày D tháng M`, `D/M`, `D tháng M`.
   - Thứ trong tuần: có `tuần sau|tuần tới` → `thứ_hai_tuần_sau + wd` với `thứ_hai_tuần_sau = today + (7 - today.weekday())`; có `tuần này` → `thứ_hai_tuần_này + wd`; không có → `delta = (wd - today.weekday()) % 7`, nếu `delta == 0` thì `7` (trừ khi có `hôm nay`).
   - `ngày D` không tháng: tháng này nếu `D ≥ today.day`, ngược lại tháng sau.
3. **Giờ trong ngày:** các mẫu `X giờ`, `X giờ rưỡi`, `X giờ Y (phút)`, `X giờ kém Y`, `Xh`, `XhYY`, `X:YY` (X, Y là số hoặc chữ). `kém Y`: `(X-1):(60-Y)`; `rưỡi` = :30.
   - Từ chỉ buổi trong cửa sổ 3 token quanh biểu thức giờ: `sáng` → giữ `h`; `trưa` → `h` nếu `h ≥ 10` ngược lại `h+12`; `chiều`, `tối` → `h+12` nếu `h < 12`; `đêm` → `h+12` nếu `6 ≤ h < 12`, `0` nếu `h == 12`, ngược lại `h`.
   - Không có từ chỉ buổi và `h ≤ 12`: tạo hai ứng viên `h` và `h+12`. Ứng viên chính: ngày không phải hôm nay → `h+12` nếu `1 ≤ h ≤ 6`, `h` nếu `7 ≤ h ≤ 11`, `12` nếu `h == 12`; ngày là hôm nay → ứng viên sớm nhất lớn hơn `now`. `conf = 0.6`, ứng viên còn lại để trong `extra["alternatives"]`. `h ≥ 13` hoặc `h == 0`: `conf = 0.9`, không mơ hồ.
4. **Kết hợp:** có giờ nhưng không có ngày → hôm nay; nếu kết quả ≤ `now` → +1 ngày. Có ngày không có giờ → phát `Hint(kind="time")` với `value` chỉ có ngày.

#### Bảng test (`tests/test_vi_norm.py`), `now = 2026-11-16T17:00:00+07:00` (thứ Hai)

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
| "nhắc tôi họp lúc ba giờ chiều mai" | 2026-11-17T15:00:00+07:00 |
| "năm giờ rưỡi sáng mai" | 2026-11-17T05:30:00+07:00 |
| "họp thứ sáu tuần sau lúc 9 giờ sáng" | 2026-11-27T09:00:00+07:00 |
| "thứ sáu lúc 8 giờ tối" | 2026-11-20T20:00:00+07:00 |
| "hai tiếng nữa" | 2026-11-16T19:00:00+07:00 |
| "ba mươi phút nữa" | 2026-11-16T17:30:00+07:00 |
| "tám giờ tối nay" | 2026-11-16T20:00:00+07:00 |
| "bảy giờ kém mười lăm sáng mai" | 2026-11-17T06:45:00+07:00 |
| "mười lăm giờ" | 2026-11-17T15:00:00+07:00 (vì đã qua giờ hôm nay) |
| "ngày 20 tháng 12 lúc 10 giờ" | 2026-12-20T10:00:00+07:00, `conf` 0.6, alternatives có 22:00 |
| "ngày mốt" | "2026-11-18" |

### 5.5 `asr.py`

```python
class ASR:
    def __init__(self, model_name): ...    # nạp một lần, dùng cho mọi mẫu
    def transcribe(self, wav_path, hotwords: str | None = None) -> list[Hyp]
```

1. Đọc WAV bằng `soundfile`, ép mono float32, 16 kHz.
2. **Cắt lặng:** tính năng lượng RMS theo khung 20 ms; giữ từ khung đầu tiên đến khung cuối cùng có RMS > `0.02 * max_rms` (chừa đệm 150 ms mỗi đầu). Nếu cắt xong dưới 0.3 s thì giữ nguyên bản gốc.
3. Chạy mô hình kiến trúc Whisper (`WhisperForConditionalGeneration` + `WhisperProcessor`), `language="vi"`, `task="transcribe"`, `num_beams=ASR_BEAMS`, `num_return_sequences=ASR_NBEST`, `return_dict_in_generate=True`, `output_scores=True`. Điểm mỗi ứng viên = `sequences_scores`. Hotwords (nếu có): `ids = tokenizer(hotwords, add_special_tokens=False).input_ids` → `prompt_ids = processor.get_prompt_ids(ids)` (hàm này nhận **token ids**, không nhận chuỗi) rồi truyền vào `generate(prompt_ids=...)`; khi giải mã phải bỏ phần prompt khỏi văn bản.
4. **Kiểm tra suy biến** `is_degenerate(text, duration)`: rỗng; hoặc số token / thời lượng (giây) > 6; hoặc có n-gram (n = 1..3) lặp liên tiếp ≥ 4 lần. Ứng viên suy biến bị loại. Nếu mọi ứng viên suy biến thì chạy lại một lần không có hotwords; nếu vẫn suy biến thì trả `[Hyp("", -inf)]`.
5. Trả về danh sách sắp theo điểm giảm dần, `text` đã qua `normalize`.

`ENABLE_HOTWORD_REASR` (tùy chọn): sau khi có snapshot và scope là in-scope, gọi lại `transcribe` với hotwords = các tên trong `Entity.names` nối bằng `", "` (≤ 400 ký tự) cộng `user_profile`. Chỉ dùng kết quả mới nếu không suy biến.

**Hàm `transcribe_sample(item, asr, split_dir) -> (hyps_current, history_texts)`:** ASR audio hiện tại; với mỗi lượt user trong `history` có đường dẫn audio (xem `inspect_data.py` để biết khóa), chạy ASR top-1 để lấy văn bản. Cache **theo đường dẫn audio** (mỗi lượt history là một file riêng, không dùng chung key `id`) trong `cache/asr_<split>.json` khi chạy eval.

### 5.6 `scope.py`

```python
def in_scope(llm, hyps, tools, ctx) -> tuple[bool, dict]   # dict: debug (lex_score, llm_answer)
```

1. **Điểm từ vựng:** BM25 (tự cài, k1=1.5, b=0.75) giữa transcript top-1 (đã bỏ dấu) và "tài liệu" của mỗi tool = `app + name_vi + tên tool + mô tả` (đã bỏ dấu). `lex = max score`.
2. **LLM:** prompt ngắn (không có snapshot): danh sách `tool.name: mô tả` + câu `Yêu cầu: {transcript}`. Chỉ thị: "Trả lời đúng một từ. CO nếu có công cụ nào thực hiện được yêu cầu, hoặc yêu cầu thiếu thông tin nhưng thuộc phạm vi của công cụ. KHONG nếu không công cụ nào liên quan." `max_new_tokens=3`.
3. **Quyết định:** ngoài phạm vi chỉ khi `LLM == KHONG` **và** `lex < SCOPE_LEX_THRESHOLD`. Ngưỡng tối ưu trên train (`eval/run.py --tune-scope`: quét ngưỡng, chọn giá trị tối đa hóa độ chính xác `refuse` mà recall `act/ask` không dưới 99%).
4. Khi ngoài phạm vi: `agent` dừng, `tool_calls = env.get_tool_calls()` (rỗng), lấy `state_hash`.
5. Tối ưu tốc độ (không đổi hành vi): quy tắc 3 là "ngoài phạm vi **khi và chỉ khi** LLM==KHONG **và** lex < ngưỡng" ⇒ khi `lex >= SCOPE_LEX_THRESHOLD` thì kết luận in-scope và **không cần gọi LLM** (tiết kiệm ~1 lượt LLM/mẫu, ~2200 mẫu train+public). Vẫn phải kiểm tra recall trên held-out sau khi tối ưu này.

### 5.7 `resolver.py`

```python
def match_entities(text_tokens, entities, threshold) -> list[Hint]
def build_hints(hyps, entities, now) -> list[Hint]
def format_hints(hints) -> str
```

`match_entities`: với mỗi `Entity` và mỗi `name` của nó: tách token tên (bỏ dấu); trượt cửa sổ cùng độ dài trên token transcript; điểm = trung bình `token_sim` từng cặp. Chấp nhận nếu `≥ threshold`; tên đơn từ yêu cầu `≥ 0.9` và token không thuộc `STOPWORDS` (`cho, và, là, của, tôi, mình, em, anh, chị, bạn, một, các, những, trong, ở, đi, về, đến, lúc`). Trả `Hint(kind="entity", span=cửa sổ, value=entity.id, conf=điểm, extra={"collection":..., "name":...})`. Nếu nhiều entity cùng điểm cao cho cùng một span thì phát hết (gate dùng để phát hiện mơ hồ).

`build_hints`: chạy `match_entities` trên **từng** ứng viên n-best rồi gộp (giữ điểm cao nhất mỗi `(span, entity.id)`); `parse_numbers` và `parse_times` trên top-1. Với mỗi ứng viên top-2/3 mà `parse_numbers` cho giá trị khác top-1, ghi vào `extra["alt_values"]` của hint số tương ứng.

`format_hints`: mỗi dòng một hint, ví dụ:
```
TÊN "chị thu" ≈ Thư (id c_03, tin cậy 0.93)
SỐ "năm trăm nghìn" = 500000
GIỜ "ba giờ chiều mai" = 2026-11-17T15:00:00+07:00
```
Nếu mơ hồ thì thêm `hoặc <alt>`.

**Test (`tests/test_resolver.py`):** snapshot giả có contacts `Thư`, `Thu`, `Hương`; transcript "chuyển cho chị thư năm trăm nghìn" → hint entity trỏ đúng; lỗi dấu ("hương" ↔ "hướng") vẫn khớp.

### 5.8 `llm.py`

```python
class LLM:
    def __init__(self, model_name): ...       # nạp một lần
    def generate(self, messages, tools=None, max_new_tokens=512) -> str
def parse_tool_calls(text: str) -> list[Call]
def extract_text(text: str) -> str
```

- Dùng `tokenizer.apply_chat_template(messages, tools=tools, add_generation_prompt=True, enable_thinking=False)`; greedy.
- `parse_tool_calls`: `re.findall(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", text, re.S)`; mỗi cái `json.loads` trong `try/except` (lỗi → bỏ qua). Lấy `name` và `arguments` (nếu `arguments` là chuỗi thì `json.loads` tiếp). Trả `[]` nếu không tìm được.
- `extract_text`: phần văn bản ngoài các khối `<tool_call>`, dùng để phát hiện `KHONG_HO_TRO` hoặc `XONG`.

### 5.9 `prompt.py` và `planner.py`

**System prompt (cố định, tiếng Việt):**

```
Bạn là trợ lý điều khiển ứng dụng trên thiết bị bằng giọng nói. Người dùng nói tiếng Việt.
Nhiệm vụ: biến yêu cầu thành các lời gọi công cụ đúng.
Quy tắc:
1. Chỉ dùng các công cụ được cung cấp. Không bịa tên công cụ hay tham số.
2. Mọi ID (thiết bị, liên hệ, tài khoản...) phải lấy đúng từ "Dữ liệu ứng dụng". Không tự đặt ID.
3. Số tiền, giờ, ngày: ưu tiên dùng đúng giá trị trong mục "Gợi ý". Giờ dùng định dạng ISO có múi giờ.
4. Khi người dùng nói "nhà tôi", "chỗ tôi", "văn phòng" hãy dùng hồ sơ và vị trí hiện tại.
5. Nếu thiếu thông tin bắt buộc mà không thể suy ra từ yêu cầu, hồ sơ, vị trí hay dữ liệu ứng dụng: gọi sys.ask_missing_info với tool_name là công cụ định gọi và params là danh sách tên tham số còn thiếu. Không đoán.
6. Nếu không công cụ nào xử lý được yêu cầu: không gọi công cụ nào, chỉ trả lời KHONG_HO_TRO.
7. Không gọi lại công cụ đọc dữ liệu đã có. Chỉ gọi công cụ ghi khi chắc chắn.
8. Khi đã hoàn tất mọi việc người dùng yêu cầu, trả lời XONG và không gọi thêm công cụ.
```

**User message (mỗi mẫu):** các mục nối bằng dòng trống, đúng thứ tự:

```
Thời gian hiện tại: {current_time} ({timezone}); thứ {weekday_vi}
Vị trí hiện tại: {current_location}
Hồ sơ: {json user_profile}
Lịch sử: {các lượt trước: "Người dùng: <text>" ...}      # chỉ khi có
Yêu cầu: {hyps[0].text}
Cách nghe khác: {hyps[1].text} | {hyps[2].text}          # chỉ khi khác top-1
Gợi ý: {format_hints(hints)}
Dữ liệu ứng dụng:
{trim_snapshot(...)}
```

`weekday_vi = ["hai","ba","tư","năm","sáu","bảy","chủ nhật"][now.weekday()]`.

**`planner.py`:**

```python
def plan(llm, tools, ctx_messages) -> tuple[list[Call], str]:  # (calls, text)
    text = llm.generate(ctx_messages, tools=to_llm_tools(tools))
    return parse_tool_calls(text), extract_text(text)
```

Truyền toàn bộ `tools` (kể cả tool đọc) để planner có thể gọi tool đọc có tham số ở các lượt sau. Gate chặn việc gọi lại tool đọc đã có trong snapshot.

### 5.10 `gate.py` (module quan trọng nhất)

```python
@dataclass
class GateResult:
    calls: list[Call]            # được phép thực thi, theo thứ tự
    ask: Ask | None
    refuse: bool
    notes: list[str]

def gate(raw_calls, text, ctx, tools, valid_ids, entities, hints, env) -> GateResult
```

Duyệt `raw_calls` theo thứ tự, với mỗi `call`:

1. `name = resolve_tool_name(call.name, tools)`; `None` → ghi note, bỏ qua.
2. `name == "sys.ask_missing_info"` → `ask = sanitize_ask(call.args)`: `tool_name` phải thuộc `tools` (không thì dùng `resolve_tool_name`, không được thì bỏ); `params` giữ lại tên có trong `props` của tool đó; nếu danh sách rỗng thì tính `missing_params` của tool với args rỗng; rồi `continue`.
3. Tool `kind=="read"` đã có trong snapshot với cùng args rỗng → bỏ qua (note) — **chỉ khi `BLOCK_READ_ALREADY_PREFETCHED` bật**; tắt nếu metric tính F1-call (gold có ~1 read call/mẫu, nhiều call có args cụ thể, ví dụ `contacts.search {"query":"Lan"}`).
4. `args = coerce_args(tool, call.args)`: bỏ khóa không có trong `props`; ép kiểu theo `type` (`"500000"`→int, `"true"`→bool, chuỗi số thực → float, bỏ khoảng trắng thừa); `enum`: nếu giá trị không thuộc enum thì thử khớp không phân biệt hoa thường, rồi `difflib.get_close_matches(cutoff=0.8)`; không được thì **xóa tham số** (để bước missing xử lý).
5. `fix_refs(tool, args)`: với mỗi tham số có `x-ref` (đọc từ `tool.props[p].get("x-ref")`, `coll = x_ref.split(".")[-1]`): `ids = valid_ids.get(coll)` hoặc hợp mọi tập nếu không có.
   - Giá trị ∈ `ids` → giữ.
   - Ngược lại: tìm ứng viên bằng `match_entities([giá trị đã normalize], entities cùng collection)`, rồi bằng `hints` entity cùng collection. Đúng **một** ứng viên điểm cao nhất (hơn ứng viên kế ≥ 0.05) → thay bằng `entity.id`. Còn lại → **xóa tham số**.
6. `missing = missing_params(tool, args)`: tham số `required` vắng; với `one_of`: nếu không nhóm nào có đủ mọi tham số thì thiếu (`ONE_OF_ASK_MODE == "all"`: toàn bộ tham số của mọi nhóm; `"first_group"`: nhóm đầu tiên).
   - Có `missing` → `ask = Ask(tool.name, missing)`; **dừng duyệt** (các call sau bị bỏ).
7. `env.validate(name, args)`: nếu `ok:false` → thử một lần sửa: nếu lỗi nhắc tên tham số P thì xóa P (nếu P không bắt buộc) rồi validate lại; không được thì bỏ call (note).
8. Giữ call.

Sau vòng lặp:

- `ENABLE_OVERRIDE`: với mỗi call giữ lại, tham số kiểu thời gian (property có `format` chứa `date`, hoặc tên/mô tả chứa `time|giờ|ngày|thời gian|at|date`) mà đúng **một** hint `time` có `conf ≥ 0.9` và khác giá trị hiện tại thì ghi đè; tham số tiền (tên/mô tả chứa `amount|tiền|giá|price`) mà đúng một hint `number` có `conf ≥ 0.9` và khác giá trị thì ghi đè. Ghi mọi ghi đè vào `notes`.
- `ENABLE_AMBIG_ASK`: nếu call có tham số `x-ref` mà các hint entity cùng collection có ≥ 2 ứng viên điểm gần bằng nhau (chênh < 0.05) và giá trị đã chọn nằm trong số đó → `ask = Ask(tool.name, [param])` thay cho call.
- Chống lặp: trong cùng một `raw_calls`, hai call giống hệt nhau về tên + args thì bỏ call sau (chỉ trong cùng danh sách).
- Quyết định cuối: nếu `ask` và có `calls` được giữ trước đó thì theo `ASK_AFTER_PARTIAL`: `True` → giữ cả `calls` và `ask`; `False` → chỉ `ask`. Nếu không có `calls` và không có `ask` → `refuse = True` (ghi note `silent` nếu `text` không chứa `KHONG_HO_TRO`).

**Test (`tests/test_gate.py`):** dùng `FakeEnv` có `validate` trả `ok:True`. Các ca bắt buộc:

- ID bịa → thay bằng ID đúng khi có đúng một ứng viên.
- Thiếu `required` → `Ask` đúng `tool_name`/`params`.
- `x-one-of` thiếu cả hai nhóm → `Ask` theo `ONE_OF_ASK_MODE`.
- Tool ngoài `installed_apps` bị loại.
- `enum` sai kiểu chữ hoa được sửa.
- Hai call trùng trong cùng danh sách còn một.
- Tool đọc đã có trong snapshot bị bỏ (khi `BLOCK_READ_ALREADY_PREFETCHED` bật; tắt thì được giữ).

### 5.11 `executor.py`

```python
def safe_call(env, name, args, log) -> dict   # try/except quanh env.call; không ném lỗi ra ngoài
def run_plan(env, llm, tools, messages, gate_inputs, log) -> None
```

Vòng lặp (B2), `turn` từ 1 đến `MAX_TURNS`:

1. `raw_calls, text = plan(llm, tools, messages)`.
2. `res = gate(...)`. Nếu `res.refuse` → kết thúc (ở `turn == 1` nghĩa là từ chối, không gọi tool nào).
3. Ở `turn ≥ 2`: bỏ mọi lệnh ghi **giống hệt** (tên + args) một lệnh đã thực thi trong mẫu này, trừ khi transcript chứa một từ trong `REPEAT_MARKERS`. Mục đích: chặn vòng lặp ảo của mô hình sau khi đã xong việc.
4. Thực thi từng `call` trong `res.calls`: nếu tool `kind=="write"` thì tăng bộ đếm ghi; vượt `MAX_WRITES` thì dừng. `result = safe_call(env, ...)`. Thêm vào `messages` một assistant message mang `tool_calls` và một message `role="tool"` chứa `json.dumps(result, ensure_ascii=False)[:3000]`.
5. Nếu `res.ask`: thực thi `safe_call(env, "sys.ask_missing_info", {"tool_name":..., "params":[...]})` (sau các call của lượt này nếu `ASK_AFTER_PARTIAL`), rồi **kết thúc vòng lặp**.
6. Nếu không có call nào được thực thi trong lượt này (và không ask) → kết thúc.
7. Nếu `text` chứa `XONG` → kết thúc. Ngược lại sang lượt kế (planner thấy kết quả tool và có thể gọi bước phụ thuộc).

### 5.12 `agent.py`

```python
class Agent:
    def __init__(self, catalog, asr, llm): ...
    def run(self, item, env, split_dir):
        tools = catalog.tools_for(item["context"]["installed_apps"])
        hyps, hist = transcribe_sample(item, asr, split_dir)
        if PREFETCH_MODE == "always":
            snapshot = run_prefetch(env, select_prefetch_tools(tools, PREFETCH_MAX_READS))
        ok, scope_dbg = in_scope(llm, hyps, tools, item["context"])
        if not ok:
            return                              # PREFETCH_MODE="after_scope": chưa gọi tool nào
        if PREFETCH_MODE == "after_scope":
            snapshot = run_prefetch(env, select_prefetch_tools(tools, PREFETCH_MAX_READS))
        entities = build_entities(snapshot); valid_ids = collect_ids(snapshot)
        # (tùy chọn) ENABLE_HOTWORD_REASR: transcribe lại với hotwords
        now = datetime.fromisoformat(item["context"]["current_time"])
        hints = build_hints(hyps, entities, now)
        messages = build_messages(item, hyps, hist, hints, snapshot)
        run_plan(env, llm, tools, messages, gate_inputs=..., log=debug)
```

### 5.13 `infer.py`

Sao chép template của ban tổ chức. Chỉ thay thân `infer()`:

```python
def infer(item):
    env = ToolEnv(SPLIT, item["id"], root=ROOT)     # một lần
    try:
        AGENT.run(item, env, ROOT / SPLIT)
    except Exception as e:
        log_exception(item["id"], e)                # vẫn tiếp tục để nộp đủ dòng
    return env.get_tool_calls(), env.get_state_hash()
```

`AGENT` (ASR, LLM, catalog) khởi tạo **một lần** ở mức module. Vòng lặp ghi `submission.jsonl` nằm trong `try/except` cho từng mẫu để mỗi `id` luôn có đúng một dòng.

### 5.14 `eval/run.py`, `eval/metrics.py`, `eval/asr_eval.py`

```
python eval/run.py --split train --ids heldout_ids.txt --asr gold|real --out runs/<tên>
```

- `--asr gold`: dùng `label.audio_text` thay cho ASR (đo trần của harness). `--asr real`: dùng ASR thật.
- Với mỗi mẫu: chạy `infer`, so `state_hash` với `cache/gold_hash.json`, **và** so `tool_calls` với gold (theo `(name, arguments)` và theo `name`) để tính F1-call.
- Xuất `metrics.json`: **F1 call** (macro trên mẫu; khớp `(name, arguments)`; thêm biến thể chỉ khớp `name` vì chưa biết BTC khớp mềm hay cứng) **và** tỉ lệ khớp `state_hash` (kèm khớp state từng app), theo nhóm (`act/ask/refuse`), theo app; với `ask`: tỉ lệ đúng `tool_name` và đúng tập `params`; số mẫu mỗi loại lỗi. Xem mục 1.1 — không được chỉ báo cáo hash.
- **Taxonomy lỗi** (gán tự động bằng so sánh với gold, mỗi mẫu sai một nhãn): `scope_false_refuse`, `scope_missed_refuse`, `ask_vs_act`, `act_vs_ask`, `wrong_tool`, `wrong_arg_entity`, `wrong_arg_number`, `wrong_arg_time`, `wrong_id`, `gate_dropped_valid`, `exception`.
- `--tune-scope`: quét `SCOPE_LEX_THRESHOLD` (mục 5.6).
- `eval/asr_eval.py`: chạy từng ứng viên ASR trên audio train, tính WER và **lỗi thực thể** (thực thể gold trích ở Pha 0, so khớp sau `normalize`). Ứng viên: PhoWhisper-small/medium, Qwen3-ASR-0.6B/1.7B và các mô hình khác nếu có; chọn theo lỗi thực thể, không chỉ WER.

### 5.15 Module có điều kiện (làm sau khi lõi chạy; mỗi cái một ablation trên held-out)

- **Độ sâu prefetch** (`PREFETCH_MAX_READS` = 0 / 1 / 2 / tất cả) và `BLOCK_READ_ALREADY_PREFETCHED` bật/tắt: ablation trên held-out, đo **cả** F1-call và hash (mục 1.1).
- **Few-shot truy hồi (`retrieval.py`, `ENABLE_FEWSHOT`):** dựng chỉ mục BM25 (tự cài) trên `audio_text` + danh sách app của các mẫu `tune`. Với mẫu mới lấy 3 ví dụ gần nhất (loại chính mẫu nếu đang đánh giá train). Mỗi ví dụ chèn vào prompt dạng `Yêu cầu: ... → Gọi: tên_tool(args)`, **thay mọi giá trị ID bằng `<id lấy từ dữ liệu>`** để tránh chép ID. Luôn đảm bảo có tối đa một ví dụ `ask` và một ví dụ `refuse` nếu tồn tại trong các ứng viên gần.
- **Hotwords re-ASR (`ENABLE_HOTWORD_REASR`), ghi đè (`ENABLE_OVERRIDE`), hỏi khi mơ hồ (`ENABLE_AMBIG_ASK`):** đã có sẵn trong mã ở trên, chỉ bật cờ để đo.
- **Quy tắc chính sách từ train:** nếu `policy.json` cho thấy một cặp `(tool, tham số)` luôn được gold điền mặc định (ví dụ `from` luôn lấy vị trí hiện tại) thì thêm câu quy tắc tương ứng vào system prompt (một câu mỗi quy tắc). Bật từng quy tắc, đo trên held-out.

Quy tắc chung: module nào không tăng điểm trên held-out (đo **cả** F1-call và hash) thì tắt cờ và bỏ khỏi bản nộp.

---

## 6. Lộ trình giao việc và tiêu chí hoàn thành

| Mốc | Việc | Hoàn thành khi |
|---|---|---|
| **M0** | `inspect_data.py`, `analyze_train.py`, `gold_hash.py`, `split.py`; điền các giá trị `[M0]` trong `config.py`; **chốt công thức chấm** (mục 1.1) hoặc ghi rõ giả định đang dùng | Có `reports/*.json`; `gold_hash.json` đủ mọi mẫu train; kiểm tra "tạo ToolEnv lần hai không rò trạng thái" đạt; `eval/metrics.py` xuất đồng thời F1-call và hash |
| **M1** | `catalog.py`, `prefetch.py`, `lexicon.py`, `llm.py`, `prompt.py`, `planner.py`, `gate.py` (phần 1-8), `executor.py`, `agent.py` (chưa có ASR, dùng `--asr gold`), `eval/run.py` | `tests/test_catalog.py`, `tests/test_gate.py` qua; chạy `--asr gold` trên held-out cho ra `metrics.json`; số này là trần của harness |
| **M2** | `vi_norm.py` + `tests/test_vi_norm.py` (toàn bộ bảng 5.4 phải qua); `asr.py`; `eval/asr_eval.py` đo WER và lỗi thực thể cho các ứng viên; chọn `ASR_MODEL` | Có bảng so sánh ASR; chọn xong mô hình |
| **M3** | `scope.py`, `resolver.py`, `tests/test_resolver.py`, nối ASR thật vào `agent.py`, chạy `--asr real`, tune `SCOPE_LEX_THRESHOLD` | `metrics.json` ở chế độ `real`; chênh lệch với M1 cho biết phần mất do ASR; mọi mẫu `refuse` của held-out cho `tool_calls == []` khi scope đúng |
| **M4** | Bật từng cờ ở 5.15, mỗi lần một ablation | Mỗi cờ có bảng so sánh trên held-out (F1-call + hash); giữ cờ nào tăng điểm |
| **M5** | Che/đổi tên tool trong catalog dev rồi chạy lại (kiểm tra tổng quát hóa); đo thời gian chạy toàn bộ một split | Độ sụt điểm khi đổi tên tool được ghi nhận; `infer.py` xuất đủ một dòng cho mỗi `id` |
| **M6** | Chạy `infer.py` trên `public_test`, kiểm tra `submission.jsonl` (đúng một dòng mỗi `id`, JSON hợp lệ, `state_hash` không rỗng) | File nộp qua kiểm tra định dạng |

**Thứ tự ưu tiên khi thiếu thời gian:** M0 → M1 → M3 → M2 → M4 → M5. M1 đã cho một agent chạy được với transcript vàng; mọi mốc sau đều đo độ cải thiện so với nó.
