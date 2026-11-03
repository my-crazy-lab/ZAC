# Kế hoạch thực thi DataMate

Tài liệu giải thích kiến trúc bên trong trước, để thấy mỗi phần của kế hoạch tồn tại vì lý do gì. Sau đó là các milestone theo thứ tự làm, mỗi milestone gồm file, hàm, thuật toán và tiêu chí nghiệm thu.

Các chỗ chưa thấy dữ liệu thật (cột của `calendar.csv`, chữ trong `rulebook.md`, dung sai chấm number) được biến thành **bước khảo sát** có đầu ra rõ ràng, không đoán trong code.

---

## 0. Kiến trúc bên trong và lý do của kế hoạch

```
[A] Ingest ─► [B] Map schema ─► [Views canonical, đã áp rulebook + cắt tại as_of]
                                        ▲
 rulebook.md ─► [C] Knobs + RuleSpec ─────────┘
 question ─► [D] time + entity ─┬─► ĐƯỜNG 1: LLM điền Spec ─► metric library ─┐
                                └─► ĐƯỜNG 2: LLM viết SQL trên views ─────────┤
                                                                              ▼
                              [G] answerability ─► [H] quyết định p̂>0.5 ─► [I] formatter
```

PA là +1 đúng, 0 abstain, −1 sai, nên mỗi quyết định thiết kế phục vụ một trong năm mục tiêu sau:

1. **Rulebook được áp đúng một lần, ở tầng view.** Doanh thu, loại đơn huỷ/trả hàng, cắt theo as_of đều nằm trong SQL view. LLM không bao giờ tự viết logic đó. Vì vậy phải làm ingest, schema, knob và view trước LLM.
2. **LLM chỉ điền chỗ trống trong tập đóng.** Ngày tháng, tính toán, tie-break, format do code làm. Vì vậy phải làm time resolver, metric library và formatter trước, rồi mới nối LLM.
3. **Hai đường (Spec và SQL) để lấy tín hiệu đồng thuận.** Không dùng đồng thuận làm quy tắc cứng mà làm feature cho calibration.
4. **Unanswerable do code suy ra** từ capability của schema, để không mất −1 khi đoán bừa.
5. **Mọi thứ đo trên train theo leave-one-business-out.** Vì vậy `dev/evaluate.py` phải có ở milestone đầu tiên.

**Quy ước cho mọi file (LLM implementer bắt buộc tuân thủ):**

- **Dùng API LLM được cấp** (OpenAI-compatible, `Qwen3-4B`), không tự host model. `base_url`/`api_key`/`model` đọc từ `config.py` hoặc biến môi trường — **không** hard-code, **không** commit key. API vẫn gọi được ở vòng private (Docker của đội).
- Không có `if business_id == ...` hay logic theo id câu hỏi.
- Cache theo `sha256` của nội dung file dữ liệu, không theo tên business.
- Mọi sinh LLM dùng temperature 0 và seed cố định.
- Mọi duyệt `dict`/`set` đưa vào quyết định phải `sorted(...)` trước.
- Mọi hàm có type hints và có test trong `tests/`.

---

## 1. Cấu trúc repo

```
datamate/                      # gốc repo ĐÃ tên là datamate/ → code đặt ở đây, KHÔNG tạo datamate/datamate/
  config.py            # Config, DEFAULT_KNOBS
  dtypes.py            # dataclass dùng chung (mục 2)
  ingest/{reader.py, clean.py}
  schema/{roles.py, mapper.py, invariants.py, views.py}
  rules/{knobs.py, rulebook_parser.py}
  timeutil/{calendar_vi.py, resolver.py}
  text/{normalize.py, entity_linker.py, bm25.py}
  engine/{metrics.py, executor.py, sandbox.py}
  llm/{client.py, prompts.py, schemas.py}
  paths/{path1_spec.py, path2_sql.py}
  decide/{answerability.py, features.py, calibrate.py, decider.py, escalate.py}
  fmt/{formatter.py, compare.py}
  dev/{survey.py, evaluate.py, enumerate_match.py, build_bank.py, run_train.py}
  predict.py
  tests/
```

---

## 2. Hợp đồng dữ liệu (`dtypes.py`)

```python
@dataclass
class Question: id:str; business_id:str; text:str; as_of:date

@dataclass
class Answer:
    type: str                 # string|number|percent|date|boolean|list|table|unanswerable|abstain
    value: Any = None         # theo đúng định dạng submission
    reason: str | None = None

@dataclass
class Knobs:                  # giá trị mặc định = rulebook train (theo đề)
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
    cost_method: str = "wavg_by_lot"         # wavg_by_lot | wavg_up_to_sale_date
    tet_start: tuple = ("lunar", 12, 23, -1) # (loại, tháng, ngày, offset năm âm lịch)
    tet_end:   tuple = ("lunar", 1, 10, 0)
    unmapped: list[str] = field(default_factory=list)  # câu rulebook không map được

@dataclass
class RuleSpec:                 # kết quả M3 — không chỉ knob, còn capability/ngành
    knobs: Knobs
    domains: set[str]           # ngành áp dụng: cafe|pharmacy|construction|baby|repair|phone|...
    required_caps: set[str]     # capability rulebook đòi có (vd "repair_ticket", "installment")
    unmapped: list[str]

@dataclass
class TimeWindow:
    label: str; start: date; end: date        # inclusive
    kind: str = "period"        # period | cumulative | shift
    shift: str | None = None    # "sang" | "chieu" khi kind == "shift"
    trunc_same_days: bool = False   # base = kỳ trước cắt theo cùng số ngày (rulebook §2)

@dataclass
class BizContext:
    con: duckdb.DuckDBPyConnection
    mapping: dict          # role -> (table, column), cùng bảng được gán loại thực thể
    capabilities: set[str] # vd {"line_amount","cost","expiry","debt","customer"}
    date_min: date; date_max: date
    schema_conf: float     # 0..1
    status_invalid: dict   # {"cancelled":[...], "returned":[...]}
    card: str              # schema card text 1–2k token
    entity_index: Any      # từ text/entity_linker.py
    invariants: dict       # kết quả từng invariant (để log)

@dataclass
class Spec:                # JSON schema ở mục M9
    intent:str; metric:str|None; agg:str|None; subject:str|None
    filters:list; time:list; group_by:list; order:str; limit:int|None
    output:str; conditions:list

@dataclass
class Candidate: answer:Answer; source:str  # "path1"|"path2"; spec_or_sql:str; votes:int; k:int
```

---

## 3. Các milestone

### M0. Khảo sát dữ liệu và bộ chấm điểm (làm đầu tiên)

**Mục đích:** biết dữ liệu thật trước khi viết parser, và có thước đo cho mọi milestone sau.

**`dev/survey.py`.** Với mỗi business trong `train/data/`, ghi ra `survey/` các file sau (dùng để người dev chỉnh từ điển, không chạy lúc inference):

- `columns.csv`: business, file, sheet, tên cột, kiểu suy đoán, 5 giá trị mẫu, tỉ lệ null, số giá trị phân biệt.
- `calendar_head.txt`: 20 dòng đầu của `calendar.csv` và danh sách cột.
- `rulebook_sentences.txt`: rulebook tách thành câu, mỗi câu một dòng đánh số.
- `answers_stats.json`: phân bố `type`, tỉ lệ `answer == null`, 30 câu `null` mẫu, 50 câu hỏi mẫu cho mỗi `type`.

**`fmt/compare.py`** (dùng cho evaluate và cho so khớp đồng thuận):

```python
def canon_key(ans: Answer) -> Hashable
def is_correct(pred: Answer, ref: dict) -> bool
```

Quy tắc (theo rulebook §9 — đã biết, không còn là ẩn số; phần dung sai chỉnh trong `config.py`):

