# EXECUTION-PLAN.md — Kế hoạch thực thi DataMate (v3)

> **NGUỒN CHUẨN DUY NHẤT CHO MỌI QUY TẮC HIỆN THỰC.**
> Agent code chỉ cần đọc file này. Mọi thứ cần để implement (hợp đồng dữ liệu, hợp đồng Spec, SQL mẫu, prompt, thuật toán, test, tiêu chí nghiệm thu) đều nằm ở đây.
>
> | File | Vai trò | Khi xung đột |
> |---|---|---|
> | **`EXECUTION-PLAN.md`** (file này) | đặc tả code, rào phạm vi, quy tắc vàng, nghiệm thu | **luôn thắng** |
> | `docs/mNN.md` | **nhật ký phát hiện dữ liệu thật** của milestone (chỉ cho M4, M5, M8, M9, M12) | không được mâu thuẫn file này; nếu phát hiện file này sai thì ghi `BACKLOG.md` và cập nhật file này trong cùng commit |
> | `README.md` | điểm vào (bài toán, cách chạy) | file này thắng |
> | `Planning.md`, `DECISIONS.md` | rationale / biên bản | file này thắng; nếu `DECISIONS.md` lệch thì **sửa `DECISIONS.md`** |
>
> **Cách dùng:** đọc mục 0 (quy trình) → mục 1 (kiến trúc, để hiểu *tại sao*) → mục 3 (hợp đồng dữ liệu) → **mục 4 (hợp đồng Spec và engine, bắt buộc đọc kỹ)** → mục 5 (milestone đang làm).
> Việc phát sinh → `BACKLOG.md`. **Không** vá tay ngoài phạm vi milestone.

---

## 0. Quy trình làm việc

### 0.1 Chống out-of-scope (3 lớp)

| Lớp | Cách hoạt động |
|---|---|
| **1. Rào phạm vi** | Mỗi milestone có `IN scope` / `OUT scope`. OUT scope = cần nhưng **không làm ở milestone này**; ghi vào `BACKLOG.md` kèm lý do. |
| **2. Hợp đồng hàm** | Mỗi hàm có chữ ký, hành vi, edge case. Implement đúng hợp đồng, không tự mở rộng. |
| **3. Nghiệm thu khép kín** | Mỗi milestone có checklist chạy được. Chưa đạt → **không commit milestone sau** (cổng ở 0.3). |

### 0.2 Detail sheet (rút gọn, chỉ 5 milestone)

Thiết kế **đã nằm trong file này**. `docs/mNN.md` chỉ là **nhật ký những điều chỉ biết sau khi nhìn dữ liệu thật** (tên cột thực, định dạng thực, câu rulebook thực). Bắt buộc cho **M4, M5, M8, M9, M12**, viết **trước khi code** milestone đó, theo template:

```markdown
# M<n> — <tên>
## 1. Phát hiện từ dữ liệu thật (trích survey/…, tên file/cột/câu cụ thể)
## 2. Quyết định chốt (mỗi dòng: vấn đề → chọn gì → vì sao)
## 3. Chỗ nào lệch EXECUTION-PLAN.md (nếu có → sửa EXECUTION-PLAN.md cùng commit)
## 4. Test bổ sung phát sinh từ dữ liệu thật
```

Milestone khác: **không cần** detail sheet.

### 0.3 Trạng thái, phụ thuộc, cổng

| M | Tên | Phụ thuộc | Detail sheet | Trạng thái |
|---|---|---|---|---|
| M0 | Nền tảng: config, dtypes, chấm điểm, survey, **LLM client** | — | — | ☐ |
| M1 | Ingest + làm sạch | M0 | — | ☐ |
| M2 | Time resolver + lịch âm | M1 | — | ☐ |
| M3 | Rulebook → Knobs + RuleSpec | M0, M6 | — | ☐ |
| M4 | Canonicalize + mapper + bất biến + views | M1, M3, M6 | ☐ **bắt buộc** | ☐ |
| M5 | Metric registry + compile_spec + executor | M4 | ☐ **bắt buộc** | ☐ |
| M6 | Chuẩn hoá + entity linking + BM25 | M0 | — | ☐ |
| M7 | Formatter | M5 | — | ☐ |
| M8 | Enumerate-and-match + ngân hàng | M2, M5, M6, M7 | ☐ **bắt buộc** | ☐ |
| M9 | Đường 1 (Spec) | M8 | ☐ **bắt buộc** | ☐ |
| M10 | Đường 2 (SQL) | M9 | — | ☐ |
| M11 | Answerability | M4, M8 | — | ☐ |
| M12 | Quyết định + calibration + leo thang | M9, M10, M11 | ☐ **bắt buộc** | ☐ |
| M13 | Orchestrator `predict.py` | M12 | — | ☐ |
| M14 | Ablation | M13 | — | ☐ |
| M15 | Mở rộng ngành mới (sửa xe, điện thoại, mẹ và bé) | M13 | — | ☐ |
| M16 | **Đóng gói Docker + tái lập + nộp** | M13 | — | ☐ |

Thứ tự thực hiện: `M0 → M1 → M6 → M2 → M3 → M4 → M5 → M7 → M8 → (cổng G2) → M9 → M10 → M11 → M12 → M13 → {M14, M15, M16}`.

**Cổng G1 (design):** M4, M5, M8, M9, M12 chưa có `docs/mNN.md` → không code.
**Cổng G2 (nghiệm thu M8):** không được bắt đầu M9 nếu M8 chưa đạt ngưỡng ở 5.M8 (đo trên **dev** *và* **holdout**).
**Cổng G3 (end-to-end):** M14/M15/M16 chỉ bắt đầu khi M13 tạo được `submission.jsonl` hợp lệ cho 100% id.

### 0.4 Quy tắc vàng (vi phạm = phải revert)

1. **Không hardcode theo business hay câu hỏi:** cấm `if business_id == …`, cấm điều kiện theo `question.id`. Luật thi (Rule 4) coi đây là vi phạm loại bài. Mọi khác biệt phải đến từ **cấu trúc dữ liệu, tên cột, README, rulebook**.
2. **Không secret trong repo:** `DATAMATE_LLM_API_KEY` từ biến môi trường; `.env` trong `.gitignore`.
3. **Không thêm thư viện** ngoài danh sách: `pandas, openpyxl, duckdb, numpy, rapidfuzz, scikit-learn, joblib, pyarrow, httpx, pytest, python-dateutil` (+ stdlib). Cần thêm → `BACKLOG.md` và được duyệt.
4. **Mọi duyệt `dict/set` đưa vào quyết định phải `sorted(...)`**.
5. **Mọi hàm có type hints và có test** trong `tests/`.
6. **Mọi lời gọi LLM** đi qua `llm/client.py`: `temperature=0`, `seed=0`, tiền tố prompt cố định, thứ tự input cố định.
7. **Không network ngoài endpoint LLM đã cấu hình.** Khi chạy trong Docker: không download, không gọi API ngoài.
8. **Một commit = một milestone** (hoặc một phần rõ ràng): `M<n>: <nội dung>`.
9. **`as_of` là thuộc tính của câu hỏi, không phải của business.** Cấm hard-code `as_of` trong view; mọi cắt theo `as_of` do `compile_spec` chèn vào SQL (4.5).
10. **LLM không bao giờ viết ngày, không viết logic nghiệp vụ, không tự đặt tên thực thể.** Ngày do `resolve_time`; nghiệp vụ do view + registry; thực thể lấy từ danh sách ứng viên (4.4).
11. **Không đọc `dev/splits.json` trong code inference** (chỉ dev dùng).

### 0.5 Quy ước code

- Python 3.12, `.venv/` ở gốc repo. `from __future__ import annotations`. Dataclass cho cấu trúc dữ liệu, `Enum` cho intent/metric/type.
- Lỗi: hàm xử lý lỗi cục bộ trả giá trị lỗi có kiểu; executor trả `ExecResult(error=…)`, **không raise**. Chỉ raise cho lỗi lập trình.
- Log: `logging.getLogger(__name__)`, mức `INFO`, **không in ra stdout**.
- **Tiền lưu `DECIMAL(20,4)`** trong DuckDB (chính xác, không sai số float), tỉ lệ/phần trăm tính bằng `DOUBLE`; **làm tròn đúng một lần ở formatter** bằng `decimal.Decimal` + `ROUND_HALF_UP`.
- **Kiến trúc kết nối DuckDB:**
  - `cache/<sha256>.duckdb` (ghi một lần) chứa các bảng sạch `t_<slug>` (M1) **và** bảng canonical `c_*` (M4).
  - Lúc chạy: `con = duckdb.connect(":memory:")`, `ATTACH '<cache>' AS cache (READ_ONLY)`, tạo view `v_*` trong bộ nhớ trỏ tới `cache.c_*`. Không ghi vào cache.
  - **Spike bắt buộc ở M1:** xác nhận tạo `VIEW` trong `:memory:` trỏ tới bảng của DB đã `ATTACH READ_ONLY` chạy được. Nếu không: copy `c_*` vào `:memory:` (dữ liệu ≤ 300k dòng nên nhẹ).
- Thư mục cache: `DATAMATE_CACHE_DIR` (mặc định `/tmp/datamate_cache`). **Không bao giờ ghi vào `/data`** (chỉ đọc).
- Cache khoá theo `sha256` **nội dung file dữ liệu** (đã sắp theo tên) + `SCHEMA_VERSION`, **không** theo `business_id`.

### 0.6 Chia dev / holdout (chỉ dùng lúc phát triển)

- 30 business train → **24 dev + 6 holdout**, chọn một lần bằng `random.Random(RANDOM_SEED).sample(sorted(ids), 6)`, ghi `dev/splits.json`.
- **Vòng sửa lỗi (M8) chỉ nhìn `unmatched` của dev.** Với holdout chỉ xem **số liệu tổng hợp**; không mở từng câu holdout để sửa từ điển. Mục đích: đo khả năng tổng quát hoá sang business lạ.
- Bản nộp cuối dựng ngân hàng ví dụ từ **cả 30 business**.
- Calibration (M12) dùng `GroupKFold` theo business trên cả 30 (bank của fold bị loại không chứa câu của business đó).

---

## 1. Kiến trúc và lý do (đọc để hiểu vì sao kế hoạch có thứ tự này)

```
Files ─► [M1 Ingest] ─► t_* (bảng sạch)
              │
              ▼
        [M4 canonicalize theo archetype] ─► c_* (bảng canonical, tên cột cố định)
              │                                   ▲ bất biến → schema_conf
              ▼                                   │
        [M4 views v_*]  ◄── Knobs/RuleSpec [M3] ──┘     (view KHÔNG chứa as_of)
              ▲
 question ─► [M6 nd + entity] ─► [M2 windows]
              │
              ├─► ĐƯỜNG 1: LLM điền Spec (JSON, constrained) ─► validate ─► [M5 compile_spec] ─┐
              └─► ĐƯỜNG 2: LLM viết SQL trên v_* ────────────────────────────────────────────────┤
                                                                                                  ▼
                        [M11 answerability] ─► [M12 decide: p̂ > 0.5] ─► [M7 formatter] ─► answer
```

Điểm là **PA = +1 đúng, 0 abstain, −1 sai**. Mọi quyết định thiết kế phục vụ các nguyên tắc sau:

1. **Nghiệp vụ nằm ở code, không ở LLM.** Rulebook (doanh thu, loại đơn huỷ/trả, đơn vị cơ bản, công nợ…) được áp **một lần** trong view và registry. Vì vậy phải xong M1→M5 trước khi nối LLM.
2. **Hai lớp dữ liệu.** `c_*` (canonical) hấp thụ mọi khác biệt giữa các archetype; `v_*` (view) áp rulebook và **giống nhau cho mọi business**. Metric/Spec chỉ biết `v_*`.
3. **LLM chỉ chọn trong tập đóng.** Ngày → nhãn do `resolve_time` cấp; thực thể → mã từ danh sách ứng viên; metric/intent/subject → enum. Đường 1 = *điền chỗ trống* vào khung SQL; k mẫu để tăng xác suất điền đúng **và** đo độ tin cậy (`p1_vote_frac`).
4. **Hai đường độc lập một phần.** Đường 2 (SQL tự do trên view) dùng biểu diễn khác nên bắt lỗi tầng câu hỏi; **không** bắt được lỗi tầng dữ liệu/rulebook dùng chung (đó là việc của bất biến M4).
5. **Unanswerable suy ra bằng code** từ capability dữ liệu; không chắc thì abstain (đoán sai −1).
6. **Calibration quyết định trả lời.** Chỉ trả khi `p̂ − margin > 0.5`.
7. **Tổng quát hoá sang business/loại hình lạ** là mục tiêu chính của test private (đề nói có loại hình chưa thấy). Vì vậy: archetype `UNKNOWN` có đường đi riêng, holdout tách riêng, và ngành mới (M15) xếp sau lõi.
8. **Tái lập:** greedy, seed cố định, sort mọi thứ, đo ΔPA giữa hai lần chạy (Rule 8: ≤ 0.03).

---

## 2. Bố cục repo

```
datamate/
├── README.md  Planning.md  DECISIONS.md  EXECUTION-PLAN.md  BACKLOG.md
├── docs/mNN.md                       # chỉ M4, M5, M8, M9, M12
├── requirements.txt                  # M0
├── config.py                         # M0
├── dtypes.py                         # M0
├── ingest/{reader.py, clean.py}                          # M1
├── timeutil/{calendar_vi.py, resolver.py}                # M2
├── rules/{knobs.py, rulebook_parser.py}                  # M3
├── schema/{roles.py, archetypes.py, canon.py, mapper.py,
│           invariants.py, views.py, card.py}              # M4
├── engine/{registry.py, compile.py, templates.py, lots.py,
│           executor.py, sandbox.py}                       # M5
├── text/{normalize.py, entity_linker.py, bm25.py,
│         numeric_filters.py, abbrev_vi.json}             # M6
├── fmt/{compare.py, formatter.py}                        # M0, M7
├── llm/{client.py, fake.py, schemas.py, prompts.py}      # M0 (client, fake), M9 (schemas, prompts)
├── paths/{path1_spec.py, path2_sql.py}                   # M9, M10
├── decide/{answerability.py, features.py, calibrate.py,
│           decider.py, escalate.py}                      # M11, M12
├── domains/{repair.py, phone.py, baby.py}                # M15
├── dev/{survey.py, evaluate.py, enumerate_match.py, build_bank.py, tag_group.py,
│        run_train.py, null_causes.py, repro_check.py, ablate.py, splits.json}
├── predict.py                                            # M13
├── docker/{Dockerfile, predict.sh, start_llm.sh, README_solution.md}   # M16
├── models/  survey/  cache/  .venv/                      # gitignore
└── tests/{fixtures/, test_*.py}
```

---

## 3. Hợp đồng dữ liệu

### 3.1 `dtypes.py`