- `number`: so khớp theo **luật chấm thật** (rulebook §9), không theo dung sai lỏng: tiền → số nguyên VND, làm tròn về đồng, nửa đồng làm tròn lên; số khác → 2 chữ số thập phân; đúng khi hai bên bằng nhau sau khi làm tròn (`abs(a-b) <= 1e-9`). Dung sai lỏng (`0.5` tuyệt đối / `1e-4` tương đối) chỉ dùng để **log chẩn đoán** trong `dev/evaluate.py`, KHÔNG dùng để tính PA — nếu không ta tinh chỉnh trên metric lạc quan hơn chấm điểm thật.
- `percent`: rulebook §9 nói "khớp tuyệt đối" và "đúng 2 chữ số thập phân" → đúng khi bằng nhau sau khi làm tròn 2 chữ số thập phân (`abs(a-b) <= 1e-9`). Sai số tuyệt đối 0.01 chỉ để log.
- `string`: chuẩn hoá = bỏ khoảng trắng thừa + hạ chữ thường + bỏ dấu câu, **giữ nguyên dấu tiếng Việt** (rulebook §9: "Ngoài các cách viết đó, dấu tiếng Việt phải đúng"; ví dụ sai ghi rõ `"Sting dầu 330ml"` là sai). Chỉ chấp nhận khác dấu khi khớp được một phần tử trong `alias` (alias là các cách viết khác *có thật trong file* của shop).
- `date`: bằng ISO; câu hỏi theo tháng dùng `YYYY-MM` → so cả hai dạng (so sánh `YYYY-MM` với `YYYY-MM-01` cùng tháng là khớp).
- `boolean`: bằng.
- `list`: so khớp có thứ tự từng phần tử như `string`. Cùng độ dài.
- `table`: cùng số cột, cùng số dòng, so từng ô (số theo `number`, chuỗi theo `string`), bỏ qua tên cột.
- **Alias:** `answers.jsonl` có trường `alias` là **mảng alias theo từng phần tử** (vd `[["KH0098"],["KH0078","Từ Hải Thanh 0359470831"]]`). Với `list`/`table`, phần tử `i` được coi là khớp nếu khớp giá trị `answer[i]` **hoặc** bất kỳ phần tử nào của `alias[i]`. Với `string`, `alias` là mảng các cách viết thay thế (mã, tên kèm số điện thoại). `alias` rỗng (`[]`) là hợp lệ, không phải lỗi.
- ref `answer is None` thì chỉ đúng khi `pred.type == "unanswerable"`. `abstain` luôn cho 0 điểm.
- `canon_key`: số làm tròn 6 chữ số có nghĩa, chuỗi bỏ khoảng trắng + hạ chữ thường (**giữ dấu**), list thành tuple, table thành tuple của tuple.

**`dev/evaluate.py`:** đọc `submission.jsonl` và `answers.jsonl`, in PA tổng, PA theo `type`, theo business, tỉ lệ coverage (không abstain) và precision.

**Nghiệm thu:** chạy evaluate với submission "đáp án tham chiếu" cho PA = 1.0, và với "toàn abstain" cho PA = 0.0. Test `is_correct` cho mỗi type, ít nhất 3 ca mỗi type, trong đó có ca alias.

---

### M1. Ingest và làm sạch (`ingest/`)

**Mục đích:** đưa mọi định dạng bẩn về bảng DuckDB sạch, để M4 chỉ phải nghĩ về nghĩa của cột.

**`reader.py`:** `def load_business(path) -> list[RawTable]`, `RawTable(name, source, sheet, df)`.

- CSV: thử encoding theo thứ tự `utf-8-sig, utf-8, cp1258, latin-1`, chọn encoding đầu tiên giải mã không lỗi và không chứa ký tự `�`. Delimiter dùng `csv.Sniffer` trên 20KB đầu, fallback thử `, ; \t |` và chọn cái cho số cột ổn định nhất.
- Excel: `openpyxl`/`pandas`, đọc mọi sheet, bỏ sheet rỗng.
- SQLite: mọi bảng (không phải `sqlite_%`) và mọi view.
- Bỏ qua `README.md` ở bước này (M4 đọc).

**`clean.py`:**

```python
def find_header_row(df_raw) -> int
def clean_table(df_raw) -> pd.DataFrame
def parse_number_series(s) -> pd.Series
def parse_date_series(s) -> pd.Series
```

- `find_header_row`: duyệt 15 dòng đầu, chọn dòng đầu tiên mà (a) ≥ 60% ô không rỗng là chuỗi không phải số và (b) dòng liền sau có tỉ lệ ô không rỗng ≥ 60%. Mặc định dòng 0.
- Sau header: bỏ dòng rỗng hoàn toàn và dòng "tổng" (ô đầu chứa `tong|total|cong` không dấu mà các cột id để trống). Cột tên trùng thì thêm hậu tố `_2`. Ô gộp: forward-fill chỉ cho cột mà ≥ 30% null và các giá trị không null lặp lại (cột nhóm).
- `parse_number_series` quyết định theo **cả cột**. Bỏ ký hiệu `đ ₫ vnd VND`, khoảng trắng. Hậu tố `k` ×1e3, `tr|triệu|m` ×1e6, `tỷ|ty|b` ×1e9. Dấu thập phân: nếu cột có mẫu `\d{1,3}(\.\d{3})+(,\d+)?` chiếm đa số thì `.` là nghìn, `,` là thập phân. Nếu mẫu `\d{1,3}(,\d{3})+(\.\d+)?` chiếm đa số thì ngược lại. Còn lại dùng `float()`.
- `parse_date_series`: thử Excel serial (số 20000–60000 trong cột thuần số), ISO, rồi `dd/mm/yyyy` và `mm/dd/yyyy`. Nếu có giá trị có thành phần đầu > 12 thì là dd/mm, nếu thành phần thứ hai > 12 thì là mm/dd, nếu không quyết định được thì mặc định dd/mm (kiểu Việt). Cột được coi là ngày khi tỉ lệ parse ≥ 0.9.
- Chuỗi: `unicodedata.normalize("NFC")`, strip. Với mỗi cột chuỗi lưu thêm `<col>__nd` (bỏ dấu, lower) để so khớp.
- Dòng trùng: chỉ drop khi **toàn bộ cột** trùng và bảng có cột id mà id trùng. Ghi `dup_dropped` vào log.
- Nạp vào DuckDB, tên bảng `raw_<slug>`. Cache vào `cache/<sha256>.duckdb` (sha256 của nối byte các file dữ liệu đã sắp xếp).

**Nghiệm thu (test đơn vị):** `parse_number_series(["1.200.000đ","1,2tr","500k"])` ra `[1200000,1200000,500000]`. Cột `["01/02/2026","13/02/2026"]` ra tháng 2. Chạy trên mọi business train: không crash, mọi bảng có ≥ 1 dòng, ghi báo cáo số cột ngày/số parse được.

---

### M2. Time resolver và lịch âm (`timeutil/`)

**Mục đích:** LLM không được tự tính ngày. Resolver tính khoảng thời gian và đưa vào prompt đã tính sẵn.

**`calendar_vi.py`.** Đọc `calendar.csv` theo `survey/calendar_head.txt`. Viết adapter `load_calendar(path) -> Calendar` từ các cột thực (kỳ vọng có ngày dương và ngày/tháng/năm âm kèm cờ tháng nhuận). Các hàm:

```python
def lunar_to_solar(year:int, month:int, day:int, leap:bool=False) -> date
def tet_window(cal, tet_year:int, knobs) -> tuple[date,date]
```

Cửa sổ Tết của năm âm lịch Y: `start = lunar_to_solar(Y-1, 12, 23)`, `end = lunar_to_solar(Y, 1, 10)` (đọc từ `knobs.tet_start/tet_end`, không hard-code). Nếu tháng Chạp không có ngày 23 thì lấy ngày cuối tháng.

**`resolver.py`:**

```python
def resolve_time(text_nd:str, as_of:date, knobs:Knobs, cal:Calendar) -> tuple[list[TimeWindow], list[str]]
# trả (các khoảng, danh sách cụm thời gian không giải được)
```

`text_nd` là câu đã bỏ dấu và lower. Dùng bảng pattern có thứ tự ưu tiên (cụm dài trước), mỗi pattern gắn một hàm. Tuần bắt đầu theo `knobs.week_start`.

| Cụm (không dấu) | Khoảng |
|---|---|
| `hom nay` | [as_of, as_of] |
| `hom qua` | [as_of−1, as_of−1] |
| `tuan nay` | [đầu tuần chứa as_of, as_of] |
| `tuan (roi\|truoc)` | cả tuần liền trước tuần chứa as_of (T2→CN) |
| `thang nay` | [mùng 1 tháng của as_of, as_of] |
| `thang (roi\|truoc)` | cả tháng liền trước; **riêng khi dùng làm base so sánh** với một kỳ chính kết thúc ở hôm nay → cắt theo cùng số ngày của tháng trước (rulebook §2: "so với tháng trước thì lấy cùng số ngày của tháng trước"; tháng trước không có ngày đó thì đến hết tháng trước). Kỳ chính không kết thúc ở hôm nay (vd "so với tháng trước đó" với kỳ chính là tháng 2/2026) → base là cả tháng trước |
| `quy nay` | [đầu quý, as_of]; `quy (roi\|truoc)` cả quý liền trước |
| `nam nay` | [1/1, as_of]; `nam (ngoai\|roi\|truoc)` cả năm trước |
| `(\d+) ngay (qua\|gan day\|vua roi)` | [as_of−N+1, as_of] nếu `last_n_includes_today` |
| `(\d+) tuan qua`, `(\d+) thang qua` | tương tự theo tuần/tháng |
| `qua N, hon N, tren N, duoi N` | **không** gồm N (rulebook §2) |
| `tu N tro len` | gồm N |
| `ca sang` / `ca chieu` | lọc theo **giờ tạo đơn**: sáng 06:00–13:59, chiều 14:00–21:59 → `kind="shift"`; so sánh ca chiều với ca sáng thì mốc là ca sáng |
| `den het ngay X` / `tinh den het ngay X` | `kind="cumulative"`: trạng thái **lũy kế từ đầu dữ liệu** đến hết ngày X (rulebook §2), không phải "tháng này" |
| `thang (\d{1,2})` | tháng đó của năm as_of nếu tháng ≤ tháng của as_of, ngược lại của năm trước |
| `cung ky (nam ngoai\|nam truoc)` | dịch mọi khoảng chính 1 năm (29/2 thành 28/2), thêm nhãn `yoy` |
| `cung ky (thang\|tuan) (truoc\|roi)` | dịch cùng độ dài lùi một tháng/tuần, nhãn `prev` |
| `tet (nam ngoai\|nam truoc)` | cửa sổ Tết của năm dương `as_of.year−1` |
| `tet (nay\|vua roi\|gan nhat)` hoặc `tet` trơn | cửa sổ Tết gần nhất có `start <= as_of` |
| `thu (2..7\|cn) (tuan roi\|tuan nay)` | ngày đó trong tuần tương ứng, độ dài 1 ngày |
| `so voi` / `tang giam` / `bao nhieu %` kèm hai cụm thời gian | trả hai khoảng, nhãn `main` (cụm đứng trước) và `base` (cụm đứng sau) |

Nhãn mặc định `main`. Khi một câu có hai cụm thời gian thì nhãn theo thứ tự xuất hiện: `main`, `base`. Nếu câu chứa từ thời gian nhận ra (`tuan|thang|quy|nam|ngay|tet|hom`) mà không pattern nào khớp thì thêm cụm vào `unresolved`.

Ngoài ra (chưa nằm trong bảng trên, nhưng câu hỏi thật có):

- **Nhiều kỳ trong một câu** ("Xét 3 tháng 1/2026, 2/2026 và 3/2026, doanh thu tháng nào lớn nhất?"; "dthu 3 tháng 4/2026, 5/2026, 6/2026 có tăng liên tục không") → trả list window theo đúng thứ tự câu nêu (`main` cho kỳ chính, `p1..pn` cho kỳ còn lại). Câu boolean so sánh liên tiếp cần **intent riêng** (`series_compare`), không dùng `compare_periods` 2 cửa sổ.
- **So sánh hai ca trong cùng kỳ** ("doanh thu ca chiều tăng hay giảm % so với ca sáng") → `main` và `base` cùng khoảng ngày, chỉ khác `shift`. Không phải so sánh kỳ.
- **Cùng kỳ năm ngoái** ("cùng kỳ tháng trước", "so cùng kỳ năm trước") → dịch cùng độ dài lùi 1 năm, giữ nguyên quy tắc cắt cùng số ngày nếu có.

**Nghiệm thu (test cứng, as_of = 2026-03-04, Thứ Tư):**

- `tuan roi` thành 2026-02-23..2026-03-01
- `thang nay` thành 2026-03-01..2026-03-04
- `thang truoc` thành 2026-02-01..2026-02-28
- `thang nay` + `thang truoc` (kỳ chính kết thúc ở hôm nay) → base phải là 2026-02-01..2026-02-04 (cắt cùng số ngày), **không** phải cả tháng 2
- `ca chieu` → `kind="shift"`, `shift="chieu"`; `den het ngay 2026-03-01` → `kind="cumulative"`
- `7 ngay qua` thành 2026-02-26..2026-03-04
- `cung ky nam ngoai` cho `thang nay` thành 2025-03-01..2025-03-04
- Cửa sổ Tết các năm trong lịch khớp ngày dương lấy tay từ `calendar.csv`, test ít nhất 3 năm.
- Thêm test cho năm nhuận, đầu năm (as_of 2026-01-02 thì `thang truoc` thuộc năm 2025).

---

### M3. Rulebook thành Knobs (`rules/`)

**Mục đích:** rulebook đổi theo split, nên phải thành tham số có kiểu thay vì hard-code hoặc để LLM đọc tự do mỗi câu.

**`knobs.py`:** `DEFAULT_KNOBS` (mục 2) và `KNOB_DOMAINS`: map tên knob thành tập giá trị hợp lệ, dùng để validate.

**`rulebook_parser.py`:**

```python
def parse_rulebook(text:str, train_text:str|None, llm) -> RuleSpec
```

Thuật toán, theo thứ tự:

1. Tách rulebook thành câu (theo dòng, dấu `.`, bullet). Chuẩn hoá mỗi câu bằng `normalize` (M6).
2. Nếu `train_text` có (lưu sẵn trong repo dưới dạng file dữ liệu, không keyed theo business) thì tính `sha1` của câu đã chuẩn hoá. Câu có trong train thì giữ knob mặc định. Chỉ câu **mới hoặc đổi** mới xử lý ở bước 3.
3. Với mỗi câu cần xử lý, tìm knob liên quan bằng từ khoá (không dấu):
   - `doanh thu|revenue` → nhóm revenue_*
   - `vat|thue` → revenue_include_vat
   - `van chuyen|ship|giao hang` → revenue_include_shipping
   - `voucher|ma giam gia` → revenue_deduct_order_voucher
   - `huy|cancel` → exclude_cancelled
   - `tra hang|hoan hang|return` → returned_policy
   - `ban chay` → bestseller_metric
   - `tuan` → week_start, this_week
   - `thang nay|thang truoc` → this_month
   - `gia von|cost` → cost_method
   - `tet|thang chap|mung` → tet_start/tet_end
4. Với mỗi (câu, knob) gọi LLM dạng **trắc nghiệm**: prompt gồm câu rulebook, tên knob, danh sách lựa chọn từ `KNOB_DOMAINS` đánh số, yêu cầu trả `{"choice": <số>}` (JSON có schema, parse + validate theo M9 — không có guided decoding kiểu vLLM). Áp giá trị vào knob. Với knob bool, lựa chọn là `[true, false, "không liên quan"]`.
5. Câu không có knob nào khớp từ khoá nhưng chứa từ khoá nghiệp vụ lạ (`tinh|bao gom|khong tinh|loai tru|bo qua`) thì thêm vào `knobs.unmapped`.
6. Validate: mọi giá trị trong domain, nếu không thì trả về mặc định và thêm vào `unmapped`.
7. Ghi `knobs` ra log.
8. **Câu rulebook sinh *capability* chứ không sinh knob** (cần cho split public_test): một số luật không phải tham số số/boolean mà là **một khả năng nghiệp vụ mới**. `public_test/rulebook.md` có 3 ngành mới không có trong train: **Mẹ và bé** (số/size theo danh mục, khách thành viên mới theo ngày đăng ký), **Sửa xe** (lượt xe, phiếu bảo hành, nhiều việc ghi chung một ô, thợ), **Cửa hàng điện thoại** (thu máy cũ, trả góp theo kỳ, bảo hành). Luật kiểu này ghi vào `RuleSpec.required_caps` (vd `repair_ticket`, `installment`, `trade_in`, `member_since`, `size_breakdown`) và `RuleSpec.domains`, **không** ép vào knob.
   - Hệ quả kiến trúc: capability mới không mở rộng được bằng `Knobs` → phải có view/metric tương ứng (M4/M5), nếu không thì câu đó chỉ trả lời được qua đường 2 (SQL tự do) và phải bị hạ p.
   - Tên capability định danh **không theo business_id** → một bảng capability chung cho mọi business, đúng nguyên tắc ở mục 0.

**Nghiệm thu:** parse rulebook train ra đúng `DEFAULT_KNOBS` (so với `rulebook_sentences.txt`, sửa DEFAULT cho khớp nếu rulebook train thật nói khác đề). Test với một rulebook sửa tay (đổi tuần bắt đầu từ Chủ nhật, tính cả phí ship) ra knob tương ứng. Parse `public_test/rulebook.md` → `RuleSpec` phải khác train đúng ở 3 ngành mới + các luật thêm/bớt, và **không câu nào bị rơi** (đối chiếu `rulebook_sentences.txt` của cả hai split).

---

### M4. Map schema, bất biến, views (`schema/`)

**Mục đích:** đây là chốt chặn lỗi tương quan theo business, nguồn mất điểm lớn nhất. Cho ra `BizContext` và các view canonical mà cả hai đường dùng.

**`roles.py`:** định nghĩa `ROLES` theo thực thể:

| Thực thể | Role |
|---|---|
| orders | order_id, order_date, order_time, order_status, customer, order_voucher, shipping_fee, vat_amount, vat_rate, order_total, order_channel, order_customer_group, order_shift, order_employee, order_pay_method, order_debt_total, order_paid |
| lines | line_order_id, line_product, qty, qty_base, unit_name, unit_price, line_discount, line_amount, line_cost, line_returned_flag, return_qty, line_is_service |
| products | product_code, product_name, category, unit, unit_cost |
| customers | customer_id, customer_name, phone, customer_group, customer_since |
| lots | lot_id, lot_product, lot_date, lot_qty, lot_cost, expiry_date |
| inventory | inv_product, inv_qty, inv_date |
| debts | debt_customer, debt_amount, debt_date, due_date, paid_amount |
| expenses | exp_date, exp_amount, exp_category |
| payments | pay_order_id, pay_date, pay_amount, pay_method |
| suppliers | supplier_id, supplier_name |
| employees | employee_id, employee_name |
| units | unit_product, unit_name, unit_factor (bảng quy đổi đơn vị) |
| price_history | ph_product, ph_date, ph_new, ph_old |
| deliveries | del_order_id, del_date, del_seq, del_plate, del_employee |