```python
class AnswerType(str, Enum):
    STRING="string"; NUMBER="number"; PERCENT="percent"; DATE="date"
    BOOLEAN="boolean"; LIST="list"; TABLE="table"
    UNANSWERABLE="unanswerable"; ABSTAIN="abstain"

@dataclass
class Question: id:str; business_id:str; text:str; as_of:date

@dataclass
class Answer:
    type: str                       # AnswerType
    value: Any = None               # đúng định dạng submission
    reason: str | None = None       # chỉ cho unanswerable

@dataclass
class Knobs:                        # mặc định = rulebook train
    revenue_after_line_discount: bool = True
    revenue_deduct_order_voucher: bool = False
    revenue_include_vat: bool = False
    revenue_include_shipping: bool = False
    exclude_cancelled: bool = True
    returned_policy: str = "exclude_order"   # exclude_order | exclude_line | ignore
    bestseller_metric: str = "qty"           # qty | revenue | orders
    week_start: int = 0                      # 0 = Thứ Hai
    this_month: str = "month_to_date"
    this_week: str = "week_to_date"
    last_n_includes_today: bool = True
    cost_method: str = "line_cost"           # line_cost | wavg_by_lot | wavg_up_to_sale_date
    tet_start: tuple = ("lunar", 12, 23, -1) # (loại, tháng, ngày, offset năm âm lịch)
    tet_end:   tuple = ("lunar", 1, 10, 0)
    shift_morning: tuple = (6, 13)           # giờ bắt đầu, giờ kết thúc (gồm)
    shift_afternoon: tuple = (14, 21)
    rounding_money: str = "half_up"

@dataclass
class RuleSpec:
    knobs: Knobs
    domains: set[str]               # ngành rulebook nhắc: cafe|pharmacy|construction|baby|repair|phone|…
    features: set[str]              # mục nghiệp vụ rulebook có nêu (xem 3.3) — CHỈ để tính tin cậy
    unmapped: list[str]             # câu rulebook không map được

@dataclass
class TimeWindow:
    label: str; start: date; end: date          # inclusive
    kind: str = "period"                         # period | cumulative | shift
    shift: str | None = None                     # "sang" | "chieu"
    trunc_same_days: bool = False

@dataclass
class BizContext:
    con: Any                         # duckdb connection (:memory:, đã tạo v_*)
    archetype: str                   # "A_flat" … hoặc "UNKNOWN"
    data_caps: set[str]              # capability DỮ LIỆU (3.2)
    date_min: date; date_max: date
    schema_conf: float               # 0..1
    flags: dict                      # cờ từ bất biến (line_amount_includes_vat, …)
    status_invalid: dict             # {"cancelled":[…], "returned":[…]}
    value_dict: dict                 # {"channel":[…], "pay_method":[…], "customer_group":[…], …}
    card: str                        # schema card (4.11)
    entity_index: Any
    rules: RuleSpec
    invariants: dict                 # kết quả từng bất biến (để log)
    verified: bool                   # False cho domain M15 / UNKNOWN (không có đáp án để kiểm)

@dataclass
class Spec:                          # xem 4.4 — hợp đồng chính thức
    intent:str; metric:str|None; subject:str|None; filters:list[dict]
    time:list[str]; having:dict|None; order:str; limit:int|None
    output:str; params:dict

@dataclass
class CompiledPlan:
    sql: str                         # SQL trả bảng kết quả
    post: str | None                 # tên hậu xử lý Python (4.6)
    out_type: str
    meta: dict                       # {"is_money":bool, "value_col":"value", "subject":…}

@dataclass
class ExecResult: columns:list[str]; rows:list[tuple]; error:str|None; elapsed_s:float
@dataclass
class Candidate: answer:Answer; source:str; spec_or_sql:str; votes:int; k:int
@dataclass
class EntityMatch: span:tuple[int,int]; kind:str; canonical_name:str; code:str|None; score:float
@dataclass
class AnswerCheck: answerable:bool; p_unanswerable:float; reason:str; entity_missing:bool
@dataclass
class MappingCandidate: mapping:dict; penalties:dict; score:float; schema_conf:float
```

### 3.2 Capability DỮ LIỆU (`ctx.data_caps`) — suy ra từ dữ liệu, **không** từ rulebook

| cap | điều kiện có |
|---|---|
| `line_amount` | `c_lines.line_amount` có và qua `inv_line_math` |
| `qty` | `c_lines.qty` có |
| `qty_base` | có `qty_base` hoặc suy được từ `c_units` |
| `order_date` | `c_orders.order_date` parse ≥ 90% |
| `order_ts` | `order_ts` có giờ (không chỉ ngày) ≥ 90% dòng |
| `customer` | `customer_key` hoặc `customer_name` có |
| `category` | `c_products.category` có |
| `cost_line` | `line_cost_total` có ≥ 80% dòng |
| `cost_catalog` | `c_products.unit_cost` có |
| `cost` | `cost_line` hoặc `cost_catalog` hoặc `lots` |
| `lots` | `c_lots` có `lot_qty` + `lot_cost` |
| `expiry` | `c_lots.expiry_date` hoặc cột hạn dùng ở danh mục |
| `inventory_snapshot` | `c_inventory` có |
| `stock` | `inventory_snapshot` hoặc (`lots` và `line`) |
| `payments` | `c_payments` có |
| `order_debt` | `c_orders.order_debt_total` có |
| `debt` | `order_debt` |
| `imports` | `c_imports` có |
| `price_history` | `c_price_history` có |
| `units` | `c_units` có |
| `channel`, `pay_method`, `employee`, `customer_group`, `customer_since`, `size` | cột tương ứng có |
| `returns` | `return_flag` hoặc `c_returns` có |
| `deliveries` | `c_deliveries` có |

### 3.3 `RuleSpec.features` (chỉ dùng cho độ tin cậy, **không** dùng để suy unanswerable)

`cash_shift_report`, `peak_hour`, `loyal_customer`, `topping_split`, `installment`, `trade_in`, `warranty_service`, `repair_ticket`, `member_since`, `size_breakdown`, `product_group_share`, `debt_rules`, `cost_rules`. Câu hỏi thuộc nhóm `X` mà `X ∉ rules.features` → feature `rule_missing=1` ở M12 (hạ p), **không** đánh unanswerable.

### 3.4 `config.py`

```python
RANDOM_SEED = 20261103
HOLDOUT_BUSINESSES = 6
SCHEMA_VERSION = "v3"

DATA_ROOT   = os.environ.get("DATAMATE_DATA_ROOT", "/data")      # mount của BTC
OUT_DIR     = os.environ.get("DATAMATE_OUT_DIR", "/result")
CACHE_DIR   = os.environ.get("DATAMATE_CACHE_DIR", "/tmp/datamate_cache")
DEADLINE_S  = 5.25*3600                                            # tính từ lúc predict.sh bắt đầu

# LLM
LLM_BASE_URLS   = os.environ.get("DATAMATE_LLM_BASE_URLS", "http://127.0.0.1:8000/v1").split(",")
LLM_API_KEY     = os.environ.get("DATAMATE_LLM_API_KEY", "EMPTY")
LLM_MODEL       = os.environ.get("DATAMATE_LLM_MODEL", "Qwen3-4B")
LLM_CONCURRENCY = 16
LLM_MAX_RETRIES = 4
LLM_TIMEOUT_S   = 120
LLM_CTX_TOKENS  = 8192

# Chấm điểm (rulebook §9)
NUM_ABS_TOL = 1e-9; NUM_DECIMALS = 2; PERCENT_DECIMALS = 2; MONEY_ROUND = "half_up"

# Nghiệp vụ
EXPIRING_DEFAULT_DAYS = 30
SLOW_QTY_PERCENTILE = 25
HIGH_STOCK_PERCENTILE = 75
K1 = 3; K2 = 5                     # số mẫu đường 1, đường 2
CALIB_MARGIN = 0.05
UNVERIFIED_EXTRA_MARGIN = 0.15     # domain M15 / UNKNOWN
CALIB_MIN_TRAIN_PER_OUTTYPE = 50
SQL_TIMEOUT_S = 20; SQL_MAX_ROWS = 1000
```

---

## 4. Hợp đồng Spec và engine (**phần cốt lõi — M5, M8, M9, M10, M11 đều dựa vào đây**)

### 4.1 Hai lớp dữ liệu

**Lớp 1 — `c_*` (canonical, vật lý, tạo ở M4, nằm trong cache):**

| bảng | cột (tên cố định) |
|---|---|
| `c_orders` | `order_id TEXT, order_date DATE, order_ts TIMESTAMP?, customer_key TEXT?, customer_name TEXT?, status_raw TEXT?, channel TEXT?, pay_method TEXT?, employee TEXT?, order_total DEC?, shipping_fee DEC?, vat_amount DEC?, vat_rate DOUBLE?, order_voucher DEC?, order_debt_total DEC?, order_paid DEC?` |
| `c_lines` | `order_id, line_no INT, product_code TEXT?, product_name TEXT, qty DOUBLE, qty_base DOUBLE?, unit_name TEXT?, unit_price DEC?, line_discount DEC?, line_amount DEC, line_cost_total DEC?, return_flag BOOL, return_qty DOUBLE?, is_service BOOL, size TEXT?` |
| `c_products` | `product_code, product_name, category, unit, unit_cost DEC?, size?` |
| `c_customers` | `customer_key, customer_name, phone, customer_group, customer_since DATE?, is_walkin BOOL` |
| `c_payments` | `order_id?, customer_key?, pay_date DATE, pay_amount DEC, pay_method?` |
| `c_lots` | `lot_id, product_code, lot_date DATE, lot_qty DOUBLE, lot_cost DEC, expiry_date DATE?` |
| `c_inventory` | `product_code, inv_date DATE, inv_qty DOUBLE, lot_id?` |
| `c_imports` | `import_id, import_date DATE, product_code, qty DOUBLE, qty_base DOUBLE?, unit_name TEXT?, amount DEC, is_cancelled BOOL, supplier?` |
| `c_units` | `product_code, unit_name, unit_factor DOUBLE` |
| `c_price_history` | `product_code, ph_date DATE, ph_old DEC, ph_new DEC` |
| `c_returns` | `order_id, product_code?, return_date DATE?, return_qty DOUBLE` |
| `c_deliveries` | `order_id, del_date DATE, employee?` |

`?` = có thể NULL. Bảng thiếu → không tạo và **không** có capability tương ứng. Nhiều bảng nguồn (sheet theo tháng, phiếu + chi tiết) được **hợp nhất/join ở bước canonicalize**, không để lọt xuống view.

**Lớp 2 — `v_*` (view, tạo trong `:memory:`, áp knob, KHÔNG có `as_of`):**

| view | cột | quy tắc |
|---|---|---|
| `v_orders_all` | `order_id, order_date, order_ts, customer_key, customer_name, channel, pay_method, employee, is_cancelled, is_returned, has_return, is_cod, is_marketplace, is_walkin, order_total, order_debt_total, …` | **mọi trạng thái** (cho `cancel_rate`) |
| `v_orders` | như trên | chỉ đơn hợp lệ: `NOT is_cancelled` (nếu `exclude_cancelled`) và áp `returned_policy` (`exclude_order` → loại đơn có `has_return`) |
| `v_lines` | `order_id, order_date, order_ts, line_no, product_code, product_name, category, customer_key, customer_name, is_walkin, channel, pay_method, employee, customer_group, qty, qty_base, unit_name, base_unit, line_amount_net, line_cost_total, is_service, size` | **chỉ dòng của `v_orders`**; `line_amount_net` theo knob (4.1.1). **Join**: `v_lines = c_lines JOIN v_orders ON order_id` (mang `channel, pay_method, employee, is_walkin, order_ts`) `LEFT JOIN v_products ON product_code` (mang `category, base_unit = v_products.unit` = **đơn vị cơ bản**) `LEFT JOIN v_customers ON customer_key` (mang `customer_group`) |
| `v_products` | `product_code, product_name, category, unit, unit_cost` | tên master = tên xuất hiện nhiều nhất theo `product_code` |
| `v_customers` | `customer_key, customer_name, customer_name_nd, customer_group, customer_since, is_walkin` | |
| `v_payments` | `order_id?, customer_key, pay_date, pay_amount` | |
| `v_debt_events` | `customer_key, order_id, event_date, delta DEC, kind` | `kind='order'` (+`debt_initial`, ngày đặt) và `kind='payment'` (−`pay_amount`, ngày thu); **loại đơn huỷ, COD, sàn TMĐT**; **không cộng VAT** (rulebook §4, quyết định 12) |
| `v_stock_inputs`, `v_imports`, `v_price_history`, `v_lots`, `v_units` | tương ứng `c_*` | chỉ tạo nếu có capability |

**4.1.1 `line_amount_net`:** bắt đầu từ `line_amount` (đã sau giảm giá dòng theo bất biến). Nếu cờ `line_amount_includes_vat` → chia `(1+vat_rate)`; nếu `revenue_deduct_order_voucher` → trừ voucher phân bổ theo tỉ trọng dòng; nếu `revenue_include_vat/shipping` → cộng tương ứng. **Dòng `is_service` (phí phục vụ) vẫn nằm trong `line_amount_net`** (vẫn tính doanh thu) nhưng bị loại khỏi xếp hạng/đếm (4.8).

**4.1.2 Cờ `is_cod`, `is_marketplace`:** từ `pay_method` (chứa `cod|thu ho`) và `channel` (chứa `shopee|lazada|tiktok|tmdt|san`). Từ điển ở `config`/`schema/roles.py`, mở rộng bằng dữ liệu train.

### 4.2 Danh mục từ điển giá trị (`ctx.value_dict`)

Lúc dựng context, với mỗi cột `channel, pay_method, customer_group, employee, size, category` lấy tập giá trị phân biệt (≤ 50) kèm bản `nd`. Dùng để (a) rút `filters` từ câu hỏi (M8), (b) đưa vào prompt, (c) validate `filters.values` của Spec.

### 4.3 Registry metric (`engine/registry.py`)

```python
@dataclass
class MetricDef:
    name: str
    caps: set[str]                 # cap DỮ LIỆU bắt buộc (4.3 / 3.2)
    source: str                    # view gốc
    date_col: str                  # cột ngày dùng cho cửa sổ thời gian
    value_expr: str                # biểu thức aggregate trên alias `s`
    subjects: set[str]             # subject hợp lệ
    is_money: bool
    default_output: str
    template: str                  # "std" | "point_stock" | "point_debt" | "expiring" | "cancel_rate" | "import_avg"
```

| metric | caps | source | date_col | value_expr | subjects | tiền |
|---|---|---|---|---|---|---|
| `revenue` | line_amount | `v_lines` | `order_date` | `SUM(s.line_amount_net)` | product, category, customer, day, week, month, channel, pay_method, employee, customer_group, window | ✔ |
| `qty` | qty | `v_lines` | `order_date` | `SUM(COALESCE(s.qty_base, s.qty))` | product, category, customer, day, week, month, window | ✘ |
| `orders` | order_date | `v_orders` | `order_date` | `COUNT(DISTINCT s.order_id)` | customer, day, week, month, channel, pay_method, employee, window | ✘ |
| `customers` | customer | `v_orders` | `order_date` | `COUNT(DISTINCT s.customer_key) FILTER (WHERE NOT s.is_walkin)` | day, week, month, channel, window | ✘ |
| `aov` | line_amount | `v_lines` | `order_date` | `SUM(s.line_amount_net)/NULLIF(COUNT(DISTINCT s.order_id),0)` | day, week, month, channel, window | ✔ |
| `cancel_rate` | order_date | `v_orders_all` | `order_date` | `100.0*SUM(CASE WHEN s.is_cancelled THEN 1 ELSE 0 END)/NULLIF(COUNT(*),0)` | day, week, month, channel, window | ✘ |
| `profit` | line_amount, cost_line | `v_lines` | `order_date` | `SUM(s.line_amount_net - s.line_cost_total)` | product, category, customer, day, week, month, window | ✔ |
| `stock` | stock | (point) | — | tồn tại `as_of` | product, category | ✘ |
| `stock_value` | stock, cost_catalog | (point) | — | `Σ tồn × unit_cost` (giá vốn **danh mục**, quyết định 11) | category, none | ✔ |
| `debt` | debt | (point) | — | số dư nợ tại ngày chốt | customer, none | ✔ |
| `debt_age` | debt, payments | (point) | — | tuổi nợ của khách = `CUTOFF − order_date` gộp theo `params.debt_age_stat` ∈ {`max` (đơn còn nợ cũ nhất), `avg`, `min`}; tuổi tính từ **ngày đặt** (quyết định 13) | customer | ✘ |
| `expiring` | expiry, stock | (point) | — | lô còn tồn có hạn trong `[as_of, as_of+N]` | product | ✘ |
| `stock_split_unit` | stock, units | (point) | — | `[số đơn vị lớn nguyên, số đơn vị cơ bản lẻ]` của mặt hàng (rulebook §3, quyết định 14) | product | ✘ |
| `import_amount` | imports | `v_imports` | `import_date` | `SUM(s.amount)` (bỏ phiếu huỷ) | product, day, week, month, supplier, window | ✔ |
| `import_avg_price` | imports | `v_imports` | `import_date` | `SUM(s.amount)/NULLIF(SUM(COALESCE(s.qty_base, s.qty)),0)` (bình quân **theo số lượng quy về đơn vị cơ bản**) | product | ✔ |

**Đơn vị:** `qty_base` là số lượng quy về **đơn vị cơ bản** (rulebook §3). `c_lines.qty_base` có thể NULL ⇒ mọi tổng dùng `COALESCE(qty_base, qty)`.
Câu **"bán được bao nhiêu `<đơn vị>`"** (`params.unit_name`) → lọc theo **đơn vị cơ bản của mặt hàng**: `s.base_unit = '<đơn vị>'` (quyết định 7 — KHÔNG lọc theo `unit_name` của dòng, vì dòng có thể bán theo đơn vị lớn), vẫn cộng `qty_base`.
`import_avg_price` phải quy về đơn vị cơ bản (c_imports.qty_base) — nếu không, trộn thùng với chai làm sai trung bình.
`stock_split_unit` chỉ để khớp câu **train** ở M8: `public_test` đã **bỏ** luật "Tồn theo đơn vị lớn" ⇒ không có câu hỏi loại này ở test.

Metric của ngành mới (`repair_*`, `installment_*`, `members_new`, `size_qty`, `peak_hour`, `loyal_customers`, `cash_by_shift`, `topping_qty`) định nghĩa ở **M15**, không thuộc lõi.

**Quy tắc dấu hiệu:** `price_effect` (câu "tăng giá ảnh hưởng doanh thu…") **không** nằm trong registry lõi cho tới khi M8 khảo sát `survey/price_effect_samples.txt` (các câu train chứa "tang gia|giam gia|doi gia") và chốt công thức (có tham chiếu câu rulebook) trong `docs/m08.md`; trước đó các câu này rơi vào `intent=other`.

### 4.4 Spec — hợp đồng giữa LLM và `compile_spec`

```json
{
  "intent":  "aggregate_total | compare_periods | compare_series | rank_top | lookup_single | filter_list | boolean_check | point_in_time | group_share | cancel_rate | other",
  "metric":  "<tên trong registry> | null",
  "subject": "product | category | customer | day | week | month | channel | pay_method | employee | customer_group | supplier | window | none | null",
  "filters": [ {"field": "product|category|customer|channel|pay_method|employee|customer_group|size|unit_name", "op": "=|!=|in", "values": ["<giá trị>"]} ],
  "time":    ["main", "base", "p1", "p2", "..."],
  "having":  {"op": ">|>=|<|<=", "value": 1000000} | null,
  "order":   "asc | desc",
  "limit":   1 | 3 | 5 | null,
  "output":  "string | number | percent | date | boolean | list | table",
  "params":  { "compare_mode": "pct|diff", "check": "none|series_increasing|series_decreasing|argmax_label|argmin_label|exists|gt_threshold|main_gt_base", "threshold": 0, "expiring_days": 30, "unit_name": "", "debt_age_stat": "max|avg|min", "slow_and_high_stock": false, "extra_metrics": [] }
}
```

**Ràng buộc bắt buộc (LLM không được vi phạm; `validate_spec` kiểm sau khi sinh, vi phạm → mẫu bị loại):**
1. `time` chỉ chứa **nhãn** có trong danh sách `windows` do `resolve_time` cấp. **LLM không viết ngày.**
2. `filters[].values` phải thuộc **danh sách thực thể ứng viên** (tên master/mã, từ `link_entities`) hoặc `ctx.value_dict`. Giá trị lạ → loại.
3. `metric ∈ registry`; `subject ∈ registry[metric].subjects` (hoặc `none`/`null`).
4. `intent`↔`output` hợp lệ theo bảng 4.5.
5. `limit` bắt buộc khi `intent ∈ {rank_top, lookup_single}` (`lookup_single` ⇒ `limit=1`).
6. `params` chỉ chứa key trong mẫu trên.

`having` mang luật "qua/hơn/trên/dưới N **không gồm** N; từ N trở lên **gồm** N" (rulebook §2). Do `text/numeric_filters.py` rút từ câu hỏi (M6) và **đưa vào prompt như gợi ý**; Spec chỉ cần chép lại.

### 4.5 Bảng intent → khung SQL (`engine/templates.py`)

Mọi khung dùng ký hiệu: `{AS_OF}` = `DATE 'YYYY-MM-DD'` của câu hỏi; `{TIME}` = vị từ thời gian (4.7); `{FILTER}` = vị từ filters (AND); `{SUBJ_CODE}`, `{SUBJ_NAME}` theo 4.8.

| intent | output hợp lệ | metric template | khung |
|---|---|---|---|
| `aggregate_total` | number, percent | std | **T1** |
| `compare_periods` | percent, number, (list/string nếu có `subject`) | std | **T3** |
| `compare_series` | boolean, list, string, date | std | **T4** |
| `rank_top` | list, string, table, date | std | **T2** |
| `lookup_single` | string, date, number | std | **T2** (`limit=1`) |
| `filter_list` | list, table | std | **T2** (`limit=null`, có `having`) |
| `boolean_check` | boolean | std/point | **T5** |
| `point_in_time` | number, string, list, table | point_* | **T6** (theo metric) |
| `group_share` | percent | std | **T7** |
| `cancel_rate` | percent | cancel_rate | **T1** trên `v_orders_all` |
| `other` | — | — | không biên dịch; chỉ đường 2 |

**T1 (tổng):**
```sql
SELECT {VALUE_EXPR} AS value
FROM {SOURCE} s
WHERE {TIME} AND {FILTER} AND s.{DATE_COL} <= {AS_OF}
```

**T2 (xếp hạng / liệt kê)** — luôn lấy `limit+1` dòng để formatter phát hiện hoà ở biên:
```sql
WITH g AS (
  SELECT {SUBJ_CODE} AS code, {SUBJ_NAME} AS name, {VALUE_EXPR} AS value
  FROM {SOURCE} s {JOINS}
  WHERE {TIME} AND {FILTER} AND {SUBJ_VALID} AND s.{DATE_COL} <= {AS_OF}
  GROUP BY 1, 2
  {HAVING}                                   -- HAVING {VALUE_EXPR} > N
)
SELECT name, value, code FROM g
ORDER BY value {DIR}, code ASC               -- hoà → code TĂNG DẦN, kể cả khi DIR=ASC
{LIMIT_PLUS_1}                               -- LIMIT limit+1 (bỏ nếu limit=null)
```

**T3 (so sánh kỳ):** hai CTE `m` (cửa sổ `main`), `b` (cửa sổ `base`):
```sql
WITH m AS (SELECT {VALUE_EXPR} AS v FROM {SOURCE} s WHERE {TIME_MAIN} AND {FILTER} AND s.{DATE_COL}<={AS_OF}),
     b AS (SELECT {VALUE_EXPR} AS v FROM {SOURCE} s WHERE {TIME_BASE} AND {FILTER} AND s.{DATE_COL}<={AS_OF})
SELECT CASE WHEN '{MODE}'='pct' THEN (m.v-b.v)*100.0/NULLIF(b.v,0) ELSE (m.v-b.v) END AS value FROM m, b
```
`base = 0` ⇒ `value` NULL ⇒ formatter abstain. Khi `subject` khác `none`: tính `(m−b)` hoặc `%` **theo từng đối tượng** (FULL JOIN hai CTE theo `code`) rồi xếp hạng như T2.

**T4 (chuỗi N kỳ):** `UNION ALL` mỗi nhãn một dòng `(label, value)` theo **đúng thứ tự `spec.time`**; `post` ∈ `{series_increasing, series_decreasing, argmax_label, argmin_label}`.

**T5 (boolean):** chạy T1/T6 rồi `post` ∈ `{exists, gt_threshold, main_gt_base}` (so trong Python, không trong SQL).

**T6 (tại một thời điểm):** theo metric, ngày chốt = `end` của cửa sổ `main` nếu `kind=cumulative`, ngược lại `as_of`:
- `stock`/`stock_value`: có `inventory_snapshot` → lấy snapshot mới nhất có `inv_date ≤ ngày chốt` theo từng sản phẩm; ngược lại `Σ lot_qty (lot_date ≤ ngày chốt) − Σ qty_base bán hợp lệ (order_date ≤ ngày chốt)`.
- `debt`: `SELECT customer_key, SUM(delta) AS bal FROM v_debt_events WHERE event_date <= {CUTOFF} GROUP BY 1 HAVING SUM(delta) > 0`; loại khách lẻ khỏi **xếp hạng** nhưng **cộng vào tổng nợ** (quyết định 8).
- `debt_age`: đơn còn nợ cũ nhất của khách: `{CUTOFF} − MIN(order_date)` trên các đơn có `debt_initial − Σ payments(order_id, ≤ CUTOFF) > 0`; yêu cầu cap `payments` có `order_id`; nếu thanh toán không gắn đơn → áp **FIFO theo ngày đặt** (`engine/lots.py: fifo_allocate`).
- `expiring`: `engine/lots.py: remaining_by_lot(con, cutoff)`: tồn theo lô từ snapshot có `lot_id`; không có → **FIFO theo hạn dùng** (bán trừ lô hạn gần nhất trước). Lọc `expiry_date BETWEEN cutoff AND cutoff + N` (`N = params.expiring_days` mặc định `EXPIRING_DEFAULT_DAYS`).
- `slow_and_high_stock` (điều kiện kép "bán chậm nhưng tồn nhiều"): tính `qty` theo cửa sổ `main` và `stock` tại ngày chốt; chọn sản phẩm có `qty ≤ P25(qty)` **và** `stock ≥ P75(stock)` (phân vị theo `config`, trên các sản phẩm có tồn > 0).

**T7 (tỉ trọng nhóm):** `group_value*100.0/NULLIF(total_shop_value,0)`, trong đó `total_shop_value` là **cùng metric, cùng cửa sổ, toàn bộ cửa hàng** (gồm khách vãng lai và dòng `is_service`), còn `group_value` áp `FILTER` (nhóm hàng/nhóm khách).

### 4.6 `CompiledPlan.post` (hậu xử lý Python ở `engine/compile.py`)

| post | đầu vào | đầu ra |
|---|---|---|
| `None` | bảng kết quả | formatter xử lý theo `out_type` |
| `series_increasing` / `series_decreasing` | dãy `(label,value)` | `bool` — **tăng/giảm chặt chẽ** liên tiếp theo thứ tự `spec.time` |
| `argmax_label` / `argmin_label` | dãy | nhãn kỳ có giá trị lớn/nhỏ nhất (hoà → nhãn xuất hiện trước); formatter đổi nhãn → `YYYY-MM` nếu cửa sổ là một tháng |
| `exists` | số dòng | `bool(rows>0)` |
| `gt_threshold` | giá trị | `value > params.threshold` |
| `main_gt_base` | T3 diff | `value > 0` |

**Ánh xạ `intent` → `post`** (compile_spec tự suy; `params.check` chỉ để *gợi ý*, nếu mâu thuẫn thì `post` theo bảng này):

| intent | post | điều kiện |
|---|---|---|
| `aggregate_total` | `None` | |
| `compare_periods` | `None` | |
| `compare_series` | `argmax_label` / `argmin_label` | `output=string|date` ⇒ argmax/argmin theo câu hỏi; `output=boolean` ⇒ `series_increasing`/`series_decreasing` |
| `rank_top` / `lookup_single` / `filter_list` | `None` | |
| `boolean_check` | `series_increasing`/`series_decreasing` | nhiều kỳ; 1 kỳ ⇒ `exists` |
| `point_in_time` | `None` | |
| `group_share` | `None` | |
| `cancel_rate` | `None` | |

`params.check` được LLM chép lại từ gợi ý; **compile_spec không tin LLM về `post`**.

### 4.7 Vị từ thời gian (`{TIME}`)

Với mỗi nhãn trong `spec.time` lấy `TimeWindow` tương ứng:
- `kind="period"` → `(s.date BETWEEN DATE 'start' AND DATE 'end')`.
- `kind="cumulative"` → `(s.date <= DATE 'end')` (lũy kế từ đầu dữ liệu).
- `kind="shift"` → thêm `AND EXTRACT(hour FROM s.order_ts) BETWEEN lo AND hi` (giờ theo `Knobs.shift_*`); cần cap `order_ts`, thiếu → `unanswerable` (M11).
- Nhiều cửa sổ trong cùng khối: nối bằng `OR` và bọc ngoặc.
- **Mọi truy vấn có thêm `AND s.date <= {AS_OF}`** (bẫy: dữ liệu có thể chứa dòng sau `as_of`).

### 4.8 Luật xếp hạng

- Chỉ **đơn hợp lệ** (đã nằm sẵn trong `v_orders`/`v_lines`).
- `{SUBJ_CODE}`: `product`→`product_code` (rỗng→`nd(product_name)`), `category`→`nd(category)`, `customer`→`customer_key` (rỗng→`nd(customer_name)` đã bỏ ký tự lạ — quyết định 9), `day`→`order_date`, `week`→ngày đầu tuần theo `week_start`, `month`→`date_trunc('month', order_date)`, `window`→nhãn cửa sổ, `channel|pay_method|employee|customer_group`→giá trị cột.
- `{SUBJ_NAME}`: `product`→tên master từ `v_products`; `customer`→`customer_name`; còn lại như code.
- `{SUBJ_VALID}`: `product` → `NOT s.is_service AND s.product_name IS NOT NULL`; `customer` → `NOT s.is_walkin` (khách lẻ loại khỏi xếp hạng, **vẫn** tính trong tổng — quyết định 8); `qty` luôn loại `is_service`.
- Tiêu chí mặc định cho "bán chạy": `knobs.bestseller_metric` (`qty` = `qty_base`).
- `order="asc"` cho "chậm nhất/ít nhất"; vẫn tie-break `code ASC`.
- **Hoà ở biên:** T2 lấy `limit+1`; nếu `value[limit] == value[limit+1]` (hoặc hạng 1 = hạng 2 với "… nhất") → formatter **abstain** (đề bài đã loại các câu hoà ở biên, nên hoà = dấu hiệu ta hiểu sai).
- Ít hơn `limit` phần tử → trả tất cả (đề bài quy định).

### 4.9 Ví dụ Spec (tham chiếu cho prompt và test; as_of = 2026-03-04, thứ Tư)

| # | Câu hỏi | windows | Spec |
|---|---|---|---|
| 1 | "sp bán dc nhiều nhất tuần rồi là gì" | `main` 2026-02-23..2026-03-01 | `{"intent":"lookup_single","metric":"qty","subject":"product","filters":[],"time":["main"],"having":null,"order":"desc","limit":1,"output":"string","params":{}}` |
| 2 | "tháng này doanh thu bao nhiêu" | `main` 2026-03-01..2026-03-04 | `{"intent":"aggregate_total","metric":"revenue","subject":"none","filters":[],"time":["main"],"order":"desc","limit":null,"output":"number","having":null,"params":{}}` |
| 3 | "doanh thu tháng này tăng giảm bao nhiêu % so với tháng trước" | `main` 03-01..03-04; `base` 02-01..02-04 (`trunc_same_days`) | `intent=compare_periods, metric=revenue, time=["main","base"], output=percent, params.compare_mode="pct"` |
| 4 | "top 3 khách mua nhiều nhất tháng 2" | `main` 02-01..02-28 | `intent=rank_top, metric=revenue, subject=customer, limit=3, output=list` |
| 5 | "Xét 3 tháng 1/2026, 2/2026, 3/2026, tháng nào doanh thu lớn nhất" | `p1,p2,p3` (+`main`=p1) | `intent=compare_series, metric=revenue, subject=window, time=["p1","p2","p3"], output=date, params.check=null` (post `argmax_label`) |
| 6 | "dthu 3 tháng 4,5,6/2026 có tăng liên tục ko" | `p1,p2,p3` | `intent=boolean_check, metric=revenue, time=["p1","p2","p3"], output=boolean, params.check="series_increasing"` |
| 7 | "còn ai nợ trên 2 triệu, liệt kê" | `main` cumulative đến as_of | `intent=filter_list, metric=debt, subject=customer, having={">",2000000}, limit=null, output=list` |
| 8 | "tỉ lệ huỷ đơn tháng 6/2025" | `main` 2025-06-01..2025-06-30 | `intent=cancel_rate, metric=cancel_rate, subject=none, output=percent` |
| 9 | "thuốc nào sắp hết hạn" | — | `intent=filter_list, metric=expiring, subject=product, output=list, params.expiring_days=30` |