Các role bổ sung ở trên là role **thật sự xuất hiện trong dữ liệu** (kiểm từ `train/data/biz_123/pos.sqlite` và các file xlsx: `thanh_toan`, `nha_cung_cap`, `nhan_vien`, `don_vi_sp`/`DanhSachQuyDoi`, `lich_su_gia`/`BangGia`, `Bảng kê phiếu giao hàng`, `Kênh bán`, `Phương thức thanh toán`, `Nhóm khách hàng`, `MaCaLam`/giờ tạo đơn). Số câu train phụ thuộc từng nhóm: công nợ 116, đơn vị lớn 131, ca sáng/chiều 77, tỉ lệ huỷ 60, phương thức thanh toán 21, nhân viên 18, nhà cung cấp 6 → không map được các role này thì mất ~15% câu.

Mỗi role có `NAME_TOKENS` (danh sách chuỗi không dấu) và `VALUE_TESTS` (hàm trên cột). Ví dụ:

- `qty`: tên chứa `so luong|sl|qty|quantity`, giá trị số, phần lớn nguyên, nhỏ.
- `line_amount`: `thanh tien|tt|amount|total|doanh thu`, giá trị số.
- `order_status`: `trang thai|status|tt don`, ≤ 20 giá trị phân biệt kiểu chuỗi.
- `expiry_date`: `han dung|hsd|exp|het han`, cột ngày.
- `lot_cost`: `gia nhap|gia von|cost|don gia nhap`.

Sau khi chạy `dev/survey.py`, mở rộng `NAME_TOKENS` cho tới khi ≥ 95% cột của các business train có role đúng ghi tay vào `tests/fixtures/expected_roles.json` được heuristic tìm thấy (thiết lập nhãn tay cho 5 business đại diện).

**`mapper.py`:**

```python
def map_business(tables, readme:str, llm) -> list[MappingCandidate]  # sắp theo điểm giảm dần
```

1. **Phân loại bảng:** với mỗi bảng thô và mỗi thực thể, `table_score = Σ best_role_score` trên các role bắt buộc của thực thể. Gán thực thể có điểm cao nhất nếu vượt ngưỡng 0.5. Bảng phẳng (có cả `qty`, `line_amount`, `order_date`, product và không có bảng khác chứa order) được gán `orders_lines_flat`. Khi đó tạo `order_id` tổng hợp là `row_number()` (nếu không có cột id đơn) và coi mỗi dòng là một đơn một dòng.
2. **Chấm role cột:** `score = 0.6*name_score + 0.4*value_score`, trong đó `name_score` là tỉ lệ khớp token (fuzzy, `rapidfuzz.partial_ratio/100`) và `value_score` là kết quả `VALUE_TESTS`.
3. **Cột chưa chắc** (top1 − top2 < 0.15, hoặc top1 < 0.5): gọi LLM trắc nghiệm. Prompt gồm tên bảng, tên cột, 8 giá trị mẫu, đoạn README có nhắc tên cột (tìm bằng chuỗi), 4 role ứng viên và "không có". Đầu ra JSON có schema `{"choice": int}` (parse + validate, xem M9). Dùng thinking mode nếu client hỗ trợ (chỉ chạy một lần cho business).
4. **Giá trị trạng thái** (cột `order_status` và cờ trả hàng): lấy tập giá trị phân biệt. Phân loại bằng từ điển không dấu: cancelled = `huy|cancel|void|that bai|failed`, returned = `hoan|tra hang|return|refund`. Giá trị không nằm trong từ điển thì LLM trắc nghiệm `[cancelled, returned, valid]`. Lưu vào `status_invalid`.
5. **Khoá join:** với mỗi cặp (cột id ở bảng A, cột ở bảng B) tính containment `|A∩B|/|B|`. Chọn cặp containment ≥ 0.95 và tên gần nhất.
6. **Sinh tối đa 3 mapping ứng viên** bằng cách thay phương án top-2 ở các cột có margin nhỏ nhất.

**`invariants.py`:** mỗi hàm trả `(passed:bool, penalty:float, info:dict)`.

- `inv_line_math`: tỉ lệ dòng có `|qty*unit_price − line_discount − line_amount| ≤ 1% line_amount`. Pass nếu ≥ 0.95. Nếu không pass, thử biến thể không trừ giảm giá, và biến thể `line_amount = qty*unit_price*(1+vat_rate)`. Biến thể nào pass thì ghi `line_amount_includes_vat = True` hoặc `discount_already_applied = True`.
- `inv_order_total`: với mỗi đơn có `order_total`, tính `diff = order_total − Σline_amount`. Hồi quy (hoặc so khớp) với `shipping_fee`, `vat_amount`, `−order_voucher`. Ghi các cờ `order_total_includes_ship/vat/voucher`.
- `inv_dates`: tỉ lệ parse ≥ 0.9, khoảng ngày 12–30 tháng, số đơn có `order_date > as_of` (ghi log).
- `inv_join`: tỉ lệ dòng mồ côi ≤ 2%.
- `inv_products`: tỉ lệ sản phẩm trong lines không có trong products ≤ 2%.
- `schema_conf = 1 − min(1, Σ penalty)` của mapping được chọn.

Chọn mapping có tổng penalty thấp nhất. Nếu cả ba có `schema_conf < 0.5` thì giữ cái tốt nhất và `schema_conf` thấp (hạ xác suất mọi câu của business).

**Capabilities:** tập từ khoá suy ra từ role đã map: `line_amount`, `qty`, `cost` (có `lot_cost` hoặc cột giá vốn), `expiry`, `debt`, `customer`, `inventory`, `returns`, `expenses`, `category`, `order_date`, `unit` (quy đổi đơn vị), `payment` (bảng thanh toán), `pay_method`, `supplier`, `employee`, `channel`, `customer_group`, `shift` (giờ tạo đơn), `price_history`, `delivery`, `service_line` (dòng "Phí phục vụ"), `hour`.

Capability mới nhưng **chưa có view/metric** thì `ctx.capabilities` không được chứa nó → M11 sẽ trả unanswerable cho câu cần nó (đúng rulebook §7: "shop không ghi loại thông tin câu hỏi cần, thì không trả lời được").

**`views.py`:**

```python
def build_views(ctx_con, mapping, knobs, as_of:date) -> None
```

Tạo (hoặc thay) các view TEMP với **tên cột canonical cố định**. Mọi view đều cắt `order_date <= as_of` và tương tự cho ngày khác.

- `v_orders(order_id, order_date, order_time, customer, status_valid BOOL, ...)`: `status_valid` false khi trạng thái thuộc `cancelled` (nếu `exclude_cancelled`).
- `v_orders_all(order_id, order_date, status, is_cancelled, is_returned, ...)`: **giữ mọi trạng thái** (kể cả huỷ, trả). Bắt buộc cho `cancel_rate` (rulebook §1: tỉ lệ huỷ = đơn huỷ trong **mọi** đơn đặt của kỳ, mọi trạng thái) — không dùng được `v_orders` vì view đó đã lọc đơn huỷ.
- `v_lines(order_id, order_date, product_code, product_name, category, qty, qty_base, unit_name, line_amount_net, line_cost, is_service BOOL)`:
  - `line_amount_net` = `line_amount` (đã sau giảm giá dòng). Nếu `line_amount_includes_vat` thì chia `(1+vat_rate)`. Nếu `revenue_deduct_order_voucher` thì trừ voucher phân bổ theo tỉ trọng dòng. Nếu `revenue_include_shipping`/`include_vat` thì cộng tương ứng.
  - Chỉ giữ dòng có `status_valid` và áp `returned_policy`: `exclude_order` thì loại đơn có ít nhất một dòng bị cờ trả hàng hoặc có trong bảng `returns` với qty > 0.
  - `qty_base` = số lượng quy về **đơn vị cơ bản** (rulebook §3: "bán chạy theo số lượng quy về đơn vị cơ bản"). Dùng cột quy đổi sẵn nếu có ("Số lượng quy đổi", "Quy ra ĐV lẻ", "SL quy đổi", `don_vi_sp.HeSoQuyDoi`), không có thì suy từ `v_units`; không có bảng quy đổi nào → `qty_base = qty`.
  - `is_service` = dòng "Phí phục vụ" (rulebook §3: không xếp hạng, không đếm, **nhưng vẫn tính vào doanh thu** và vẫn nằm trong mẫu số tỉ trọng nhóm hàng).