### 4.10 Quy tắc answerability thống nhất (dùng ở M11)

Thứ tự áp dụng:
1. **Thiếu cap dữ liệu:** `registry[metric].caps ⊄ ctx.data_caps` ⇒ `p_unanswerable = 0.9 × schema_conf`, lý do `"Dữ liệu không có <cap>"`. Ví dụ không có `cost` mà hỏi lợi nhuận (rulebook §7).
2. **Thiếu cap cho cửa sổ ca:** có cửa sổ `kind="shift"` mà thiếu `order_ts` ⇒ `0.9 × schema_conf`.
3. **Kỳ hoàn toàn ngoài phạm vi dữ liệu:** `end < date_min` hoặc `start > date_max` ⇒ `0.8`. **Chồng một phần ⇒ không unanswerable.**
4. **Tương lai:** `start > as_of` ⇒ `0.85`.
5. **Thực thể không tồn tại:** cụm tên không link được ⇒ `entity_missing=True` ⇒ **abstain** (chưa gán unanswerable) cho tới khi `dev/null_causes.py` chứng minh trong câu `null` của train có nhiều trường hợp này.
6. Câu `null` mà không rơi vào 1–5 ⇒ **abstain** (không đoán).

`RuleSpec.features` **không** tham gia các bước trên (chỉ là feature tin cậy).

### 4.11 Mẫu schema card (`ctx.card`, ≤ 1500 token, `schema/card.py`)

```
[DỮ LIỆU] archetype=D_erp | ngày: 2024-09-01..2026-03-03 | schema_conf=0.93
[NĂNG LỰC] line_amount, qty, qty_base, order_ts, customer, category, cost_line, payments, debt, channel, pay_method
[VIEW]
v_lines(order_id, order_date, product_code, product_name, category, customer_name, qty, qty_base, unit_name, line_amount_net, line_cost_total, is_service, channel, pay_method, …)
v_orders(order_id, order_date, order_ts, customer_key, …)  v_products(…)  v_debt_events(…)
[GIÁ TRỊ] channel={Tại quầy|Grab|Shopee} | pay_method={Tiền mặt|Chuyển khoản|COD} | category(top15)={…}
[QUY TẮC KHÁC MẶC ĐỊNH] (chỉ liệt kê knob khác mặc định)
[GHI CHÚ README] (≤ 400 ký tự đầu của README đã làm sạch)
```
Cắt theo thứ tự ưu tiên: bỏ README → rút `category` → rút danh sách cột; không bao giờ cắt `[NĂNG LỰC]` và `[VIEW]`.

---

## 5. Milestone

### M0 — Nền tảng: config, dtypes, chấm điểm, survey, LLM client

**Tạo:** `config.py`, `dtypes.py`, `requirements.txt`, `BACKLOG.md`, `fmt/compare.py`, `dev/survey.py`, `dev/evaluate.py`, `llm/client.py`, `llm/fake.py`, `tests/test_compare.py`, `tests/test_llm_client.py`
**IN:** luật chấm §9; survey; client LLM (dùng sớm bởi M3, M4).
**OUT:** ingest (M1), Spec/prompt (M9).

**`dev/survey.py`** (chạy trên `train/` và `public_test/`, ghi `survey/`, chỉ dev): `columns.csv` (business, file, sheet, cột, kiểu đoán, 5 giá trị mẫu, tỉ lệ null, số giá trị phân biệt); `calendar_head.txt`; `rulebook_sentences.txt` (mỗi câu một dòng đánh số — **mọi tham chiếu "§" của rulebook trong code/test phải trỏ tới số câu này**); `answers_stats.json` (phân bố type, tỉ lệ `null`, 30 câu `null` mẫu, 50 câu mẫu mỗi type); **`as_of_stats.json`** (với mỗi business: số `as_of` phân biệt, min, max — để biết `as_of` có đổi theo câu không); `price_effect_samples.txt` (câu chứa "tang gia|giam gia|doi gia"); `dev/splits.json` (24/6, mục 0.6).

**`fmt/compare.py`:**
```python
def canon_key(ans: Answer) -> Hashable
def is_correct(pred: Answer, ref: dict) -> bool
def norm_text(s: str) -> str
def norm_number(x, is_money: bool) -> Decimal | None
```
Luật (rulebook §9, đã chốt):
- `number`: tiền → số nguyên VND, **nửa đồng làm tròn lên**; số khác → 2 chữ số thập phân; đúng khi `|a−b| ≤ 1e-9` sau chuẩn hoá; chuỗi ("4.820.000") → sai.
- `percent`: khớp tuyệt đối sau làm tròn 2 chữ số.
- `string`: `norm_text` = bỏ khoảng trắng thừa + lower + bỏ dấu câu, **giữ dấu tiếng Việt**; chỉ chấp nhận khác dấu khi khớp phần tử trong `alias`.
- `date`: ISO; câu theo tháng dùng `YYYY-MM` — so `YYYY-MM` với `YYYY-MM-01` cùng tháng là khớp.
- `boolean`: bằng nhau.
- `list`: cùng độ dài, so từng phần tử **theo thứ tự**; phần tử `i` khớp nếu khớp `answer[i]` hoặc phần tử trong `alias[i]`.
- `table`: cùng số cột và số dòng, so từng ô, **bỏ qua tên cột**.
- `ref.answer is None` ⇒ chỉ đúng khi `pred.type=="unanswerable"`; `abstain` luôn 0 điểm.
- `alias == []` hợp lệ.
- `canon_key`: số làm tròn 6 chữ số có nghĩa; chuỗi `norm_text`; list → tuple; table → tuple của tuple.

**`llm/client.py`:**
```python
class LLM:
    def __init__(self, cfg=config): ...
    async def agenerate(self, prompts: list[str], *, json_schema: dict | None = None,
                        max_tokens: int = 512, thinking: bool = False) -> list[str]
    def generate(self, prompts, **kw) -> list[str]        # bọc asyncio.run
```
- OpenAI-compatible `/chat/completions`, `httpx.AsyncClient`, `LLM_CONCURRENCY` luồng; nhiều URL (`LLM_BASE_URLS`) → **chia vòng theo chỉ số prompt** (`i % n_urls`, xác định).
- Tham số cố định: `temperature=0`, `seed=0`, `top_p=1`. Qwen3: không suy luận → `extra_body={"chat_template_kwargs":{"enable_thinking": false}}`; `thinking=True` → `true` và `max_tokens` do người gọi cấp.
- `json_schema` ⇒ `response_format={"type":"json_schema","json_schema":{"name":"x","schema":…,"strict":true}}`; endpoint từ chối ⇒ `{"type":"json_object"}` ⇒ cuối cùng parse + validate + **hỏi lại tối đa 1 lần**.
- Retry backoff mũ khi 429/5xx (`LLM_MAX_RETRIES`). Mọi lỗi cuối cùng ⇒ trả `""` cho prompt đó (mẫu hỏng), **không** ném ra ngoài.
- Kết quả **đúng thứ tự input** (gom theo chỉ số).
- `llm/fake.py`: `FakeLLM` trả theo bảng tra `{hash(prompt): output}` hoặc hàm callback; dùng cho test M3, M4, M9.

**Nghiệm thu:**
- [ ] `evaluate.py` với submission = đáp án tham chiếu ⇒ **PA = 1.000**; toàn `abstain` ⇒ **PA = 0.000**.
- [ ] `test_compare.py`: ≥ 3 ca mỗi type, có ca alias, ca sai dấu (`"Sting dầu 330ml"` **sai** so với `"Sting dâu 330ml"`), ca table/list có alias.
- [ ] `survey.py` sinh đủ file; `answers_stats.json` khớp phân bố đã biết (number 1884, percent 578, list 193, date 145, string 88, unanswerable 70, boolean 23, table 19 — tổng 3000).
- [ ] `as_of_stats.json` cho biết mỗi business có **1 hay nhiều** `as_of`; ghi kết luận vào `BACKLOG.md` (nếu nhiều thì quy tắc vàng 9 càng quan trọng).
- [ ] Client: 20 prompt song song ⇒ đúng thứ tự; mô phỏng 429 ⇒ retry thành công; JSON hỏng ⇒ chỉ mẫu đó rỗng.

---

### M1 — Ingest và làm sạch

**Tạo:** `ingest/reader.py`, `ingest/clean.py`, `tests/test_clean.py`
**IN:** đọc CSV/XLSX/SQLite → DataFrame sạch → DuckDB `t_*`.
**OUT:** hiểu nghĩa cột (M4).

```python
@dataclass
class RawTable: name:str; source:str; sheet:str|None; df:pd.DataFrame
def load_business(path: str) -> list[RawTable]
def load_questions(path: str) -> list[Question]
def find_header_row(df_raw, max_scan:int=15) -> int
def clean_table(df_raw, header_row:int) -> pd.DataFrame
def parse_number_series(s) -> pd.Series
def parse_date_series(s) -> pd.Series
def union_monthly_sheets(tables:list[RawTable]) -> list[RawTable]
def to_duckdb(tables, cache_path) -> None
```

Quy tắc:
- CSV: encoding thử `utf-8-sig, utf-8, cp1258, latin-1` (chọn cái đầu giải mã không lỗi, không chứa `�`); delimiter `csv.Sniffer` trên 20KB đầu, fallback `, ; \t |` chọn cái cho số cột ổn định nhất.
- Excel: đọc **mọi sheet**, bỏ sheet rỗng. **Sheet theo tháng của cùng một file có cùng tập cột phải union thành một bảng logic** (ghép dọc, thêm cột `__sheet`) — bắt buộc cho business có 12–24 sheet tháng (vd biz_102/103/112/115).
- SQLite: mọi bảng (trừ `sqlite_%`) và view; tên `t_<table>`.
- `find_header_row`: dòng đầu trong 15 dòng đầu mà ≥ 60% ô là chuỗi không phải số **và** dòng kế có ≥ 60% ô không rỗng; mặc định 0.
- Bỏ dòng rỗng hoàn toàn và dòng "tổng" (ô đầu chứa `tong|total|cong` không dấu, các cột id để trống). Tên cột trùng ⇒ hậu tố `_2`, `_3`.
- Ô gộp: forward-fill **chỉ** cột có ≥ 30% null và các giá trị không null lặp lại (cột nhóm).
- `parse_number_series` quyết định theo **cả cột**: bỏ `đ ₫ vnd VND` và khoảng trắng; hậu tố `k`×1e3, `tr|triệu|m`×1e6, `tỷ|ty|b`×1e9; nếu mẫu `\d{1,3}(\.\d{3})+(,\d+)?` đa số ⇒ `.` là nghìn, `,` thập phân; nếu `\d{1,3}(,\d{3})+(\.\d+)?` đa số ⇒ ngược lại; còn lại `float()`.
- `parse_date_series`: Excel serial (20000–60000 trong cột thuần số) → ISO → `dd/mm/yyyy` → `mm/dd/yyyy`. Có phần tử đầu > 12 ⇒ dd/mm; phần thứ hai > 12 ⇒ mm/dd; không quyết được ⇒ **dd/mm**. Cột là ngày khi ≥ 90% parse được. Cột có cả giờ ⇒ giữ `TIMESTAMP`.
- Chuỗi: `NFC` + strip; thêm cột `<col>__nd` (bỏ dấu, lower).
- Trùng dòng: drop khi **toàn bộ cột** trùng **và** có cột id bị trùng; ghi `dup_dropped` vào log.
- Cache: `CACHE_DIR/<sha256>.duckdb`, `sha256` = nối byte các file dữ liệu **đã sắp theo tên** + `SCHEMA_VERSION`.
- **Spike (0.5):** script `tests/test_duckdb_attach.py` xác nhận view trong `:memory:` trỏ tới DB `ATTACH READ_ONLY` chạy được; ghi kết quả vào `BACKLOG.md`.

**Nghiệm thu:**
- [ ] `parse_number_series(["1.200.000đ","1,2tr","500k"]) == [1200000,1200000,500000]`.
- [ ] Cột `["01/02/2026","13/02/2026"]` ⇒ tháng 2 (dd/mm).
- [ ] Chạy **44 business** (30 train + 14 public_test) không crash; mọi bảng ≥ 1 dòng; báo cáo số cột ngày/số parse được.
- [ ] Sheet nhiều tháng đã union: số dòng bảng union = tổng số dòng các sheet.
- [ ] Spike DuckDB đạt (hoặc ghi phương án copy vào bộ nhớ).

---

### M6 — Chuẩn hoá, entity linking, BM25, bộ lọc số  *(làm ngay sau M1, vì M3, M4 cần)*

**Tạo:** `text/normalize.py`, `text/entity_linker.py`, `text/bm25.py`, `text/numeric_filters.py`, `text/abbrev_vi.json`, `tests/test_text.py`
**OUT:** embedding; gọi LLM.

```python
def nd(s:str) -> str                       # NFC → bỏ dấu (đ→d) → lower → gộp khoảng trắng
def expand_abbrev(s_nd:str) -> str
def build_entity_index(con) -> EntityIndex          # từ v_products, v_customers, value_dict
def link_entities(q_nd:str, index) -> list[EntityMatch]
class BM25: topk(q_nd:str, n:int) -> list[tuple[int,float]]
def extract_having(q_nd:str) -> dict | None         # {"op":">","value":2000000}
```

- `ABBREV` khởi tạo: `sp→san pham, dc→duoc, ko→khong, k→khong (chỉ khi đứng riêng, không sau số), kh→khach hang, nv→nhan vien, hsd→han su dung, sl→so luong, dt→doanh thu, ln→loi nhuan, tt→thanh toan, ntn→nhu the nao, bn→bao nhieu, hh→hang hoa`. **Bắt buộc mine thêm từ câu hỏi train** (`dthu, bnhiu, vs, giùm, moi…`) vào `abbrev_vi.json` (dev step; **không** dùng câu test). Đo: token lạ còn sót trên câu train **< 5%**.
- Entity: n-gram 1..5 token, bỏ n-gram toàn stopword (`la, cua, bao nhieu, nhat, thang, tuan, …`); điểm = `max(token_set_ratio, partial_ratio)/100` (+ thưởng nếu khớp token đầu); giữ ≥ 0.8; ưu tiên span dài và điểm cao; mỗi span top-3; khớp cả sản phẩm và danh mục ⇒ giữ cả hai, gán `kind`.
- **Tên giữ dấu** trong index (để trả đúng tên), **so khớp** trên dạng bỏ dấu.
- `extract_having`: nhận `qua|hon|tren|lon hon|nhieu hon` ⇒ `>`; `duoi|it hon|nho hon` ⇒ `<`; `tu N tro len` ⇒ `>=`; `tu N tro xuong` ⇒ `<=`. Số: `\d+([.,]\d+)?` kèm `k|nghin|tr|trieu|ty` (×1e3, ×1e3, ×1e6, ×1e6, ×1e9). Không có số ⇒ `None`.
- `BM25`: tự cài (k1=1.5, b=0.75) trên câu train đã `nd`, không thư viện ngoài.

**Nghiệm thu:** `nd("Cà phê sữa")=="ca phe sua"`, `nd("Đường")=="duong"`; `extract_having("khach mua tren 2 trieu")=={"op":">","value":2000000}`; `extract_having("tu 3 don tro len")=={"op":">=","value":3}`; ≥ 90% tên sản phẩm được nhắc trong câu train link đúng mã SP ở top-1 (đo trên câu đáp án string/list, **sau khi M4 xong**); token lạ còn sót < 5%.

---

### M2 — Time resolver + lịch âm

**Tạo:** `timeutil/calendar_vi.py`, `timeutil/resolver.py`, `tests/test_time.py`
**OUT:** tính số liệu nghiệp vụ.

```python
@dataclass
class Calendar: rows:list[dict]; by_date:dict; lunar_index:dict
def load_calendar(path:str) -> Calendar            # đọc theo survey/calendar_head.txt
def lunar_to_solar(cal, year:int, month:int, day:int, leap:bool=False) -> date | None   # tra bảng, không tự tính thiên văn
def tet_window(cal, tet_year:int, knobs:Knobs) -> tuple[date,date] | None
def resolve_time(text_nd:str, as_of:date, knobs:Knobs, cal:Calendar) -> tuple[list[TimeWindow], list[str]]
```

`load_calendar` là adapter theo cột thực của `calendar.csv` (xem `survey/calendar_head.txt`); tra cứu theo bảng, thiếu ngày ⇒ trả `None` ⇒ cụm Tết vào `unresolved`. Cửa sổ Tết của năm âm lịch Y: `start = lunar(Y−1, 12, 23)` (không có 23 ⇒ ngày cuối tháng Chạp), `end = lunar(Y, 1, 10)`; đọc từ `knobs.tet_start/tet_end`.

`resolve_time` nhận `text_nd` đã bỏ dấu. Bảng pattern (cụm dài trước; tuần theo `knobs.week_start`):

| Cụm (không dấu) | Khoảng |
|---|---|
| `hom nay` | [as_of, as_of] |
| `hom qua` | [as_of−1, as_of−1] |
| `tuan nay` | [đầu tuần chứa as_of, as_of] |
| `tuan (roi\|truoc)` | **trọn** tuần liền trước (T2→CN), không cắt theo hôm nay |
| `thang nay` | [mùng 1, as_of] |
| `thang (roi\|truoc)` đứng riêng | cả tháng liền trước |
| `thang (roi\|truoc)` làm **base** của kỳ chính kết thúc ở hôm nay | cắt **cùng số ngày** của tháng trước (`trunc_same_days=True`; tháng trước không có ngày đó ⇒ đến hết tháng trước). Kỳ chính không kết thúc hôm nay ⇒ base = cả tháng trước |
| `quy nay` / `quy (roi\|truoc)` | [đầu quý, as_of] / cả quý trước |
| `nam nay` / `nam (ngoai\|roi\|truoc)` | [1/1, as_of] / cả năm trước |
| `(\d+) ngay (qua\|gan day\|vua roi)` | [as_of−N+1, as_of] nếu `last_n_includes_today` |
| `(\d+) tuan qua`, `(\d+) thang qua` | tương tự theo tuần/tháng |
| `thang (\d{1,2})(/(\d{4}))?` | tháng đó; không nêu năm ⇒ năm của as_of nếu tháng ≤ tháng as_of, ngược lại năm trước |
| `den het ngay X`, `tinh den het ngay X` | `kind="cumulative"`, `end=X` (lũy kế từ đầu dữ liệu) |
| `ca sang` / `ca chieu` | `kind="shift"`, `shift="sang"/"chieu"` (khoảng ngày lấy từ cụm thời gian đi kèm, mặc định `thang nay`); so ca chiều với ca sáng ⇒ `main`=chiều, `base`=sáng, cùng khoảng ngày |
| `cung ky (nam ngoai\|nam truoc)` | dịch mọi khoảng chính lùi 1 năm (29/2→28/2), nhãn `yoy` |
| `cung ky (thang\|tuan) (truoc\|roi)` | dịch cùng độ dài lùi 1 tháng/tuần, nhãn `prev` |
| `tet (nam ngoai\|nam truoc)` | cửa sổ Tết của năm dương `as_of.year−1` |
| `tet (nay\|vua roi\|gan nhat)` hoặc `tet` trơn | cửa sổ Tết gần nhất có `start <= as_of` |
| `thu (2..7\|cn) (tuan roi\|tuan nay)` | ngày đó trong tuần tương ứng |
| nhiều tháng liệt kê ("thang 1/2026, 2/2026 va 3/2026", "3 thang 4,5,6/2026") | một `TimeWindow` mỗi tháng, nhãn theo thứ tự câu: `main`(=p1), `p1..pn` |
| hai cụm + `so voi\|tang\|giam\|bao nhieu %` | nhãn `main` (cụm đứng trước), `base` (cụm đứng sau) |

Nhãn mặc định `main`. Câu chứa từ thời gian (`tuan|thang|quy|nam|ngay|tet|hom`) mà không pattern nào khớp ⇒ cụm vào `unresolved`. **Luật "qua/hơn N không gồm N" KHÔNG thuộc resolver** (đó là `having`, M6).

**Nghiệm thu** (as_of = 2026-03-04, Thứ Tư):
- [ ] `tuan roi` ⇒ 2026-02-23..2026-03-01
- [ ] `thang nay` ⇒ 2026-03-01..2026-03-04
- [ ] `thang truoc` đứng riêng ⇒ 2026-02-01..2026-02-28
- [ ] `thang nay` + `thang truoc` ⇒ base 2026-02-01..**2026-02-04**, `trunc_same_days=True`
- [ ] `7 ngay qua` ⇒ 2026-02-26..2026-03-04
- [ ] `thang nay` + `cung ky nam ngoai` ⇒ 2025-03-01..2025-03-04
- [ ] `ca chieu` ⇒ `kind="shift"`, `shift="chieu"`; `tinh den het ngay 2026-03-01` ⇒ `kind="cumulative"`
- [ ] "thang 1/2026, 2/2026 va 3/2026" ⇒ 3 windows đúng thứ tự
- [ ] Cửa sổ Tết khớp ngày dương lấy tay từ `calendar.csv` cho ≥ 3 năm; năm nhuận; đầu năm (as_of 2026-01-02, `thang truoc` ⇒ tháng 12/2025)

---

### M3 — Rulebook → Knobs + RuleSpec

**Tạo:** `rules/knobs.py`, `rules/rulebook_parser.py`, `tests/test_rulebook.py`
**OUT:** tạo view/metric mới.

```python
KNOB_DOMAINS: dict[str, list]      # tên knob → tập giá trị hợp lệ
def parse_rulebook(text:str, train_text:str|None, llm) -> RuleSpec
```

Thuật toán (8 bước):
1. Tách rulebook thành câu (theo dòng, dấu `.`, bullet); chuẩn hoá bằng `nd`.
2. Có `train_text` (file dữ liệu trong repo `rules/train_rulebook.md`, không keyed theo business): tính `sha1` mỗi câu đã chuẩn hoá; câu **có trong train** ⇒ giữ knob mặc định; chỉ câu **mới/đổi** đi tiếp.
3. Với mỗi câu đi tiếp, chọn knob liên quan theo từ khoá không dấu: `doanh thu|revenue`→nhóm `revenue_*`; `vat|thue`→`revenue_include_vat`; `van chuyen|ship|giao hang`→`revenue_include_shipping`; `voucher|ma giam gia`→`revenue_deduct_order_voucher`; `huy|cancel`→`exclude_cancelled`; `tra hang|hoan hang|return`→`returned_policy`; `ban chay`→`bestseller_metric`; `tuan`→`week_start, this_week`; `thang nay|thang truoc`→`this_month`; `gia von|cost`→`cost_method`; `tet|thang chap|mung`→`tet_start/tet_end`; `ca sang|ca chieu|gio`→`shift_*`.
4. Mỗi (câu, knob) gọi LLM **trắc nghiệm** (prompt mẫu bên dưới), schema `{"choice": int}`, parse + validate, hỏi lại tối đa 1 lần. Knob bool: lựa chọn `[true, false, "không liên quan"]`.
5. Câu không khớp knob nào nhưng chứa từ khoá nghiệp vụ lạ (`tinh|bao gom|khong tinh|loai tru|bo qua`) ⇒ `unmapped`.
6. Validate: mọi giá trị ∈ `KNOB_DOMAINS`, sai ⇒ về mặc định + `unmapped`.
7. **Bước 8 — features/domains:** quét từ khoá để điền `RuleSpec.features` (3.3) và `domains`: `sua xe|tho|bao hanh`→`repair_ticket, warranty_service`; `tra gop|ky gop|tra cham`→`installment`; `thu may cu|thu cu`→`trade_in`; `ngay dang ky|thanh vien`→`member_since`; `size|so`→`size_breakdown`; `ty trong|nhom hang`→`product_group_share`; `khung gio|cao diem`→`peak_hour`; `nhieu ngay co mua|khach than thiet`→`loyal_customer`; `topping`→`topping_split`; `tien mat theo ca|thu ngan`→`cash_shift_report`; `cong no|no`→`debt_rules`; `gia von`→`cost_rules`.
8. Ghi `RuleSpec` vào log.

**Prompt MCQ mẫu (dùng chung cho M3 và M4):**
```
Câu quy tắc: "{sentence}"
Tham số cần xác định: {knob_name}
Chọn đúng MỘT lựa chọn. Chỉ trả JSON {"choice": <số>}.
{n}. {option_n}   (mỗi lựa chọn một dòng, đánh số từ 0)
```

**Nghiệm thu:**
- [ ] Parse `train/rulebook.md` ⇒ đúng `Knobs` mặc định (đối chiếu `survey/rulebook_sentences.txt`; nếu rulebook train nói khác đề thì **sửa mặc định** trong `dtypes.py` và ghi `BACKLOG.md`).
- [ ] Rulebook sửa tay (tuần bắt đầu Chủ nhật, tính cả phí ship) ⇒ knob tương ứng.
- [ ] Parse `public_test/rulebook.md` ⇒ `RuleSpec` khác train **đúng** ở các ngành mới và luật thêm/bớt; **mọi câu** ở cả hai split đều được gán knob/feature hoặc nằm trong `unmapped` (in danh sách `unmapped`, người dev duyệt).
- [ ] Test dùng `FakeLLM`.

---

### M4 — Canonicalize + mapper + bất biến + views  ← **rủi ro lớn nhất**

**Tạo:** `schema/roles.py`, `schema/archetypes.py`, `schema/canon.py`, `schema/mapper.py`, `schema/invariants.py`, `schema/views.py`, `schema/card.py`, `tests/fixtures/expected_roles.json`, `tests/fixtures/make_mini.py`, `tests/test_mapper.py`, `tests/test_views.py`, `docs/m04.md`
**IN:** map cột → cột canonical, canonicalize ra `c_*`, bất biến, view `v_*` (lõi).
**OUT:** SQL metric (M5); view cho ngành mới (M15).

#### A. Catalog archetype (phát hiện theo **cấu trúc**, không theo business_id)

| Mã | Dấu hiệu | Business train |
|---|---|---|
| `A_flat` | 1 file, cột có qty + giá + ngày + tên hàng | 101,110,114,125,107,113,116,126 |
| `B_monthly` | 1 file nhiều sheet tháng + file danh mục/quy đổi | 102,103,104,109,121,112,130 |
| `C_norm_csv` | `don_hang` + `chi_tiet_don` + `khach_hang` + `san_pham` (+`thanh_toan`) | 111,127,129 |
| `D_erp` | ≥ 8 file: hoá đơn, chi tiết, sản phẩm, khách, nhập, quỹ, tồn | 106,119,120,122,124,128 |
| `E_retail_suite` | bán hàng + danh mục/giá + nhập + tồn + giao hàng/công nợ | 105,108,115,117,118 |
| `G_sqlite` | `.sqlite` (≈17 bảng POS) | 123 |
| `H_repair`, `I_phone`, `J_baby` | sổ sửa xe / sổ điện thoại / mẹ và bé | chỉ ở public_test (M15) |
| `UNKNOWN` | không khớp | — |

`detect_archetype(tables) -> (code, confidence)` chấm theo *tên file/bảng chuẩn hoá (nd, bỏ khoảng trắng)* + *tập cột*. Dưới ngưỡng ⇒ `UNKNOWN`. Danh sách business ở bảng chỉ để người dev tạo nhãn kiểm thử, **cấm** dùng trong code.

**`UNKNOWN`:** không dùng adapter riêng. Chạy mapper tổng quát (mục C) trên mọi bảng; tìm bảng "giống dòng bán" (có đồng thời cột số lượng, cột tiền, cột ngày, cột tên/mã hàng) ⇒ dựng `c_lines`/`c_orders` theo kiểu `A_flat`; không tìm được ⇒ **không tạo `c_lines`**, `schema_conf = min(schema_conf, 0.3)`, `data_caps` gần như rỗng ⇒ đường 1 vô hiệu, chỉ đường 2 trên `t_*` (M10).

#### B. Từ điển role (`schema/roles.py`)

Namespace duy nhất: **tên cột canonical** của `c_*` (4.1). Mỗi cột có `NAME_TOKENS` (không dấu) và `VALUE_TESTS`. Tên đã thấy trong dữ liệu thật (khởi tạo, mở rộng sau survey):

| cột canonical | tên điển hình |
|---|---|
| `order_id` | `Mã hóa đơn, MaHoaDon, Mã đơn hàng, Đơn số, Mã bill, Mã đơn` |
| `order_date` / `order_ts` | `Ngày đặt hàng, Thời gian, Ngày, NgayBan, Ngày HĐ, Ngày tháng` (có giờ ⇒ `order_ts`) |
| `status_raw` | `Trạng thái đơn hàng, Trạng thái, Xử lý, Kết quả, Trạng thái xử lý, Status` |
| `qty` | `Số lượng, so_luong, SL, Số lượng bán` |
| `qty_base` | `Số lượng quy đổi, Quy ra ĐV lẻ, SL quy đổi, Số lượng lẻ` |
| `line_amount` | `Thành tiền, Tổng tiền, Thanh_tien, T.Tiền, Tiền, Amount` |
| `unit_price` | `Đơn giá, Giá đơn vị, don_gia, Giá sản phẩm, Giá bán` |
| `line_discount` | `Giảm giá, Chiết khấu dòng, Khấu trừ` |
| `line_cost_total` | `Giá vốn, Giá vốn lúc bán, Giá vốn hiện tại` (**đơn vị hay tổng** quyết bằng bất biến `inv_cost`) |
| `product_name` | `Tên sản phẩm, Nội dung, Hàng, Tên hàng, Tên hàng hóa, Mặt hàng` |
| `customer_name` / `customer_key` | `Tên khách hàng, Khách hàng, Đối tác, Bên mua, Khách` / `Mã KH, Mã khách hàng, ma_kh, Số KH` |
| `pay_method` | `Phương thức thanh toán, Phương thức TT, PTPP` |
| `channel` | `Kênh bán, Nguồn, Bán qua` |
| `customer_group` | `Nhóm khách hàng, Nhóm, Loại hình khách` |
| `employee` | `Mã NV bán, Người tạo, Thợ, Người giao hàng` |
| `expiry_date` | `Hạn sử dụng, HSD, HanSuDung` |
| `unit_factor` | `Quy đổi, Hệ số, HeSoQuyDoi, Tỉ lệ quy đổi` |
| `order_debt_total` | `Còn nợ, Còn lại, Công nợ, Dư nợ` |
| `order_paid` | `Khách đã trả, Đã thanh toán, Đã thu` |
| `ph_new/ph_old` | `Giá mới, Giá cũ` (bảng `lich_su_gia`, `BangGia`) |

Sau `survey/columns.csv`: mở rộng `NAME_TOKENS` tới khi **≥ 95% cột có nhãn tay** trong `tests/fixtures/expected_roles.json` được heuristic tìm đúng. Nhãn tay cho **≥ 2 business mỗi archetype lõi** (tối thiểu 12 business) — ghi trong `docs/m04.md` danh sách đã chọn.