- `v_products(product_code, product_name, category, unit, unit_cost, alias_list)` (tên master là tên xuất hiện đa số trong bảng products, khớp theo `product_code`).
- `v_units(product_code, unit_name, unit_factor)`: bảng quy đổi đơn vị (chỉ tạo nếu có capability `unit`).
- `v_payments(order_id, pay_date, pay_amount, pay_method)`: từ bảng thanh toán hoặc cột "Khách đã trả" + "Ngày TT"; dùng cho công nợ, "nợ thêm/trả nợ/thu nợ", tuổi nợ.
- `v_suppliers`, `v_employees`, `v_price_history`, `v_deliveries`: tương tự (chỉ tạo nếu có capability).
- `v_lots`, `v_returns`, `v_expenses`, `v_inventory` tương tự (chỉ tạo nếu có capability).
- **Công nợ:** ưu tiên suy từ `v_orders` + `v_payments` (`order_debt_total` − Σ thanh toán ≤ ngày X), **không** dựa vào bảng `debts` khi shop ghi công nợ ở đơn (rulebook §4). Loại đơn COD và đơn bán qua sàn TMĐT khỏi công nợ (rulebook §4) → cần cờ `is_cod`/`is_marketplace` từ `order_pay_method`/`order_channel`.
- `v_stock(product_code, qty_on_hand)`: từ snapshot nếu có (snapshot gần nhất ≤ as_of), ngược lại `Σ lot_qty (lot_date ≤ as_of) − Σ qty bán hợp lệ`.
- **Bộ view riêng cho 3 ngành mới ở public_test** (quyết định đã chốt: làm cả 3). Dữ liệu của chúng **không** theo mô hình đơn/dòng/sản phẩm, nên cần view riêng. Phát hiện theo **dấu hiệu cấu trúc** (số cột, tên cột), **không** theo `business_id`:
  - *Sửa xe* → `v_repair_tickets(ticket_date, vehicle_line, plate, works_text, works, mechanic, amount, is_warranty)`: mỗi dòng = 1 lượt xe; `works` tách theo dấu phẩy + mẫu số thứ tự (`1)`, `2)`); phiếu bảo hành = ghi chú bảo hành **hoặc** tiền = 0.
  - *Điện thoại* → `v_phone_orders(order_id, order_date, customer, phone, device, amount, trade_in_amount, paid, note)` + `v_installments(order_id, due_date, period_amount, paid_amount, is_overdue)` + `v_warranty_tickets(receive_date, customer, device, imei, issue)` + `v_trade_ins(trade_date, customer, device, price, ref_order_id)`.
  - *Mẹ và bé* → dùng chung `v_lines`, bổ sung `size`/`product_no` từ danh mục và `customer_since` (ngày đăng ký) để phục vụ câu "khách thành viên mới trong tháng" và "số / size".

**Nghiệm thu:** với business train, `SELECT SUM(line_amount_net) FROM v_lines WHERE ...` khớp đáp án tham chiếu cho ít nhất các câu doanh thu đơn giản (kiểm bằng M8). Test với bảng giả có thêm trạng thái "Đã hủy" và đơn có hàng trả, chắc chắn bị loại. Test `v_lines` không chứa đơn sau as_of.

---

### M5. Metric library và executor (`engine/`)

**Mục đích:** nghiệp vụ nằm ở code, nên đường 1 không có lỗi nghiệp vụ ngẫu nhiên.

**`metrics.py`:**

```python
@dataclass
class MetricDef:
    name:str; required_caps:set[str]; value_sql:str  # biểu thức aggregate trên v_lines (alias l)
    needs:list[str]                                    # view cần join

METRICS = {
 "revenue":  MetricDef("revenue", {"line_amount"}, "SUM(l.line_amount_net)", []),
 "qty":      MetricDef("qty", {"qty"}, "SUM(l.qty)", []),
 "qty_base": MetricDef("qty_base", {"qty"}, "SUM(l.qty_base)", []),   # quy về đơn vị cơ bản
 "orders":   MetricDef("orders", {"order_date"}, "COUNT(DISTINCT l.order_id)", []),
 "customers":MetricDef("customers", {"customer"}, "COUNT(DISTINCT l.customer)", []),
 "aov":      MetricDef("aov", {"line_amount"}, "SUM(l.line_amount_net)/NULLIF(COUNT(DISTINCT l.order_id),0)", []),
 "cancel_rate": MetricDef("cancel_rate", {"order_date"}, "100.0*SUM(is_cancelled)/NULLIF(COUNT(*),0)", ["v_orders_all"]),
 "profit":   ...,  # revenue − Σ qty*unit_cost (xem dưới)
 "stock":    ...,  # từ v_stock
 "stock_value": ...,  # tồn × giá vốn 1 đơn vị cơ bản ghi trong danh mục (rulebook §5)
 "debt":     ...,  # SUM(order_debt_total − Σ thanh toán ≤ ngày X) theo khách, > 0, loại COD/TMĐT (rulebook §4)
 "debt_age": ...,  # tuổi nợ = as_of − order_date; đơn đặt hôm nay có tuổi nợ 0 (rulebook §4)
 "expiring": ...,  # lot còn tồn, expiry_date ∈ [as_of, as_of+N]
 # metric cho 3 ngành mới (view riêng ở M4):
 "repair_tickets": ...,  # COUNT/SUM(v_repair_tickets) theo thợ, theo việc, theo biển số; bỏ phiếu bảo hành
 "installments": ...,  # SUM phần góp còn nợ trong kỳ, và số kỳ quá hạn (hạn góp < ngày hỏi)
 "members_new": ...,  # COUNT khách có customer_since trong tháng (kể cả chưa mua)
 "size_breakdown": ...,  # số lượng theo Số/Size của một mặt hàng (lấy theo cột danh mục, không đoán theo tên)
}
```


`compile_spec` sinh SQL theo khung:

```sql
SELECT <subject_expr> AS key, <value_sql> AS value
FROM v_lines l
[JOIN ... theo needs]
WHERE <time windows OR'd> AND <filters>
GROUP BY key
ORDER BY value DESC, <code_expr> ASC
LIMIT <k>
```

Quy tắc:

- `subject` thuộc `{product, category, customer, day, week, month}`. `<code_expr>` là `product_code` (hoặc mã khách) để tie-break theo code tăng dần đúng luật ranking; **không có mã thì theo tên** (rulebook §9).
- `bán chạy` không nêu tiêu chí thì metric = `knobs.bestseller_metric`; giá trị `qty` ở đây nghĩa là `qty_base` (đơn vị cơ bản). Dòng `is_service` ("Phí phục vụ") không được xếp hạng, không được đếm (rulebook §3).
- `order = "asc"` cho "chậm nhất/ít nhất".
- `compare_periods`: sinh hai truy vấn con (`main`, `base`), kết quả `(main−base)/NULLIF(base,0)*100` cho percent.
- `compare_periods` có thêm biến thể **chênh lệch tuyệt đối** khi câu hỏi hỏi "hơn/kém bao nhiêu (số, không phải %)": trả `main − base`, giữ đơn vị của số đo, ra **số âm** khi kém (rulebook §1). Phân biệt bằng từ khoá: có "phần trăm|%|mấy phần trăm" → percent; có "hơn bao nhiêu|kém bao nhiêu|chênh lệch" mà không có "%" → số.
- `conditions` (điều kiện kép như "bán chậm nhưng tồn nhiều"): CTE tính `rank_by_qty` và `rank_by_stock`, định nghĩa ngưỡng là phân vị 25% thấp của qty và 75% cao của stock trong cùng khoảng (ngưỡng nằm trong `config.py`, chỉnh sau khi đối chiếu với câu train).
- **Giá vốn — hai khái niệm khác nhau, không gộp thành một knob:**
  - *Giá vốn dòng bán* (dùng cho lãi gộp): rulebook §5 nói rõ lấy **giá vốn ghi trên dòng bán** (`line_cost`), **không** tự tính lại từ phiếu nhập hay từ lô. Shop không có cột giá vốn trên dòng → câu lãi gộp/lãi ròng là unanswerable (rulebook §7).
  - *Giá vốn bình quân theo lô* (khi shop không ghi giá vốn dòng, hoặc cho giá trị tồn kho): hai biến thể `wavg_by_lot` (giá vốn đơn vị của sản phẩm = Σ(lot_qty×lot_cost)/Σlot_qty trên mọi lô có `lot_date ≤ as_of`) và `wavg_up_to_sale_date` (tính tới ngày bán). M8 chọn biến thể khớp câu train và ghi vào `knobs.cost_method` mặc định.
- Sắp hết hạn: `expiring_within_days` lấy từ câu (mặc định 30 nếu câu nói "sắp" không nêu số, đây là chỗ calibration sẽ hạ p nếu sai).

**`executor.py`, `sandbox.py`:**

```python
def run_sql(con, sql:str, timeout_s:float=20, max_rows:int=1000) -> ExecResult  # (columns, rows, error)
```

Dùng connection `read_only` đã có view. Chạy trong thread, `con.interrupt()` khi quá timeout. Từ chối mọi câu không bắt đầu bằng `SELECT` hoặc `WITH`, và mọi câu chứa `ATTACH|COPY|INSTALL|LOAD|PRAGMA|CREATE|INSERT|UPDATE|DELETE|DROP|read_csv|read_parquet` (so khớp không phân biệt hoa thường).

**Nghiệm thu:** test từng metric trên bảng nhỏ dựng tay (10 đơn, có đơn huỷ, đơn trả, hai sản phẩm bằng điểm để kiểm tie-break theo code). Test sandbox chặn câu `DROP TABLE`, timeout đúng.

---

### M6. Chuẩn hoá, entity linking, BM25 (`text/`)

**Mục đích:** câu hỏi không dấu/viết tắt phải khớp được với tên trong dữ liệu mà không cần LLM khôi phục dấu.

**`normalize.py`:**

```python
def nd(s:str) -> str          # NFC → bỏ dấu (kể cả đ→d) → lower → gộp khoảng trắng
def expand_abbrev(s_nd:str) -> str
```

`ABBREV` (dict, ở `config.py`) khởi tạo: `sp→san pham, dc→duoc, ko→khong, k→khong (chỉ khi đứng riêng, không đứng sau số), kh→khach hang, nv→nhan vien, hsd→han su dung, sl→so luong, dt→doanh thu, ln→loi nhuan, tt→thanh toan, ntn→nhu the nao, bn→bao nhieu, hh→hang hoa, ton→ton kho (giữ nguyên "ton", chỉ thêm nhãn)`. Mở rộng bằng cách quét câu hỏi train tìm token không có trong từ điển tiếng Việt không dấu của dữ liệu (dev step, kết quả lưu vào file từ điển trong repo, không dùng câu test).

Câu train viết tắt **và** sai chính tả nhiều (`dthu`, `bnhiu`, `vs`, `check giùm`, `k`, `dc`, `sp`, `mỗi`/`moi`) → phải mine từ **câu hỏi** train chứ không chỉ từ tên cột trong dữ liệu. Đo lại bằng: tỉ lệ token lạ còn sót trên toàn bộ câu train (mục tiêu < 5%); đây là nút thắt rẻ nhất để tăng tỉ lệ khớp ở M8.

**`entity_linker.py`:**

```python
def build_entity_index(con, mapping) -> EntityIndex   # từ v_products, v_customers, category
def link_entities(q_nd:str, index) -> list[EntityMatch]  # (span, kind, canonical_name, code, score)
```

- Sinh n-gram từ 1 đến 5 token của câu, bỏ n-gram toàn stopword (`la, cua, bao nhieu, nhat, thang, tuan, ...`).
- Với mỗi n-gram tính điểm với mọi tên (đã bỏ dấu): `max(rapidfuzz.fuzz.token_set_ratio, partial_ratio)/100`, cộng thưởng nếu khớp bắt đầu bằng cùng token. Giữ điểm ≥ 0.8.
- Loại các n-gram trùng vùng, ưu tiên span dài và điểm cao. Mỗi span giữ top-3.
- Nếu n-gram khớp cả tên sản phẩm và danh mục thì giữ cả hai và gán `kind`.

**`bm25.py`:** `BM25(docs_nd).topk(q_nd, n)` bằng `rank_bm25` hoặc tự cài. Index trên câu hỏi train đã qua `nd`. Không dùng embedding.

**Nghiệm thu:** test `nd("Cà phê sữa")=="ca phe sua"`, `nd("Đường")=="duong"`. Với bảng sản phẩm train, ≥ 90% tên sản phẩm được nhắc trong câu hỏi train link ra đúng mã SP ở top-1 (đo trên các câu có đáp án kiểu string/list).

---

### M7. Formatter (`fmt/formatter.py`)

```python
def to_submission(result:ExecResult, spec:Spec|None, out_type:str, ctx, knobs) -> Answer
```

- `string`: lấy ô đầu tiên của hàng đầu, lấy tên master từ `v_products` theo `product_code`. Nếu kết quả là mã SP thì đổi sang tên master. Trả **nguyên văn trong dữ liệu** (giữ dấu tiếng Việt) — rulebook §9 chỉ cho phép bỏ dấu khi *so khớp*, không khi *ghi*.
- `list`: cột `key` theo thứ tự truy vấn, đã tie-break `(−value, code asc)`. Nếu ít hơn k phần tử thì trả hết. Phần tử có thể là số hoặc chuỗi (vd "tồn theo đơn vị lớn" trả `[16, 1]`).
- `number`: làm tròn theo rulebook §9 — tiền → số nguyên VND, làm tròn về đồng, **nửa đồng làm tròn lên**; số khác → 2 chữ số thập phân. Số nguyên thì xuất `int` (JSON number, không kèm đơn vị, không dấu phân cách nghìn).
- `percent`: giá trị `(new−old)/old*100` làm tròn 2 chữ số thập phân. Nếu `old == 0` thì abstain (không xác định). Giảm thì ra **số âm** (rulebook §1).
- `date`: ISO `YYYY-MM-DD`; **câu hỏi theo tháng** ("doanh thu tháng nào lớn nhất") → `"YYYY-MM"` (rulebook §9).
- `boolean`: `bool`.
- `table`: `{"columns":[snake_case_nd...], "rows":[[...]]}`, tên cột lấy từ alias của truy vấn (snake_case không dấu).
- Kết quả rỗng: nếu intent là aggregate (đếm/tổng) và các entity đều tồn tại thì trả `0`, ngược lại `abstain`. Với rank/lookup mà rỗng thì abstain.
- Nếu câu "... nhất" mà hạng 1 và hạng 2 bằng nhau thì abstain (reference đã loại ca này nên đây là dấu hiệu sai).

**Nghiệm thu:** test mỗi type, test tie-break theo code tăng dần, test percent `-12.45` (không phải `-0.1245`), test k lớn hơn số ứng viên, test `date` theo tháng ra `YYYY-MM`, test `list`/`table` khớp qua `alias` từng phần tử.

---

### M8. Enumerate-and-match trên train và ngân hàng ví dụ (`dev/`)

**Mục đích:** (a) kiểm chứng metric library và knob trên đáp án thật, (b) tìm intent chưa phủ, (c) tạo ngân hàng ví dụ (câu hỏi → spec) đã xác minh bằng thực thi. Đây là bước kiểm tra tính đúng đắn của toàn bộ phần deterministic, nên **bắt buộc trước khi nối LLM**.

**`enumerate_match.py`:** với mỗi câu train:

1. Chạy M2 (khoảng thời gian), M6 (entity), M4/M5 (views).
2. Sinh ứng viên spec bằng luật từ khoá:
   - `metric`: `doanh thu|ban duoc bao nhieu tien`→revenue, `bao nhieu (cai|ly|chiec)|so luong`→qty (có nêu đơn vị → `qty_base`), `bao nhieu don`→orders, `loi nhuan|loi gop`→profit, `ton`→stock, `no`→debt, `ty le huy`→cancel_rate, `het han`→expiring. Nếu câu mơ hồ, liệt kê **tất cả** metric hợp lệ.
   - `intent`: `nhat|top|nhieu nhat|it nhat`→rank (limit 1, hoặc k nếu có `top k`), `so voi|tang|giam`→compare_periods, `co ... khong`→check_bool, `liet ke|danh sach|nhung`→filter_list.
   - Với mỗi slot còn mơ hồ (khoảng thời gian nào, biến thể giá vốn, biến thể knob), liệt kê tổ hợp (tối đa 24).
3. `compile_spec` → `run_sql` → `to_submission` → `is_correct`. Giữ các spec đúng, ưu tiên spec ít slot nhất.
4. **LLM bootstrap** cho câu còn lại (sau khi M9 có): sinh 8 spec với temperature 0.7, giữ spec nào đúng khi thực thi.
5. Ghi `bank.jsonl` (id, business, question_nd, spec) và `unmatched.jsonl` (câu, đáp án tham chiếu, lý do thất bại: không spec nào khớp, hoặc thực thi lỗi).

**`build_bank.py`:** từ `bank.jsonl` dựng index BM25 (M6) lưu `bank_index.pkl` và nhãn intent/metric cho kNN.

**Quy trình dev bắt buộc:** sau mỗi lần chạy, mở `unmatched.jsonl`, nhóm theo lý do, và sửa một trong: từ điển viết tắt, `NAME_TOKENS`, definition metric, hoặc thêm intent. Lặp lại tới khi **tỉ lệ khớp ≥ 90% các câu có đáp án khác null** (đây là phần deterministic, nếu thấp thì đáp án tham chiếu đang dùng quy tắc ta chưa hiểu). Câu `null` được xử lý ở M11.

**Cổng M8 đo theo intent, không chỉ một số chung** (tránh overfit code cho train): lõi `revenue / orders / qty / period / compare` phải ≥ 95%; intent dài đuôi (`debt`, `stock`, `cost`, `pharmacy`, `construction`, `price_effect`) ≥ 80%, phần dưới ngưỡng phải ghi rõ lý do trong `calibration.md`. Tổng ≥ 90% là điều kiện cần nhưng không đủ.

**Train không có** business sửa xe / điện thoại / mẹ và bé → M8 **không kiểm được** phần này (170/1000 câu public test). Với các domain mới chỉ có thể dựa vào rulebook (M3) + view/metric mới, và phải chấp nhận rủi ro → mọi câu thuộc domain mới mặc định hạ `p` hơn (xem M12).

---

### M9. LLM client và đường 1 (Spec) (`llm/`, `paths/path1_spec.py`)

**`llm/client.py`:**

```python
class LLM:
    def __init__(self, cfg): ...      # model_path, dtype, max_len đọc từ config.py (không hard-code tên model)
    def generate(self, prompts:list[str], *, json_schema:dict|None=None,
                 max_tokens:int=512, temperature:float=0.0, seed:int=0,
                 thinking:bool=False) -> list[str]
```