#### C. `mapper.py`

```python
def map_business(tables:list[RawTable], readme:str, llm) -> list[MappingCandidate]   # sort theo score giảm dần
```
1. **Phân loại bảng** theo thực thể: `table_score = Σ best_role_score` trên cột bắt buộc của thực thể; gán thực thể điểm cao nhất nếu ≥ 0.5.
2. **Chấm cột:** `score = 0.6*name_score + 0.4*value_score`; `name_score` = `rapidfuzz.partial_ratio/100` trên token không dấu; `value_score` = `VALUE_TESTS` (kiểu, phân phối, cardinality, tỉ lệ nguyên, `qty×giá≈tiền`).
3. **Cột chưa chắc** (top1 − top2 < 0.15 hoặc top1 < 0.5): LLM trắc nghiệm (prompt MCQ ở M3; nội dung: tên bảng, tên cột, 8 giá trị mẫu, đoạn README có nhắc cột, 4 vai ứng viên + "không có"), **một lần cho cả business**, `thinking=True`.
4. **Giá trị trạng thái** (cột `status_raw`, cờ trả hàng): từ điển không dấu `cancelled = huy|cancel|void|that bai|failed`, `returned = hoan|tra hang|return|refund`; giá trị lạ ⇒ LLM `[cancelled, returned, valid]`. Lưu `status_invalid`.
5. **Khoá join:** containment `|A∩B|/|B| ≥ 0.95` + tên gần nhất.
6. Sinh tối đa 3 mapping ứng viên (đổi phương án top-2 ở cột margin nhỏ nhất); chọn theo tổng penalty (mục E).
7. **README:** tìm câu về quy đổi đơn vị ("1 thùng = 24 lon"), tên cột đặc biệt ⇒ đưa vào `docs`/ghi chú; parse quy đổi bằng regex `1\s*(\w+)\s*=\s*(\d+)\s*(\w+)` ⇒ bổ sung `c_units` nếu dữ liệu không có bảng quy đổi.

#### D. `canon.py` — canonicalize (hấp thụ khác biệt archetype)

```python
def canonicalize(tables, mapping, archetype) -> dict[str, pd.DataFrame]   # trả c_* (4.1)
```
Quy tắc chung:
- Bảng phẳng: `order_id` = cột id đơn nếu có, **không có** ⇒ `'R' || row_number()` theo thứ tự file; mỗi dòng = một đơn một dòng.
- Phiếu + chi tiết: join theo khoá join đã chọn; thuộc tính đơn (ngày, khách, trạng thái) lấy từ phiếu.
- Sheet theo tháng: đã union ở M1.
- `qty_base`: ưu tiên cột quy đổi sẵn; không có ⇒ `qty × unit_factor` từ `c_units`; không có bảng quy đổi ⇒ `qty_base = qty` (**ghi cờ `qty_base_assumed`**).
- `is_service`: tên sản phẩm chứa `phi phuc vu|phi dich vu|service`.
- `is_walkin`: tên khách rỗng hoặc chứa `khach le|vang lai|khach vang lai|khong ten`.
- Tiền chuẩn `DECIMAL(20,4)`; ngày `DATE`; chuỗi NFC.
- `line_cost_total`: nếu bất biến `inv_cost` kết luận cột là giá vốn **đơn vị** ⇒ nhân `qty_base`.

#### E. `invariants.py` — mỗi hàm trả `(passed, penalty, info)`

- `inv_line_math`: tỉ lệ dòng có `|qty*unit_price − line_discount − line_amount| ≤ 1%·line_amount`; pass ≥ 0.95. Không pass ⇒ thử biến thể không trừ giảm giá và `line_amount = qty*unit_price*(1+vat_rate)`; biến thể pass ⇒ ghi cờ `discount_already_applied` hoặc `line_amount_includes_vat`.
- `inv_order_total`: `order_total − Σ line_amount` so với `shipping_fee`, `vat_amount`, `−order_voucher` ⇒ cờ `order_total_includes_ship/vat/voucher`.
- `inv_qty_base`: `qty_base ≈ qty × unit_factor` ≥ 95% ⇒ cờ `qty_base_is_converted`.
- `inv_cost`: `line_cost_total` hợp lý (≤ line_amount ở ≥ 90% dòng) hay là đơn vị ⇒ cờ `cost_is_unit`.
- `inv_debt`: `order_debt_total − Σ thanh toán` khớp cột "Còn nợ/Còn lại" (nếu có) ≥ 95% ⇒ cờ `debt_from_orders`.
- `inv_dates`: tỉ lệ parse ≥ 0.9; khoảng ngày 12–30 tháng; đếm đơn có `order_date > as_of` (chỉ log).
- `inv_join`: dòng mồ côi ≤ 2%. `inv_products`: sản phẩm không có trong master ≤ 2%.
- `schema_conf = 1 − min(1, Σ penalty)` của mapping được chọn. Cả 3 ứng viên `< 0.5` ⇒ giữ cái tốt nhất, `schema_conf` thấp (M12 hạ p cho **mọi** câu của business).

#### F. `views.py`

```python
def build_context(biz_dir:str, knobs:Knobs, rules:RuleSpec, llm) -> BizContext
def build_views(con, knobs:Knobs, flags:dict) -> None     # tạo v_* theo 4.1, KHÔNG có as_of
```
`build_context`: M1 → mapping → canonicalize → bất biến → ghi `c_*` vào cache → mở `:memory:` + `ATTACH` → `build_views` → `value_dict` → `entity_index` → `card` (4.11) → `data_caps` (3.2) → `ctx`. Có cache `c_*` theo `sha256` thì bỏ qua các bước đầu.

**Nghiệm thu:**
- [ ] Heuristic tìm đúng ≥ 95% cột có nhãn trên ≥ 2 business mỗi archetype lõi.
- [ ] Mini-fixture (`make_mini.py`) có: 1 đơn huỷ, 1 đơn có hàng trả, 1 đơn sau `as_of`, 2 sản phẩm bằng điểm bán, 1 khách lẻ, 1 dòng phí phục vụ, 1 đơn COD, 1 khách có thanh toán trả dần ⇒ `v_lines` không chứa đơn huỷ/trả/COD-nợ đúng luật; `v_orders_all` giữ đủ.
- [ ] `SELECT SUM(line_amount_net) FROM v_lines WHERE …` khớp đáp án tham chiếu cho các câu doanh thu đơn giản (kiểm tự động ở M8).
- [ ] Bảng phẳng ⇒ `order_id` sinh **ổn định** qua hai lần chạy.
- [ ] Archetype `UNKNOWN` (bảng giả lạ) ⇒ `schema_conf ≤ 0.3` và không crash.
- [ ] Mọi `v_*` không chứa tham chiếu `as_of` (test `grep`).

---

### M5 — Metric registry + compile_spec + executor

**Tạo:** `engine/registry.py`, `engine/templates.py`, `engine/compile.py`, `engine/lots.py`, `engine/executor.py`, `engine/sandbox.py`, `tests/test_metrics.py`, `tests/test_compile.py`, `docs/m05.md`
**IN:** registry 4.3, khung T1–T7 (4.5), `validate_spec`, `compile_spec`, `run_sql`.
**OUT:** prompt (M9), quyết định trả lời (M12), metric ngành mới (M15).

```python
def validate_spec(spec:Spec, ctx:BizContext, windows:list[TimeWindow], entities:list[EntityMatch]) -> list[str]   # trả danh sách lỗi
def compile_spec(spec:Spec, ctx:BizContext, knobs:Knobs, windows:list[TimeWindow], as_of:date) -> CompiledPlan
def run_sql(con, sql:str, timeout_s:float=20, max_rows:int=1000) -> ExecResult
```

- `validate_spec` kiểm 6 ràng buộc ở 4.4. `compile_spec` chọn khung theo bảng 4.5, **luôn** chèn `AND s.date <= as_of` (4.7), dịch `filters` thành vị từ (bảng ánh xạ field→cột `v_*` trong `engine/compile.py`; `product`/`customer` so theo mã `code`, các field khác so theo cột nguyên giá trị), `having` thành `HAVING`.
- **Giá vốn:** knob `cost_method`. `line_cost` (mặc định, **rulebook §5: lấy giá vốn ghi trên dòng bán, không tự tính lại**) → `profit` dùng `line_cost_total`. `wavg_by_lot` / `wavg_up_to_sale_date` chỉ dùng khi shop không ghi giá vốn dòng: `unit_cost(p) = Σ(lot_qty×lot_cost)/Σlot_qty` trên các lô `lot_date ≤ as_of` (biến thể thứ hai: `≤ order_date`). Cờ quyết định ở M8.
- **`run_sql`:** chỉ nhận SQL bắt đầu bằng `SELECT` hoặc `WITH`; từ chối nếu chứa (không phân biệt hoa thường) `ATTACH|COPY|INSTALL|LOAD|PRAGMA|CREATE|INSERT|UPDATE|DELETE|DROP|read_csv|read_parquet|COPY TO`; chạy trong thread, `con.interrupt()` khi quá `timeout_s`; lỗi ⇒ `ExecResult(error=…)`, **không raise**.
- `engine/lots.py`: `fifo_allocate(...)`, `remaining_by_lot(con, cutoff)` (4.5 T6).
- **Đối chiếu rulebook bắt buộc:** tạo `docs/rulebook_map.md`: mỗi metric/khung ↔ **số câu** trong `survey/rulebook_sentences.txt` định nghĩa nó. Metric nào không có câu tương ứng ⇒ ghi "không có căn cứ rulebook" và hạ ưu tiên (rơi về đường 2).

**Nghiệm thu:**
- [ ] Mỗi metric trong 4.3 có test trên mini-fixture; tie-break `code ASC` đúng (kể cả `order=asc`); T2 trả `limit+1` dòng.
- [ ] T3: `base=0` ⇒ `value` NULL; `compare_mode=diff` ra số âm khi kém.
- [ ] T4: `series_increasing` chặt chẽ (bằng nhau ⇒ False).
- [ ] T6: `debt` loại COD/TMĐT, khách lẻ có trong tổng nhưng không có trong xếp hạng; `stock` khớp cả hai cách (snapshot, lô−bán) trên fixture.
- [ ] T7: mẫu số là toàn cửa hàng, gồm khách lẻ và dòng phí phục vụ.
- [ ] Mọi SQL do `compile_spec` sinh có `<= DATE 'as_of'`; test với đơn sau `as_of` ⇒ bị loại.
- [ ] Sandbox chặn `DROP TABLE`, timeout đúng.
- [ ] `validate_spec`: nhãn thời gian lạ, filter ngoài danh sách, metric–subject sai ⇒ lỗi.

---

### M7 — Formatter

**Tạo:** `fmt/formatter.py`, `tests/test_formatter.py`

```python
def to_submission(plan:CompiledPlan, result:ExecResult, spec:Spec|None, out_type:str, ctx, knobs, windows) -> Answer
```
Luật (đã chốt):
- `string`: tên **master** (fallback tên trên dòng bán); giữ nguyên dấu; mã SP chỉ là alias, **không** là đáp án.
- `list`: theo thứ tự truy vấn (đã tie-break); phần tử số hoặc chuỗi; trả `limit` phần tử đầu (bỏ dòng `limit+1`); ít hơn `limit` ⇒ trả hết.
- `number`: tiền ⇒ `int` VND, `Decimal ROUND_HALF_UP` về đồng; số khác ⇒ 2 chữ số thập phân; JSON number, không đơn vị, không dấu nghìn.
- `percent`: giá trị từ T3/T7 làm tròn 2 chữ số; `old==0`/NULL ⇒ **abstain**; giảm ⇒ số âm (ví dụ `-12.45`, **không** `-0.1245`).
- `date`: `YYYY-MM-DD`; câu theo tháng (subject `month`, hoặc nhãn cửa sổ là trọn một tháng) ⇒ `YYYY-MM`.
- `boolean`: `bool` (từ `post`).
- `table`: `{"columns":[snake_case_không_dấu…], "rows":[[…]]}`; cột đầu = tên đối tượng; thứ tự cột theo câu hỏi.
- Rỗng: `aggregate_total` + mọi entity tồn tại ⇒ `0`; rank/lookup rỗng ⇒ **abstain**.
- **Hoà ở biên** (4.8) ⇒ **abstain**.
- `unanswerable`: `{"type":"unanswerable","reason":"…"}`.

**Nghiệm thu:** test mọi type; tie-break `code` tăng dần; percent `-12.45`; `k` > số ứng viên; date tháng ra `YYYY-MM`; hoà ở hạng 1 ⇒ abstain; list/table qua alias (dùng `is_correct`).

---

### M8 — Enumerate-and-match + ngân hàng ← **CỔNG G2**

**Tạo:** `dev/tag_group.py`, `dev/enumerate_match.py`, `dev/build_bank.py`, `tests/test_enumerate.py`, `docs/m08.md`
**IN:** sinh spec ứng viên bằng luật → thực thi → khớp đáp án → lưu bank + unmatched.
**OUT:** **không dùng LLM** trong vòng lặp dev. (Bước LLM bootstrap chạy sau M9, phải ghi rõ trong log.)

**Mục đích:** (a) kiểm chứng toàn bộ phần deterministic (view, registry, knob, resolver) **trên đáp án thật**, (b) tìm intent chưa phủ, (c) tạo ngân hàng few-shot đã xác minh bằng thực thi. Nếu phần này không tái hiện được đáp án train thì thêm LLM chỉ che lỗi.

**`tag_group(question_nd) -> str`** gán nhóm theo từ khoá để đo cổng: `core` (`doanh thu|ban chay|so don|so luong|tuan|thang|so voi|tang|giam`), `tail` (`no|ton|gia von|loi nhuan|het han|thuoc|xi mang|vat lieu|tang gia`), `null` (đáp án null).

**Thuật toán sinh ứng viên (pseudocode):**
```
for q in train_questions(dev):
    windows, unresolved = resolve_time(...)
    entities = link_entities(...)
    having = extract_having(...)
    cand_metrics = keyword_metrics(q_nd)          # doanh thu→revenue; bao nhieu (cai|ly|chiec|...)/so luong→qty;
                                                  # bao nhieu don→orders; khach→customers; loi nhuan|loi gop→profit;
                                                  # ton→stock; gia tri ton→stock_value; no→debt; tuoi no→debt_age;
                                                  # het han→expiring; nhap→import_amount; gia nhap→import_avg_price;
                                                  # ty le huy→cancel_rate; trung binh don→aov;  mơ hồ ⇒ liệt kê TẤT CẢ hợp lệ
    cand_intents = keyword_intents(q_nd)          # nhat|top|nhieu nhat|it nhat → rank_top/lookup_single (limit 1 hoặc k từ "top k");
                                                  # so voi|tang|giam → compare_periods; tang lien tuc|giam lien tuc → boolean_check+series;
                                                  # thang nao|ngay nao + nhat → compare_series/lookup (subject window/day/month);
                                                  # co ... khong → boolean_check; liet ke|danh sach|nhung → filter_list;
                                                  # ty trong|chiem bao nhieu % → group_share; ty le huy → cancel_rate
    cand_subjects = keyword_subjects(q_nd, entities)   # nhom hang→category; khach→customer; mat hang|sp→product; ngay→day; thang→month; kenh→channel; thanh toan→pay_method
    cand_time = assign_windows(windows)           # >1 cụm: thử cả hai cách gán main/base
    cand_filters = filters_from(entities, value_dict, q_nd)    # thực thể → filters; từ điển giá trị cột (kênh, PT thanh toán, nhóm khách) khớp nd
    cand_knobs = [default] + variants(bestseller_metric ∈ {qty,revenue,orders}, returned_policy, cost_method)
    specs = itertools.product(...)  sắp theo (số slot mơ hồ tăng dần, thứ tự từ điển) ; cắt 24
    for s in specs:
        errs = validate_spec(...); if errs: continue
        plan = compile_spec(...); res = run_sql(...); ans = to_submission(...)
        if is_correct(ans, ref): keep(s); break          # ưu tiên spec ÍT slot mơ hồ nhất
```
- Slot `output` suy từ `metric`+câu hỏi: tổng ⇒ number; "%" ⇒ percent; "danh sách/top k" ⇒ list; "là gì/nào" ⇒ string; "ngày nào" ⇒ date; "có … không" ⇒ boolean; "bảng" ⇒ table.
- Nhiều spec cùng đúng ⇒ chọn theo thứ tự sinh (đã sort ⇒ tái lập).
- Biến thể knob nào giúp khớp nhiều câu hơn mặc định ⇒ ghi `survey/knob_findings.md` (nếu lệch `DEFAULT` ⇒ sửa `dtypes.py` theo rulebook thật và ghi `BACKLOG.md`).

**Ghi:** `bank.jsonl` (id, business, `question_nd`, `spec`, `metric`, `intent`, `window_labels` — nhãn + mô tả ngắn như "main = tuần rồi", **không** ghi ngày) và `unmatched.jsonl` (câu, đáp án tham chiếu, lý do `no_spec | exec_error | wrong_value`, nhóm). `build_bank.py` dựng `bank_index.pkl` (BM25 + nhãn intent/metric cho kNN).

**Vòng sửa lỗi (chỉ nhìn dev unmatched):** chạy → nhóm theo lý do → chọn **đúng một** nhóm → sửa một trong: từ điển viết tắt | `NAME_TOKENS` | định nghĩa metric | thêm intent/khung → ghi `survey/fix_log.md` (ngày, nhóm, sửa gì, số câu ảnh hưởng) → chạy lại. Không sửa nhiều nhóm một lúc.

**Cổng G2 (tất cả phải đạt):**
- Dev: nhóm `core` ≥ **95%**; nhóm `tail` ≥ **80%**; tổng ≥ **90%** (trên câu có đáp án khác null).
- **Holdout** (chỉ số tổng hợp): tổng thấp hơn dev **không quá 8 điểm**. Lớn hơn ⇒ đang overfit từ điển ⇒ quay lại sửa theo hướng tổng quát (không phải theo từng câu).
- Phần dưới ngưỡng liệt kê lý do trong `survey/calibration.md`.

**Nghiệm thu:** chạy xong 3000 câu train không crash; `bank.jsonl` ≥ 90% câu có đáp án; `unmatched.jsonl` phân nhóm theo lý do; `bank_index.pkl` dựng được.

---

### M9 — Đường 1 (Spec)

**Tạo:** `llm/schemas.py`, `llm/prompts.py`, `paths/path1_spec.py`, `tests/test_path1.py`, `docs/m09.md`
**OUT:** prompt đường 2 (M10); quyết định abstain (M12).

`SPEC_SCHEMA` = JSON Schema của 4.4 với `enum` cho `intent, metric, subject, output, order, filters.field, filters.op, having.op, params.*`; `MCQ_SCHEMA = {"choice": integer}`; `SQL_SCHEMA = {"answer_type": enum, "sql": string}`.

```python
def run_path1(q:Question, ctx:BizContext, knobs:Knobs, windows, entities, bank, llm, k:int=K1) -> list[Candidate]
```
1. `q_nd = expand_abbrev(nd(q.text))`. Top-18 ví dụ gần nhất từ bank bằng BM25 (loại ví dụ cùng business khi đang đo holdout).
2. Chia 18 ví dụ thành **3 bộ 6** round-robin (bộ 1: hạng 1,4,7…; bộ 2: 2,5,8…; bộ 3: 3,6,9…).
3. Dựng prompt (template dưới) cho mỗi bộ; **câu hỏi hiện tại giữ bản gốc có dấu**.
4. `llm.generate(prompts, json_schema=SPEC_SCHEMA)` greedy; parse; **`validate_spec`** (mẫu vi phạm bị loại); chuẩn hoá (`filters` sắp theo `(field,op,values)`).
5. `compile_spec → run_sql → to_submission`; mẫu lỗi bị loại.
6. Vote theo `canon_key(answer)`; trả `Candidate(votes,k)`.
7. Cả ba mẫu hỏng hoặc `intent=="other"` ⇒ trả `[]` (đường 2 làm).
8. **Câu dễ (tối ưu, bật sau):** kNN intent (nhãn top-1 BM25) = intent mẫu đầu và mọi entity ≥ 0.95 ⇒ chỉ 1 mẫu, `k=1`. Mặc định ban đầu luôn `k=3`.

**Vì sao k mẫu với bộ ví dụ khác nhau (không đổi nhiệt độ):** lỗi của model nhỏ khi cùng prompt rất tương quan; đa dạng hoá bằng ví dụ cho lỗi ít tương quan hơn. Vote theo **kết quả thực thi** (không theo văn bản Spec). `p1_vote_frac` là feature calibration.

**Prompt đường 1 (template cố định, thứ tự khối không đổi):**
```
Bạn là bộ phân tích câu hỏi về dữ liệu bán hàng. Chỉ trả về MỘT đối tượng JSON đúng schema, không giải thích.
Quy tắc cứng:
1) "time" chỉ chứa NHÃN có trong [KHOẢNG THỜI GIAN]. Tuyệt đối không viết ngày.
2) "filters.values" chỉ chứa giá trị có trong [THỰC THỂ] hoặc [GIÁ TRỊ CỘT].
3) "metric", "subject", "output" chỉ chọn trong enum của schema.
4) Nếu câu nói "bán chạy" mà không nêu tiêu chí thì dùng tiêu chí mặc định trong [QUY TẮC].
5) Câu ngoài khả năng của các metric ⇒ intent = "other".

[DỮ LIỆU]
{ctx.card}

[QUY TẮC]
bán chạy = {knobs.bestseller_metric}; đơn hợp lệ = không huỷ, không có hàng trả; (chỉ liệt kê knob khác mặc định)

[KHOẢNG THỜI GIAN]
main: 2026-02-23..2026-03-01 (tuần rồi)
base: …

[THỰC THỂ]
"sp ..." → product: "Xi măng Hà Tiên PCB40 bao 50kg" (mã SP0001, điểm 0.96)

[GỢI Ý ĐIỀU KIỆN SỐ]
{having hoặc "không có"}

[GIÁ TRỊ CỘT]
channel={…} | pay_method={…} | customer_group={…}

[VÍ DỤ]
Câu hỏi: {example.question}
Nhãn thời gian có sẵn: main = tuần rồi
Spec: {example.spec_json}
(6 ví dụ)

[CÂU HỎI]
{q.text}
Spec:
```

**Nghiệm thu:**
- [ ] `FakeLLM`: JSON hỏng ⇒ mẫu bị loại, **không** làm hỏng cả lô; nhãn thời gian bịa ⇒ bị loại.
- [ ] `spec_correct_rate` (candidate vote cao nhất đúng) trên **holdout**, ghi theo intent vào `docs/m09.md`.
- [ ] Prompt dài ≤ `LLM_CTX_TOKENS − 600`; thử cắt ví dụ trước khi cắt card.

---

### M10 — Đường 2 (SQL tự do)

**Tạo:** `paths/path2_sql.py`, `tests/test_path2.py`

```python
def run_path2(q, ctx, knobs, windows, entities, bank, llm, k:int=K2) -> list[Candidate]
```
1. Prompt: DDL các view `v_*` (từ `information_schema`) + ghi chú "chỉ dùng view `v_*`, **không** dùng `t_*`/`c_*`" + khoảng thời gian dạng `DATE '…'` + thực thể + quy tắc xếp hạng (`ORDER BY value DESC, code ASC`; lấy `LIMIT k+1` để phát hiện hoà) + luật `<= as_of` + 4 ví dụ `(câu hỏi → {"answer_type","sql"})` với SQL **biên dịch từ spec đã xác minh** bằng `compile_spec`.
2. Sinh k=5, bộ ví dụ xoay vòng; `SQL_SCHEMA`.
3. Kiểm tra SQL: chỉ `SELECT/WITH`; **không** tham chiếu bảng ngoài danh sách cho phép. Vi phạm ⇒ bỏ mẫu.
4. `run_sql → to_submission(plan=None, out_type=answer_type)`. Mẫu lỗi/rỗng ⇒ **sửa một lần** bằng prompt: `SQL trước bị lỗi: {error}. Hãy sửa và trả lại JSON đúng schema.`
5. Vote theo `canon_key`; trả `Candidate(votes,k)`.
6. **Chế độ `fallback_raw`:** khi `ctx.archetype=="UNKNOWN"` hoặc `ctx.schema_conf < 0.5`, cho phép truy vấn các bảng sạch `t_*` (kèm danh sách cột + 3 dòng mẫu của mỗi bảng trong prompt). Candidate gắn cờ `raw_mode=True`; M12 cộng `UNVERIFIED_EXTRA_MARGIN`.

**Nghiệm thu:** `path2_correct_rate` trên holdout; in **ma trận đồng thuận** (path1 đúng/sai × path2 đúng/sai × đồng ý/bất đồng). Nếu `P(đúng | đồng ý)` không cao hơn rõ rệt `P(đúng | chỉ path1)` ⇒ giữ đường 2 chỉ cho `intent=other`, `raw_mode` và câu đường 1 không phủ. Test: SQL tham chiếu bảng cấm ⇒ bỏ mẫu.

---

### M11 — Answerability

**Tạo:** `decide/answerability.py`, `dev/null_causes.py`, `tests/test_answerability.py`

```python
def check_answerable(spec_or_intent, windows, entities, ctx, knobs, as_of) -> AnswerCheck
```
Áp đúng quy tắc **4.10** (không thêm bớt). `RuleSpec.features` không dùng ở đây.

`dev/null_causes.py`: đọc 70 câu train `answer: null`, chạy `check_answerable`, in bảng *nguyên nhân dự đoán × số câu*. Câu `null` bị bỏ sót ⇒ bổ sung luật vào 4.10 (ghi `survey/fix_log.md`, **sửa cả 4.10 trong file này**).

**Nghiệm thu:** `recall_unanswerable` và `false_unanswerable_rate` trên train; mục tiêu **`false_unanswerable_rate ≈ 0`** (mỗi lỗi = −1, và câu `null` chỉ chiếm ~2,3%). Báo cáo riêng cho dev và holdout.

---

### M12 — Quyết định, calibration, leo thang

**Tạo:** `decide/features.py`, `decide/calibrate.py`, `decide/decider.py`, `decide/escalate.py`, `dev/run_train.py`, `tests/test_decider.py`, `docs/m12.md`

**Feature (định nghĩa chính xác):**

| feature | định nghĩa |
|---|---|
| `schema_conf` | từ `ctx` |
| `rule_missing` | 1 nếu nhóm nghiệp vụ của câu ∉ `rules.features` hoặc có `unmapped` liên quan |
| `agree_p1_p2` | 1 nếu `canon_key(top1)==canon_key(top2)` |
| `p1_vote_frac`, `p2_vote_frac` | `votes/k` của ứng viên top |
| `p1_empty`, `p2_empty` | đường không có ứng viên |
| `knn_intent_agree` | nhãn intent top-1 BM25 = intent của Spec top |
| `min_entity_score` | điểm thấp nhất trong các entity được dùng (1.0 nếu không có) |
| `n_unresolved_time` | số cụm trong `unresolved` |
| `result_is_empty`, `result_negative` | kết quả rỗng / âm |
| `result_ratio_vs_neighbor` | `log((value_main+1)/(value_nb+1))`, `value_nb` = cùng metric trên **cửa sổ `neighbor`**: dịch `main` lùi đúng 1 độ dài của `main` (cùng `kind`, cùng `shift`). Cửa sổ `neighbor` **không** do `resolve_time` sinh ⇒ `compile_spec` tự dịch. NULL (không có `main`/không lấy được) ⇒ 0. **Chi phí: +1 truy vấn/câu** ⇒ tính cùng lô path1/path2, và nếu deadline ép thì bỏ feature (giá trị 0) |
| `intent`, `out_type` | one-hot |
| `n_joins` | số view được tham chiếu |
| `raw_mode`, `archetype_unknown`, `domain_unverified` | cờ |
| `esc_choice` | 0/1/2 sau leo thang (0 mặc định) |

**`decide`:**
```python
def decide(cands1, cands2, check:AnswerCheck, feats:dict, model, cfg) -> Answer
```
1. `check.p_unanswerable ≥ 0.5` **và** `schema_conf ≥ 0.6` ⇒ `unanswerable` (kèm `reason`).
2. `top1=cands1[0]`, `top2=cands2[0]`. Nếu `canon_key` bằng nhau ⇒ `c=top1`. Một đường rỗng ⇒ `c` = đáp án đường kia, cờ `single_path` (chỉ khi `intent=other`, `raw_mode`, hoặc calibrator cho phép). Bất đồng ⇒ **leo thang**; không có kết quả ⇒ `abstain`.
3. `p = model.predict_proba(feats)` (theo `out_type`), `p_adj = p − CALIB_MARGIN − (UNVERIFIED_EXTRA_MARGIN nếu raw_mode/UNKNOWN/domain_unverified)`.
4. `p_adj > 0.5` ⇒ trả `c`, ngược lại `abstain`. Intent ∈ `cfg.blocked_intents` ⇒ `abstain`.

**Phiên bản khởi đầu (chưa có model):** `p = 0.9` nếu `agree_p1_p2` ∧ `schema_conf ≥ 0.8` ∧ `min_entity_score ≥ 0.9` ∧ `n_unresolved_time == 0` ∧ `rule_missing == 0`, ngược lại `p = 0.3`.

**Calibration:**
1. `dev/run_train.py`: chạy pipeline với **business bị giữ ra** (bank không chứa câu của business đó) cho mọi câu train, ghi `features.parquet` (feature, `candidate_chosen`, `correct` 0/1).
2. `calibrate.py`: `LogisticRegression(C=1.0)` cho mỗi `out_type`; nhóm < `CALIB_MIN_TRAIN_PER_OUTTYPE` mẫu ⇒ dùng mô hình chung. `GroupKFold` theo business đo `ECE` và PA mô phỏng; chọn `CALIB_MARGIN` cho PA mô phỏng cao nhất; lưu `models/calibrator.pkl` (`joblib`).
3. **Báo cáo tổng quát hoá:** PA mô phỏng theo *leave-one-archetype-out* (đo trên archetype chưa từng thấy) ⇒ nếu `ECE` ở fold lạ cao hơn fold quen, tăng margin tương ứng.
4. `calibration.md`: ECE, PA theo `out_type`, PA mô phỏng vs PA "luôn trả lời", bảng intent có precision < 0.5 ⇒ thêm `cfg.blocked_intents`.

**`escalate.py`:** khi bất đồng hoặc `|p − 0.5| < 0.1`: prompt `thinking=True`, `max_tokens` cố định (1024), gồm câu hỏi, ngữ cảnh ngắn, phương án A (Spec/SQL + kết quả) và B; `{"choice": 1|2|0}` (0 = không phương án nào đúng). Kết quả vào `esc_choice` rồi tính lại `p`. `choice==0` ⇒ abstain.

**Nghiệm thu:** `PA_simulated` (holdout) ≥ PA baseline "luôn trả đường 1"; báo cáo `coverage` + `precision`; `calibration.md` đầy đủ.

---

### M13 — Orchestrator `predict.py`

**Tạo:** `predict.py`, `dev/repro_check.py`

```python
def discover_split(root:str) -> SplitPaths   # tìm questions.jsonl, rulebook.md, calendar.csv, thư mục data/<business_id>/
```
`discover_split` thử `root/questions.jsonl` rồi `root/*/questions.jsonl` (BTC mount `/data`; cấu trúc `<split>/data/<business_id>/` theo đề). Không thấy ⇒ lỗi rõ ràng.