Dùng **API LLM OpenAI-compatible** (`Qwen3-4B`), không tự host model:

- `base_url`, `api_key`, `model` đọc từ `config.py` / biến môi trường — **không** hard-code, **không** commit key. API dùng được cả ở vòng private (Docker của đội).
- Ép JSON bằng `response_format={"type":"json_schema","json_schema":{...}}`; endpoint từ chối → fallback `{"type":"json_object"}` → cuối cùng là prompt + parse + validate, hỏi lại tối đa 1 lần; vẫn sai thì coi như mẫu hỏng (không làm hỏng cả lô).
- **Song song 16 luồng** (không giới hạn RPM): `asyncio` + `httpx`, retry theo backoff khi gặp 429/5xx. Mọi lời gọi phải trả kết quả **đúng thứ tự input** → gom theo index, không dựa vào thứ tự hoàn thành.
- `temperature=0`, `seed` cố định (nếu endpoint hỗ trợ) để tái lập được.
- `thinking=True` → dùng tham số reasoning của endpoint nếu model hỗ trợ, cho bước khó (map cột chưa chắc, leo thang).

**`llm/schemas.py`:** `SPEC_SCHEMA` (JSON schema với `enum` cho `intent, metric, agg, subject, order, output`), `SQL_SCHEMA = {"answer_type": enum, "sql": string}`, `MCQ_SCHEMA = {"choice": integer}`.

**`paths/path1_spec.py`:**

```python
def run_path1(q:Question, ctx:BizContext, knobs:Knobs, windows, entities, bank, llm, k:int=3) -> list[Candidate]
```

1. `q_nd = expand_abbrev(nd(q.text))`. Lấy top-18 ví dụ gần nhất từ bank bằng BM25.
2. Chia 18 ví dụ thành 3 bộ 6 (round-robin theo thứ hạng: bộ 1 lấy hạng 1,4,7..., bộ 2 lấy 2,5,8..., bộ 3 lấy 3,6,9...).
3. Prompt cho mỗi bộ (theo `llm/prompts.py`, template cố định) gồm: (a) chỉ dẫn "chỉ trả JSON theo schema", (b) `ctx.card`, (c) các knob khác mặc định kèm giá trị hiện tại (một dòng mỗi knob), (d) danh sách khoảng thời gian đã tính, (e) ứng viên entity (tên master, code, điểm), (f) 6 ví dụ (`Câu hỏi: ... → Spec: ...`), (g) câu hỏi hiện tại.
4. Sinh k=3 (mỗi prompt một lần, greedy), parse JSON, chuẩn hoá spec (`filters` sắp theo `(field,op,value)`, giá trị chuỗi bỏ dấu).
5. Biên dịch qua `compile_spec`, chạy `run_sql`, định dạng bằng M7.
6. Vote theo `canon_key(answer)`. Candidate trả về gồm `votes` và `k`.
7. Nếu cả ba spec parse lỗi hoặc `intent == "other"` thì trả list rỗng (đường 2 sẽ làm).

**Câu dễ (tiết kiệm):** nếu kNN intent (nhãn bank của top-1 BM25) trùng với intent LLM mẫu đầu và mọi entity có điểm ≥ 0.95 thì chỉ sinh 1 mẫu và đặt `k=1`. Mặc định ban đầu là luôn chạy k=3, sau này mới bật tối ưu.

**Nghiệm thu:** trên validation chia theo business — holdout cố định **6/30 business** (theo seed, trong `config.py`), không lấy bank từ business đó; `spec_correct_rate = tỉ lệ câu mà candidate vote cao nhất đúng`. Ghi lại theo intent. Đây là số đo chính cho đường 1.

---

### M10. Đường 2 (SQL tự do) (`paths/path2_sql.py`)

**Mục đích:** đường kiểm chứng độc lập (biểu diễn khác) và phủ câu ngoài taxonomy.

```python
def run_path2(q, ctx, knobs, windows, entities, bank, llm, k:int=5) -> list[Candidate]
```

1. Prompt: DDL các view canonical (liệt kê `v_lines, v_products, ...` kèm cột và kiểu, in từ `information_schema`), ghi chú "đã áp rulebook: chỉ dùng view, tuyệt đối không dùng bảng `raw_*`", khoảng thời gian đã tính (dạng `DATE '2026-02-23'`), ứng viên entity, quy tắc xếp hạng (`ORDER BY value DESC, code ASC`), 4 ví dụ `(câu hỏi → {"answer_type","sql"})` lấy từ bank, trong đó SQL **biên dịch từ spec đã xác minh** bằng `compile_spec`, và câu hỏi hiện tại.
2. Sinh k=5 với bộ ví dụ khác nhau (xoay vòng như đường 1), JSON theo `SQL_SCHEMA`.
3. Kiểm tra SQL: chỉ `SELECT/WITH`, không đụng `raw_*`. Vi phạm thì bỏ mẫu.
4. `run_sql` → `to_submission` với `out_type = answer_type` (dùng chung formatter, `spec=None`). Mẫu lỗi hoặc rỗng thì **sửa một lần**: gửi lại prompt kèm lỗi, sinh 1 mẫu thay thế.
5. Vote theo `canon_key`. Trả `Candidate` có `votes, k`.

**Nghiệm thu:** `path2_correct_rate` trên cùng validation. In ma trận đồng thuận: tỉ lệ (path1 đúng/sai) × (path2 đúng/sai) × (đồng ý/bất đồng), đây là số liệu quyết định giá trị của hai đường (nếu `P(đúng | đồng ý)` không cao hơn rõ rệt `P(đúng | chỉ path1)` thì giữ đường 2 chỉ cho câu `intent=other`).

---

### M11. Khả năng trả lời (`decide/answerability.py`)

```python
@dataclass
class AnswerCheck:
    answerable: bool; p_unanswerable: float; reason: str; entity_missing: bool
def check_answerable(spec_or_intent, windows, entities, ctx, knobs) -> AnswerCheck
```

Quy tắc, áp theo thứ tự:

1. **Thiếu capability:** `METRICS[metric].required_caps - ctx.capabilities` khác rỗng thì `p_unanswerable = 0.9 * ctx.schema_conf`. Lý do dạng "Dữ liệu không có <cap>".
2. **Ngoài phạm vi dữ liệu:** khoảng thời gian `main` hoặc `base` có `end < ctx.date_min` hoặc `start > ctx.date_max` thì `p_unanswerable = 0.8`. Nếu chỉ chồng một phần thì không đặt là unanswerable (đây là trường hợp dữ liệu thiếu một phần, để calibration xử lý).
3. **Tương lai:** `start > as_of` thì `p_unanswerable = 0.85`.
4. **Entity không tồn tại:** cụm tên bị `link_entities` bỏ lỡ (điểm cao nhất < 0.8 nhưng cụm đó không nằm trong stopword/metric) thì `entity_missing = True`, **abstain** (không gán unanswerable) cho tới khi M8 chỉ ra trong câu `null` của train có thật nhiều trường hợp này (khi đó nâng `p_unanswerable` lên theo tỉ lệ đo được).
5. **Phân loại nguyên nhân `null` trong train:** viết `dev/null_causes.py` đọc câu train có `answer: null`, chạy `check_answerable`, in bảng (nguyên nhân dự đoán × số câu). Các câu `null` mà `check_answerable` bỏ sót là việc cần bổ sung luật ở bước 1–4.

**Nghiệm thu:** trên train, `recall_unanswerable` (câu `null` được phát hiện) và `false_unanswerable_rate` (câu có đáp án mà bị đánh unanswerable). Mục tiêu `false_unanswerable_rate` ≈ 0 vì mỗi lỗi là −1.

---

### M12. Quyết định, calibration, leo thang (`decide/`)

**`features.py`:** vector đặc trưng cho một câu:

```
schema_conf, n_unmapped_rules_related (0/1), agree_p1_p2 (0/1), p1_vote_frac,
p2_vote_frac, p1_empty, p2_empty, knn_intent_agree (0/1), min_entity_score,
n_unresolved_time, result_is_empty, result_negative, result_ratio_vs_neighbor
(giá trị / trung bình cùng chỉ số các kỳ liền trước, log), intent (one-hot),
out_type (one-hot), n_joins, esc_choice (sau leo thang)
```

**`decider.py`:**

```python
def decide(cands1, cands2, check:AnswerCheck, feats, model, cfg) -> Answer
```

Thuật toán:

1. Nếu `check.p_unanswerable ≥ 0.5` và `schema_conf ≥ 0.6` thì trả `unanswerable` kèm `reason`.
2. Chọn `top1 = cands1[0]`, `top2 = cands2[0]` (vote cao nhất). Ứng viên đáp án `c`:
   - nếu `canon_key(top1) == canon_key(top2)` thì `c = top1`.
   - nếu một đường rỗng thì `c` = đáp án đường còn lại, kèm cờ `single_path` (chỉ cho phép khi `intent=other` hoặc mô hình calibrated cho phép).
   - nếu bất đồng thì chuyển `escalate` (bên dưới), còn không có kết quả thì `abstain`.