```
main():
  t0 = now(); cfg = config; llm = LLM()
  paths = discover_split(cfg.DATA_ROOT)
  questions = load_questions(paths.questions)
  write_submission(abstain cho TẤT CẢ id)                  # TẦNG 0: luôn có file hợp lệ ngay từ đầu
  rules = parse_rulebook(read(paths.rulebook), TRAIN_RULEBOOK_TEXT, llm); cal = load_calendar(paths.calendar)
  for biz in sorted(businesses):                           # business_id CHỈ để tìm thư mục
      ctx = build_context(biz_dir, rules.knobs, rules, llm)
      for batch in chunks(sorted(questions_of(biz), key=id), 32):
          Tầng 1: windows/entities → path1(K1) ∥ path2(K2) → check → decide
          Tầng 2: câu bất đồng/sát ngưỡng → escalate → decide lại
          ghi nguyên tử (tmp → os.replace → OUT_DIR/submission.jsonl) sau mỗi batch
```
- Mỗi batch: các lời gọi LLM của cả batch gom lại và gửi **đồng thời**, nhưng kết quả gắn lại theo chỉ số ⇒ thứ tự xác định.
- **Đồng hồ an toàn:** `DEADLINE_S` tính từ **lúc `predict.sh` bắt đầu** (đọc `DATAMATE_START_TS`, fallback `t0`). Còn < 25% thời gian ⇒ bỏ Tầng 2; còn < 10% ⇒ chỉ đường 1; hết ⇒ dừng, giữ `abstain`. **Quyết định trả lời không phụ thuộc đồng hồ** ngoài việc dừng/bỏ tầng.
- **Log** `OUT_DIR/logs/<id>.json`: `id, answer, elapsed_s, windows, entities, spec_samples, sqls, exec_results, knobs, schema_conf, features, p, p_adj, reason`; thêm `_biz_<hash>.json` (mapping, bất biến, capabilities, archetype) và `_knobs.json` (RuleSpec).
- `dev/repro_check.py`: chạy hai lần trên 300 câu validation ⇒ in số câu đổi đáp án và `|ΔPA|`; mục tiêu `< 0.01`. Chênh nhiều ⇒ kiểm tra các câu `|p_adj − 0.5| < 0.05` và nâng margin cho nhóm đó.

**Nghiệm thu:** chạy trên thư mục train giả lập test ⇒ `submission.jsonl` hợp lệ **100% id**, đúng định dạng từng type; `evaluate` cho PA khớp `run_train.py` (±0.01); kill giữa chừng ⇒ file vẫn hợp lệ (phần còn lại `abstain`).

---

### M14 — Ablation

**Tạo:** `dev/ablate.py`, `survey/ablation.md`
4 cấu hình trên cùng holdout: (a) chỉ đường 1, (b) chỉ đường 2, (c) cả hai (đồng thuận là feature), (d) (c)+leo thang. Giữ cấu hình PA cao nhất. (c) không hơn (a) ≥ 0.02 ⇒ đường 2 chỉ chạy cho `intent=other`, `raw_mode` và câu đường 1 không phủ. Cập nhật `K1`, `K2`, bật "câu dễ" nếu PA không giảm.

---

### M15 — Mở rộng ngành mới (sửa xe, điện thoại, mẹ và bé)

**Điều kiện bắt đầu:** G3 đạt. **Lý do xếp sau:** các ngành này chỉ có ở `public_test` (không có đáp án để kiểm), còn test private lại có loại hình *khác nữa*; ưu tiên tổng quát hoá của lõi hơn. Quyết định #4 (làm cả 3 ngành) **giữ nguyên**, chỉ đổi thứ tự.

**Tạo:** `domains/repair.py`, `domains/phone.py`, `domains/baby.py`, `tests/test_domains.py`
**Nguyên tắc:** phát hiện theo **dấu hiệu cấu trúc** (tên cột, số cột), **không** theo `business_id`; mọi ngữ cảnh ngành gắn `ctx.verified=False` ⇒ M12 cộng `UNVERIFIED_EXTRA_MARGIN`.

Mỗi ngành bắt đầu bằng **khảo sát** (ghi `survey/domain_<x>.md`: cột thật, 20 câu hỏi public_test thuộc ngành, câu rulebook liên quan), rồi mới viết:

| ngành | view | metric thêm vào registry | ghi chú |
|---|---|---|---|
| sửa xe | `v_repair_tickets(ticket_date, vehicle_line, plate, works_text, mechanic, amount, is_warranty)`; `v_repair_works(ticket_id, work)` | `repair_tickets` (đếm lượt), `repair_revenue`, `repair_by_mechanic`, `works_count` | mỗi dòng sổ = 1 lượt xe; tách việc theo dấu phẩy + mẫu `1)`, `2)`; phiếu bảo hành = ghi chú bảo hành **hoặc** tiền 0 (quyết định 16) |
| điện thoại | `v_phone_orders`, `v_installments(order_id, due_date, period_amount, paid_amount, is_overdue)`, `v_warranty_tickets`, `v_trade_ins` | `installment_due`, `installment_overdue_count`, `trade_in_amount`, `warranty_count` | kỳ góp + quá hạn (quyết định 17); thu máy cũ trừ vào tiền đơn |
| mẹ và bé | dùng `v_lines`, thêm `size`, `product_no`, `customer_since` | `members_new`, `size_qty`, `group_share` theo nhóm khách | số/size lấy theo **cột danh mục**; hàng để trống Số/Size không xếp vào size nào |
| §1/§3 ở public_test | — | `cash_by_shift` (báo cáo tiền mặt theo ca theo **giờ thu tiền**), `peak_hour` (khung 1 giờ tròn nhiều đơn nhất theo giờ tạo đơn), `loyal_customers` (nhiều **ngày có mua** nhất trong kỳ), `topping_qty` (topping tách thành mặt hàng riêng) | công thức bám đúng câu rulebook; ghi số câu vào `docs/rulebook_map.md` |

Mỗi metric mới: thêm vào `registry`, `caps` riêng (vd `repair_ticket`, `installment_ledger`) **phát hiện từ dữ liệu**, test trên fixture dựng tay từ vài dòng thật.

**Nghiệm thu:** mỗi ngành có test trên fixture; chạy `predict.py` trên `public_test` không crash; **kiểm tay** 10 câu mỗi ngành (người dev duyệt, ghi `survey/domain_<x>.md`); ngành nào không qua kiểm tay ⇒ để `abstain` (đặt `domain_unverified` với margin lớn hoặc `blocked_intents`).

---

### M16 — Đóng gói Docker, tái lập và nộp

**Tạo:** `docker/Dockerfile`, `docker/predict.sh`, `docker/start_llm.sh`, `docker/README_solution.md`, `tests/test_offline.sh`
**Bắt đầu khi:** G3 đạt.

**Yêu cầu luật thi (bắt buộc):** image chứa mã nguồn (train + inference), **trọng số model**, `predict.sh` đọc test từ `/data`, ghi `/result/submission.jsonl` và `/result/logs/`; **chạy offline** (network tắt); khai báo model trong README; chạy hết test private trong **6 giờ** trên 2×RTX 5090 (gồm load model); CUDA ≥ 12.8; base image theo **Docker guideline của BTC** (đọc trước khi viết Dockerfile; chưa có thì dùng `nvidia/cuda:12.8.*-runtime` + `torch`/`vllm` bản hỗ trợ Blackwell, ghi vào `BACKLOG.md`).

**Thiết kế (client LLM giữ nguyên, chỉ đổi endpoint):**
- `docker/start_llm.sh`: với mỗi GPU `i` khởi động một vLLM server: `CUDA_VISIBLE_DEVICES=i vllm serve /models/<model> --served-model-name Qwen3-4B --port 800$i --max-model-len 8192 --enable-prefix-caching --seed 0 --gpu-memory-utilization 0.90`; chờ `/health` (timeout 15 phút). Xuất `DATAMATE_LLM_BASE_URLS=http://127.0.0.1:8000/v1,http://127.0.0.1:8001/v1`.
- `docker/predict.sh`: `export DATAMATE_START_TS=$(date +%s)` ⇒ `start_llm.sh` ⇒ `python -m predict` ⇒ dọn server. **Nếu bước nào thất bại vẫn phải còn `/result/submission.jsonl`** (Tầng 0 đã ghi toàn `abstain` ngay từ đầu `predict.py`; nếu vLLM không lên được, `predict.py` chạy chế độ **không LLM**: chỉ đường deterministic + `abstain` cho phần còn lại).
- Trọng số được tải **lúc build** (không khi chạy). Pin phiên bản mọi thư viện. `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`.
- Ghi vào `/result` và `CACHE_DIR` (`/tmp/datamate_cache`); `/data` chỉ đọc.
- **Model:** mặc định `Qwen3-4B`. Luật Rule 2 cho tổng ≤ 15B tham số (tính mọi model dùng khi suy luận, kể cả MoE) và phát hành trước 01/10/2026; đổi model chỉ qua `config.LLM_MODEL` + `start_llm.sh`, **chọn bằng số đo PA trên holdout** (M14), không theo cảm tính. Hai replica cùng trọng số: ghi rõ trong `README_solution.md` (tham số tính một lần cho mỗi model khác nhau); nếu BTC không chấp nhận, chuyển sang một server `--tensor-parallel-size 2`.

**`README_solution.md`:** danh sách model + license + ngày phát hành; mô tả pipeline; cách chạy; cấu trúc log; ghi chú tái lập.

**Nghiệm thu (checklist nộp):**
- [ ] `docker run --gpus all --network none -v <test>:/data:ro -v <out>:/result <image>` chạy trọn vẹn; `/result/submission.jsonl` hợp lệ **100% id**; `/result/logs/` đầy đủ.
- [ ] Tổng thời gian (gồm load model) đo trên máy tương đương 2×5090 **< 5.25 giờ** (còn lề).
- [ ] Chạy hai lần liên tiếp trên 300 câu validation: `|ΔPA| < 0.01` (luật cho phép ≤ 0.03).
- [ ] `grep -rn "business_id ==\|biz_1\|question.id ==" .` không thấy điều kiện logic keyed.
- [ ] Không còn `api_key` trong mã nguồn; `.env` không bị commit; `git status` sạch.
- [ ] `submission.jsonl`: đúng 1 dòng mỗi id; `answer` đúng kiểu theo `type` (number→JSON number, list→array, table→`{"columns","rows"}`); `type` ∈ 9 giá trị hợp lệ; `unanswerable` có `reason` chuỗi (hoặc bỏ trống).

---

## 6. Vòng dev M8 (lặp lại cho tới khi qua G2)

```
1. python dev/enumerate_match.py --split train --scope dev --out survey/run_<n>/
2. Mở survey/run_<n>/unmatched.jsonl    (chỉ DEV; holdout chỉ xem số liệu tổng)
3. Nhóm theo lý do: no_spec | exec_error | wrong_value
4. Chọn ĐÚNG MỘT nhóm → sửa: từ điển viết tắt | NAME_TOKENS | định nghĩa metric/khung | thêm intent
5. Ghi survey/fix_log.md: ngày, nhóm, sửa gì, số câu ảnh hưởng
6. python dev/enumerate_match.py --scope holdout --summary-only   (đo khoảng cách dev−holdout)
7. Lặp tới khi qua G2
```
Không sửa nhiều nhóm một lúc (không đo được tác động từng thay đổi).

---

## 7. Danh sách quyết định đã chốt (KHÔNG mở lại)

1. API/endpoint LLM kiểu OpenAI-compatible, mặc định `Qwen3-4B`, 16 luồng, `json_schema`, key từ env. **Khi nộp: vLLM chạy cục bộ trong image** (M16).
2. File nộp lúc dev `public_test/submission.jsonl`; lúc nộp Docker `/result/submission.jsonl`; deadline mặc định 5,25 giờ.
3. Holdout 6/30 business cố định theo seed (`dev/splits.json`).
4. **Làm cả 3 ngành mới**, nhưng ở **M15 sau lõi** (đổi thứ tự, không đổi phạm vi).
5. Prompt dùng **câu gốc có dấu** + entity đã khớp.
6. So khớp chuỗi **giữ dấu tiếng Việt**; chỉ nới qua `alias`.
7. "Tháng trước" chỉ cắt cùng số ngày khi kỳ chính kết thúc hôm nay; "tuần trước" luôn trọn tuần.
8. Khách lẻ: loại khỏi xếp hạng, **vẫn** tính doanh thu và tổng nợ.
9. Chuẩn hoá tên khách: bỏ dấu + bỏ ký tự lạ (khi ghi ra giữ nguyên).
10. "Bán được bao nhiêu <đơn vị>" → lọc theo đơn vị cơ bản.
11. Lãi gộp = giá vốn **trên dòng bán**; giá trị tồn = giá vốn danh mục; không có ⇒ unanswerable.
12. Công nợ **không** cộng VAT.
13. Tuổi nợ tính từ ngày đặt.
14. "Tồn theo đơn vị lớn" → list 2 số.
15. `margin = 0,05`, trả khi `p_adj > 0,5`.
16. Tách việc sửa xe theo dấu phẩy + số thứ tự; phiếu bảo hành = ghi chú bảo hành hoặc tiền 0.
17. Làm cả kỳ góp + quá hạn cho sổ góp.
18. Chấm điểm: khớp tuyệt đối sau làm tròn theo rulebook §9.
19. *(mới)* `as_of` là thuộc tính của câu hỏi; view không chứa `as_of`.
20. *(mới)* Hai lớp dữ liệu `c_*` (canonical, hấp thụ archetype) và `v_*` (view, áp rulebook).
21. *(mới)* Capability **dữ liệu** tách khỏi **features rulebook**; chỉ capability dữ liệu quyết định unanswerable.
22. *(mới)* LLM không viết ngày; `time` chỉ là nhãn; `filters` chỉ nhận giá trị trong danh sách ứng viên.
23. *(mới)* Hoà ở biên top-k ⇒ abstain; T2 luôn lấy `limit+1` dòng.
24. *(mới)* Vòng sửa M8 trên dev; holdout chỉ đo khoảng cách tổng quát hoá (≤ 8 điểm).
25. *(mới)* Mọi `UNKNOWN`/`raw_mode`/ngành chưa kiểm chứng chịu thêm margin `UNVERIFIED_EXTRA_MARGIN`.

---

## 8. Những điều chỉ biết được sau khi nhìn dữ liệu thật (phải khảo sát, không đoán trong code)

| Chưa biết | Nơi giải quyết | Mặc định tạm |
|---|---|---|
| Cột/định dạng `calendar.csv` | M2, `survey/calendar_head.txt` | adapter đọc cột ngày dương + ngày/tháng/năm âm |
| Chữ chính xác của rulebook train và public_test | M3, `survey/rulebook_sentences.txt` | `Knobs` mặc định theo đề |
| Mỗi business có một hay nhiều `as_of` | M0, `survey/as_of_stats.json` | coi là nhiều (an toàn) |
| Công thức `price_effect` | M8, `survey/price_effect_samples.txt` | rơi vào `intent=other` |
| Nghĩa cột "giá vốn" (đơn vị hay tổng) | M4 `inv_cost` | quyết theo bất biến |
| Thanh toán có gắn `order_id` không | M4 / T6 `debt_age` | FIFO theo ngày đặt |
| Tồn theo lô hay theo sản phẩm | M5 `engine/lots.py` | FIFO theo hạn dùng |
| Ngưỡng "sắp hết hạn", "bán chậm", "tồn nhiều" | M5, M8 | 30 ngày, P25/P75 |
| Nguyên nhân các câu `null` | M11 `null_causes.py` | thiếu capability / ngoài phạm vi / tương lai |
| Base image Docker, có tính replica cùng trọng số một lần không | M16, Docker guideline của BTC | `nvidia/cuda 12.8`; có phương án TP=2 |
| Dung sai chính thức của `number`, cách chấm list/table | M0 `compare.py` | khớp tuyệt đối sau làm tròn (rulebook §9) |