3. `p = model.predict_proba(feats)` (theo `out_type`), `p_adj = p − margin` (margin ở config, mặc định 0.05, chỉnh theo chênh calibration fold lạ/quen ở M13).
4. `p_adj > 0.5` thì trả `c`, ngược lại `abstain`.

**Phiên bản khởi đầu (trước khi có model):** `p = 0.9` nếu `agree_p1_p2` và `schema_conf ≥ 0.8` và `min_entity_score ≥ 0.9` và `n_unresolved_time == 0`, ngược lại `p = 0.3`.

**`calibrate.py` và `dev/run_train.py`:**

1. `run_train.py` chạy pipeline với **business bị giữ ra** (ngân hàng ví dụ không chứa câu của business đó) cho mọi câu train, ghi `features.parquet` gồm vector đặc trưng, `candidate_chosen`, `correct` (0/1).
2. `calibrate.py` fit `LogisticRegression(C=1.0)` (sklearn) cho mỗi nhóm `out_type`. Nhóm nào ít hơn 50 mẫu thì dùng mô hình chung. Dùng `GroupKFold` theo business để đo `ECE` và PA mô phỏng; chọn margin sao cho PA mô phỏng cao nhất trên fold. Lưu model bằng `joblib` vào `models/calibrator.pkl`.
3. Xuất báo cáo `calibration.md`: ECE, PA theo `out_type`, PA mô phỏng so với PA nếu luôn trả lời, và bảng intent có precision < 0.5 (các intent này mặc định abstain: thêm vào `cfg.blocked_intents`).

**`escalate.py`:** khi bất đồng hoặc `|p − 0.5| < 0.1`: prompt (thinking mode, giới hạn token cố định) gồm câu hỏi, ngữ cảnh ngắn, hai phương án A (spec/SQL + kết quả) và B, yêu cầu chọn `{"choice": 1|2|0}` (0 là không phương án nào đúng). Kết quả đưa vào feature `esc_choice` và tính lại `p`. Khi `choice == 0` thì abstain.

**Nghiệm thu:** `PA_simulated` trên validation (leave-one-business-out) ≥ PA của baseline "luôn trả lời đường 1". Báo cáo `coverage` và `precision`.

---

### M13. Orchestrator và logging (`predict.py`)

```
main():
  cfg = load_config(); llm = LLM(cfg)
  split = cfg.split                                   # "train" | "public_test"
  questions = read(f"{split}/questions.jsonl"); rulebook = read(f"{split}/rulebook.md")
  cal = load_calendar(f"{split}/calendar.csv")
  rules = parse_rulebook(rulebook, TRAIN_RULEBOOK_TEXT, llm)   # RuleSpec: knobs + domains + required_caps
  group questions by business_id (dùng business_id chỉ để tìm thư mục dữ liệu)
  for biz in sorted(businesses):
      ctx = load_or_build_ctx(f"{split}/data/{biz}", rules.knobs, llm)   # M1, M4, cache theo sha256
      for q in sorted(questions_of_biz, key=id):     # sort cố định
          answers[q.id] = tier0_answer(q)            # abstain mặc định
  # Tầng 1: câu có đủ tín hiệu dễ
  # Tầng 2: câu còn lại + leo thang
  # Sau mỗi lô (≤ 200 câu) ghi atomically
```

- **Tầng 0:** mọi câu bắt đầu bằng `abstain`, ghi file ngay.
- **Tầng 1:** chạy `time → entity → path1 (k=3) → path2 (k=5) → check → decide`. Câu nào có quyết định cuối (không cần leo thang) thì ghi.
- **Tầng 2:** câu cần leo thang chạy `escalate` rồi `decide` lại.
- **Ghi nguyên tử:** `write(tmp); os.replace(tmp, cfg.out_path)` sau mỗi lô, với `cfg.out_path` mặc định `public_test/submission.jsonl` (đúng nơi BTC chấm, theo mẫu lifemate) và `cfg.log_dir` mặc định `public_test/logs/`.
- **Đồng hồ an toàn:** `cfg.deadline_s = 5.25*3600` tính từ đầu `main()`. Nếu quá thì dừng Tầng 2, ghi file, thoát (câu chưa xử lý giữ `abstain`). Quyết định trả lời **không** phụ thuộc đồng hồ.
- **Ngân sách LLM:** 1000 câu × (k₁ + k₂) lời gọi API là con số lớn. Chạy **16 luồng song song** (không giới hạn RPM), có backoff khi 429. `cfg.deadline_s` mặc định **5,25·3600** (đổi được trong `config.py`): khi còn dưới 25% thời gian thì bỏ Tầng 2, dưới 50% thì giảm `k₂` (đường 2) — để luôn kịp ghi file. Không được để deadline cắt ngang giữa lô mà mất file.
- **Log:** `{cfg.log_dir}/<id>.json` gồm `id, answer, elapsed_s, windows, entities, spec_samples, sqls, exec_results, knobs_used, schema_conf, features, p, p_adj, reason`. Ghi thêm `{cfg.log_dir}/_biz_<hash>.json` cho mỗi business (mapping, invariants, capabilities) và `_knobs.json`.
- **Tái lập:** mọi `generate` greedy, seed cố định, sort đầu vào. Viết `dev/repro_check.py` chạy hai lần liên tiếp trên 300 câu validation, in số câu đổi đáp án và `|ΔPA|`. Mục tiêu ΔPA < 0.01. Nếu chênh nhiều, kiểm tra các câu có `|p_adj − 0.5| < 0.05` (nguồn nondeterminism chính) và nâng margin cho nhóm đó.

**Nghiệm thu:** chạy `predict.py` trên thư mục train giả lập test, ra `submission.jsonl` hợp lệ cho 100% id, đúng định dạng từng type, chạy evaluate ra PA khớp `run_train.py` (±0.01).

---

### M14. Ablation (quyết định cuối về hai đường)

Dùng `run_train.py` ghi PA mô phỏng cho 4 cấu hình trên cùng validation: (a) chỉ đường 1, (b) chỉ đường 2, (c) cả hai, đồng thuận làm feature, (d) (c) cộng leo thang. Giữ cấu hình cao nhất. Nếu (c) không hơn (a) ≥ 0.02 PA thì đặt đường 2 chỉ chạy cho `intent=other` và các câu đường 1 không phủ.

---

## 4. Thứ tự làm và phụ thuộc

```
M0 ─► M1 ─► M2 ─┐
        M3 ─────┼─► M4 ─► M5 ─► M7 ─► M8 ──► (cổng: ≥90% câu có đáp án khớp bằng code)
        M6 ─────┘                         │
                                          ▼
                        M9 ─► M10 ─► M11 ─► M12 ─► M13 ─► M14
```

**Cổng sau M8 là điểm kiểm soát quan trọng nhất.** Nếu phần deterministic chưa tái hiện được đáp án tham chiếu của train thì việc thêm LLM chỉ che lỗi chứ không sửa lỗi.

---

## 5. Điều chưa biết cần tự điền khi gặp dữ liệu thật

| Chưa biết | Nơi giải quyết | Mặc định tạm |
|---|---|---|
| Cột và định dạng của `calendar.csv` | M2 | **Đã biết**: `date,weekday,lunar_day,lunar_month,lunar_year,lunar_leap,holiday`, phủ 2024-01-01..2027-12-31. Có `lunar_leap` → xử lý được tháng nhuận |
| Chữ chính xác của rulebook train | M3, `rulebook_sentences.txt` | `DEFAULT_KNOBS` theo mô tả đề |
| Dung sai number, cách chấm list/table | M0 `compare.py` | **Đã chốt theo rulebook §9**: số/percent khớp tuyệt đối sau khi làm tròn; list có thứ tự; table so từng ô; `alias` theo từng phần tử |
| Cách tính giá vốn chính xác | M8 | Tách 2 khái niệm: lãi gộp dùng giá vốn dòng bán; còn lại thử cả hai biến thể bình quân theo lô |
| Ngưỡng "sắp hết hạn", "bán chậm", "tồn nhiều" | M5, M8 | 30 ngày, phân vị 25%/75% |
| Tỉ lệ và nguyên nhân câu `null` | M11 `null_causes.py` | Chỉ thiếu capability, ngoài phạm vi, tương lai |
| Model LLM chạy được trên máy đích | M9 `llm/client.py` | **Đã chốt**: API OpenAI-compatible `Qwen3-4B`, `base_url`/`api_key`/`model` trong `config.py` + env, 16 luồng song song, `response_format=json_schema`. Còn lại: cần endpoint/key thật và mức phí/giới hạn thực tế |
| View/metric cho 3 ngành mới (sửa xe, điện thoại, mẹ và bé) | M3, M4, M5 | Train không có → thiết kế mới theo rulebook; phủ 170/1000 câu public test |
| Nguồn quy đổi đơn vị ở từng shop | M4 `v_units` | Cột quy đổi sẵn > bảng quy đổi > README; thiếu hết thì `qty_base = qty` |
