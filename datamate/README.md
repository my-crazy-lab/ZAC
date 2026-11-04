# DataMate

Trả lời **câu hỏi nghiệp vụ** về dữ liệu bán hàng của một doanh nghiệp, chỉ từ các file thô (`.xlsx`, `.csv`, `.sqlite`) mà shop xuất ra — không có schema chuẩn, không có API, mỗi shop một kiểu.

> Bài toán 1/2 của đội thi tại **Zalo AI Challenge 2026**. Xem [`README.md` gốc repo](../README.md) để so sánh với bài LifeMate.

---

## Mục lục

- [Bài toán](#bài-toán)
- [Dữ liệu](#dữ-liệu)
- [Kiến trúc giải pháp](#kiến-trúc-giải-pháp)
- [Cấu trúc code mục tiêu](#cấu-trúc-code-mục-tiêu)
- [Cài đặt](#cài-đặt)
- [Chạy](#chạy)
- [Định dạng nộp bài](#định-dạng-nộp-bài)
- [Lộ trình milestone](#lộ-trình-milestone)
- [Nguyên tắc bắt buộc](#nguyên-tắc-bắt-buộc)
- [Tài liệu](#tài-liệu)

---

## Bài toán

**Đầu vào:** câu hỏi tiếng Việt (`question`) + `as_of_date` (là "hôm nay" của câu hỏi) + dữ liệu thô của shop được hỏi.

**Đầu ra:** một giá trị có kiểu: `number`, `percent`, `date`, `boolean`, `string`, `list`, `table`, hoặc `unanswerable` (không trả lời được).

**Cách chấm:** đúng **+1**, sai **−1**, bỏ trống **0** → chỉ số **PA** = tổng điểm / số câu. Vì vậy đoán bừa có thể âm; câu không trả lời được thì abstain là an toàn.

**Điểm khó của bài toán** là không phải SQL mà là **ngữ nghĩa nghiệp vụ**:

- Doanh thu = tổng thành tiền dòng, **không** trừ giảm giá cả đơn, **không** cộng VAT, **không** gồm phí giao.
- Đơn trả hàng (kể cả trả một phần) → loại **cả đơn**; đơn đang giao vẫn tính.
- "Bán chạy" xếp theo **số lượng quy về đơn vị cơ bản**, không phải số dòng hay số tiền.
- Công nợ, tuổi nợ, tồn kho, giá vốn, lô hàng, hạn dùng — mỗi ngành một cách tính.
- Mỗi câu có "luật riêng" trong `rulebook.md` (đổi theo split) → phải **áp luật đúng một lần, ở tầng view**, không để LLM tự diễn giải.

Bộ luật đầy đủ: `train/rulebook.md` và `public_test/rulebook.md`.

---

## Dữ liệu

### Bố cục

```text
datamate/
├── train/
│   ├── questions.jsonl      # {id, business_id, question, as_of_date}
│   ├── answers.jsonl        # {id, type, answer, alias}
│   ├── rulebook.md          # luật nghiệp vụ bộ train
│   ├── calendar.csv         # lịch dương + âm, 2024-01-01 → 2027-12-31
│   └── data/biz_101..biz_130/   # dữ liệu 30 shop train
└── public_test/
    ├── questions.jsonl      # 1000 câu, 14 business dev_001..dev_014
    ├── rulebook.md          # bộ test: thêm 3 ngành mới, ~12 luật mới, bỏ 3 luật
    ├── calendar.csv
    └── data/dev_001..dev_014/
```

### Quy mô

| | Train | Public test |
|---|---|---|
| Số shop | 30 (`biz_101`…`biz_130`) | 14 (`dev_001`…`dev_014`) |
| Số câu | 3000 | 1000 |

Phân bố 3000 câu train theo `type`: `number` 1884 · `percent` 578 · `list` 193 · `date` 145 · `string` 88 · `unanswerable` 70 · `boolean` 23 · `table` 19.

### Định dạng

**`questions.jsonl`**

```json
{"id": "q_001883280e83", "business_id": "biz_128", "question": "tháng này tổng giá trị các phiếu nhập hàng là bao nhiêu", "as_of_date": "2026-09-07"}
```

**`answers.jsonl`** — `answer = null` ⇔ câu `unanswerable`; `alias` là các cách viết khác **có thật trong file của shop** được chấp nhận (với `list`/`table` là mảng alias theo từng phần tử).

```json
{"id": "q_001883280e83", "type": "number", "answer": 89526400, "alias": []}
```

**`calendar.csv`** — cột: `date, weekday, lunar_day, lunar_month, lunar_year, lunar_leap, holiday`. Có cột tháng nhuận → tra lịch Tết chính xác.

**`data/<business>/`** — dữ liệu thô của shop: nhiều file `.xlsx` (có thể nhiều sheet), `.csv`, `.sqlite`; kèm `README.md` mô tả **từng cột** và quy ước riêng của shop (đơn vị quy đổi, cách hiểu số liệu). `README.md` của shop là **input hợp lệ** để đọc vào agent.

### Đặc điểm dữ liệu cần biết trước khi code

- Header **không** luôn ở dòng 0 (`biz_103` dòng 2; `biz_108/111/112` dòng 3).
- Nhiều shop tách **một sheet mỗi tháng** cần union.
- `biz_123` / `dev_006` là **SQLite** (17 bảng: `don_hang`, `chi_tiet_don`, `thanh_toan`, `tra_hang`, `the_kho`, `lo_hang`, `lich_su_gia`, `don_vi_sp`, `nhan_vien`, `nha_cung_cap`, `thong_tin_thuoc`…).
- Đơn vị bán xuất hiện nhiều cấp (lốc/thùng/hộp) → cần quy đổi về **đơn vị cơ bản**.

---

## Kiến trúc giải pháp

```text
[A] Ingest ─► [B] Map schema ─► [Views canonical, đã áp rulebook + cắt tại as_of]
                                        ▲
 rulebook.md ─► [C] Knobs + RuleSpec ─────┘
 question ─► [D] time + entity ─┬─► ĐƯỜNG 1: LLM điền Spec ─► metric library ─┐
                                └─► ĐƯỜNG 2: LLM viết SQL trên views ──────────┤
                                                                            ▼
                              [G] answerability ─► [H] quyết định p̂>0.5 ─► [I] formatter
```

> **Lý do đầy đủ** cho kiến trúc này (vì sao mỗi khối tồn tại, các quyết định cốt lõi): [`Planning.md`](Planning.md).

Ba nguyên tắc cốt lõi:

1. **Luật được áp đúng một lần, ở tầng view.** Doanh thu, loại đơn huỷ/trả, cắt theo `as_of` đều nằm trong SQL view — LLM không bao giờ tự viết logic đó.
2. **LLM chỉ điền chỗ trống trong tập đóng.** Ngày tháng, tính toán, tie-break, format do code làm.
3. **Hai đường (Spec và SQL) để lấy tín hiệu đồng thuận** — đồng thuận là *feature* cho calibration, không phải quy tắc cứng.

`unanswerable` được **suy ra từ code** (thiếu capability) chứ không đoán bừa — để không mất −1.

---

## Cấu trúc code mục tiêu

Theo [`EXECUTION-PLAN.md`](EXECUTION-PLAN.md) §1 — code nằm **ngay trong `datamate/`**, không tạo `datamate/datamate/`:

```text
datamate/
├── config.py            # Config, DEFAULT_KNOBS
├── dtypes.py            # dataclass dùng chung
├── ingest/              # reader.py (csv/xlsx/sqlite), clean.py (header, số, ngày)
├── schema/              # roles.py, archetypes.py, mapper.py, canon.py, invariants.py, views.py
├── rules/               # knobs.py, rulebook_parser.py
├── timeutil/            # calendar_vi.py, resolver.py
├── text/                # normalize.py, entity_linker.py, bm25.py, numeric_filters.py
├── engine/              # registry.py, templates.py, compile.py, executor.py, sandbox.py, answer.py
├── llm/                 # client.py, fake.py, prompts.py, schemas.py
├── paths/               # path1_spec.py, path2_sql.py
├── decide/              # answerability.py, features.py, calibrate.py, decider.py, escalate.py
├── fmt/                 # formatter.py, compare.py
├── dev/                 # survey.py, evaluate.py, enumerate_match.py, tag_group.py,
│                        #   calibrate.py, repro_check.py
├── docs/                # m04.md, m05.md, m08.md (nhật ký thiết kế + kết quả đo)
├── predict.py           # orchestrator: sinh submission.jsonl
├── tests/
├── BACKLOG.md           # việc chưa xong
└── train/ public_test/  # dữ liệu
```

---

## Cài đặt

```bash
cd datamate
python3.12 -m venv .venv
source .venv/bin/activate
pip install pandas openpyxl duckdb numpy rapidfuzz scikit-learn joblib pyarrow httpx pytest
```

Biến môi trường:

```bash
export DATAMATE_LLM_BASE_URL="https://<endpoint>/v1"
export DATAMATE_LLM_API_KEY="<key>"
export DATAMATE_LLM_MODEL="Qwen3-4B-Instruct"
```

> `api_key` **không** hard-code, **không** commit. `.env` đã bị `.gitignore` loại trừ.

---

## Chạy

```bash
# 1) Khảo sát dữ liệu (bước M0 — làm trước tiên, cho ra survey/)
python dev/survey.py

# 2) Chấm một file submission trên tập train
python dev/evaluate.py --submission public_test/submission.jsonl --answers train/answers.jsonl

# 3) Sinh submission cho public test (split và đường dẫn đọc từ config.py)
python predict.py

# 4) Đo tỉ lệ khớp của phần tất định trên train (đo có kiểm soát)
python dev/enumerate_match.py --split train --scope dev     --out survey/run_dev
python dev/enumerate_match.py --split train --scope holdout --out survey/run_holdout

# 5) Hiệu chỉnh bộ quyết định (M12) từ kết quả đo
python dev/calibrate.py --run survey/run_dev

# 6) Kiểm tra tái lập (chạy 2 lần, so kết quả)
python dev/repro_check.py --split train --limit 200

# 7) Chạy test
python -m pytest tests/ -q
```

`config.py` khai báo `split` (`train` | `public_test`), `out_path` (mặc định `public_test/submission.jsonl`), `log_dir` (mặc định `public_test/logs/`) và `deadline_s` (mặc định `5,25·3600`).

`dev/evaluate.py` in ra: PA tổng, PA theo `type`, theo business, tỉ lệ coverage (không abstain) và precision.

**Lưu ý:** `dev/evaluate.py` chỉ dùng cho train (có nhãn). `public_test` **không có đáp án** — dùng nó để phát triển được, nhưng không dùng để rút luận (không rò rỉ đáp án).

---

## Trạng thái hiện tại (đo trên `train`)

| hạng mục | kết quả |
|---|---|
| Phần **tất định** khớp đáp án thật (dev, 2367 câu) | **21.9%** (core 21.9%, other 27.5%, tail 1.6%) |
| Phần tất định khớp (holdout, 633 câu) | **14.4%** |
| **PA** sau bộ quyết định (dev / holdout / toàn train) | **+0.042 / +0.016 / +0.027** (trả lời mọi câu: −0.63) |
| Rulebook train → `DEFAULT_KNOBS` | khớp 100% (không knob nào lệch) |
| Rulebook test | ra đúng 3 ngành mới (`baby`, `repair`, `phone`), không câu nào rơi |
| Answerability (M11) | bắt 14/70 câu null, chỉ 1 trả lời sai (đo trên 3000 câu train) |
| Test (`pytest tests/`) | 38 test pass |

Chi tiết: [`docs/m08.md`](docs/m08.md) (kết quả đo + nhật ký phát hiện) và
[`BACKLOG.md`](BACKLOG.md) (việc chưa xong — cổng G2 của bản kế hoạch là ≥70% core,
hiện **chưa đạt**; nguyên nhân chính là bộ lọc theo giá trị và các metric nghiệp vụ
còn thiếu).

---

## Định dạng nộp bài

File `public_test/submission.jsonl` — mỗi dòng một câu:

```json
{"id": "q_001883280e83", "type": "number", "answer": 89526400}
{"id": "q_008fdebb6ec9", "type": "list", "answer": ["Cà phê sữa", "Bạc xỉu"]}
{"id": "q_00abc", "type": "unanswerable", "reason": "shop không có cột giá vốn"}
```

Quy tắc (rulebook §9) — **sai format là sai**:

| `type` | Format | Đúng | Sai |
|---|---|---|---|
| `number` | JSON number, không đơn vị, không dấu phân cách nghìn; tiền là số nguyên VND | `4820000` | `"4,82 triệu"`, `"4.820.000"` |
| `percent` | JSON number là **số phần trăm** | `12.4` | `"12,4%"`, `0.124` |
| `date` | `"YYYY-MM-DD"`; câu hỏi theo tháng: `"YYYY-MM"` | `"2026-08-15"` | `"15/08/2026"` |
| `boolean` | `true` / `false` | `true` | `"có"`, `1` |
| `string` | tên như trong dữ liệu, **giữ đúng dấu tiếng Việt** | `"Sting dâu 330ml"` | `"Sting dầu 330ml"` |
| `list` | mảng JSON, có thứ tự | `["Cà phê sữa"]` | `"Cà phê sữa, Bạc xỉu"` |
| `table` | `{"columns": [...], "rows": [[...], ...]}`, ô số là JSON number | `{"columns": ["khach_hang"], "rows": [["Chị Lan"]]}` | ô `"3.200.000đ"` |
| `unanswerable` | `{"type": "unanswerable", "reason": "..."}` | | |

So khớp sau khi đúng format:

- **Số, phần trăm:** khớp tuyệt đối. Tiền đúng từng đồng (nửa đồng làm tròn lên); phần trăm và số trung bình khác làm tròn 2 chữ số thập phân.
- **Chuỗi:** không phân biệt hoa thường, khoảng trắng, dấu câu. Ngoài các cách viết có thật trong file của shop (hoặc mã), **dấu tiếng Việt phải đúng**.
- **Danh sách:** đúng cả tập **và thứ tự**. Tie-break khi bằng nhau: theo mã tăng dần (không có mã thì theo tên).
- **Bảng:** cột đầu là tên đối tượng, các cột sau là số đo theo đúng thứ tự câu hỏi nêu. Thứ tự dòng không ảnh hưởng kết quả.

---

## Lộ trình milestone

Chi tiết đầy đủ (từng file, từng hàm, thuật toán, tiêu chí nghiệm thu, **IN/OUT scope**) trong [`EXECUTION-PLAN.md`](EXECUTION-PLAN.md) §3 — bản **đầy đủ các step**, tới lúc nộp bài.
**Phase 1 (đang làm):** [`EXECUTION-MVP.md`](EXECUTION-MVP.md) — cùng các step, nhưng LLM gọi **API MiniMax M3.1-flash**, không deploy, không nộp bài.
Trước khi code milestone nào phải có `docs/mNN.md` (thiết kế chi tiết) — xem [`EXECUTION-PLAN.md`](EXECUTION-PLAN.md) mục 0.2.

| M | Nội dung | Nghiệm thu |
|---|---|---|
| **M0** | Khảo sát dữ liệu + bộ chấm điểm (`dev/survey.py`, `fmt/compare.py`, `dev/evaluate.py`) | evaluate với đáp án tham chiếu cho PA = 1.0, "toàn abstain" cho PA = 0.0 |
| **M1** | Ingest & làm sạch (`ingest/`) | parse `1.200.000đ` → `1200000`; header không ở dòng 0 vẫn đúng; chạy trên mọi shop không crash |
| **M2** | Time resolver + lịch âm (`timeutil/`) | test cứng với `as_of = 2026-03-04` cho mọi cụm thời gian; cửa sổ Tết khớp lịch |
| **M3** | Rulebook → Knobs + RuleSpec (`rules/`) | parse rulebook train ra đúng `DEFAULT_KNOBS`; rulebook test sinh đúng 3 ngành mới, **không câu nào rơi** |
| **M4** | Map schema, bất biến, views (`schema/`) | view áp đúng luật doanh thu/công nợ/cắt `as_of` |
| **M5** | Metric library + executor (`engine/`) | metric tính đúng trên case train đã biết |
| **M6** | Chuẩn hoá, entity linking, BM25 (`text/`) | khớp tên có dấu, entity trùng tên/số điện thoại |
| **M7** | Formatter (`fmt/formatter.py`) | ra đúng format theo từng `type` |
| **M8** | Enumerate-and-match + ngân hàng ví dụ (`dev/`) | **cổng kiểm soát: ≥ 90% câu có đáp án khớp bằng code** |
| **M9** | LLM client + đường 1 (Spec) (`llm/`, `paths/path1_spec.py`) | spec hợp lệ, chạy được trên view |
| **M10** | Đường 2 (SQL tự do) (`paths/path2_sql.py`) | SQL sinh ra chạy được, có sửa 1 lần khi lỗi |
| **M11** | Khả năng trả lời (`decide/answerability.py`) | câu thiếu capability → `unanswerable` đúng |
| **M12** | Quyết định, calibration, leo thang (`decide/`) | PA mô phỏng trên train |
| **M13** | Orchestrator + logging (`predict.py`) | `submission.jsonl` hợp lệ cho 100% id, ghi nguyên tử |
| **M14** | Ablation 4 cấu hình (chỉ đường 1 / chỉ đường 2 / cả hai / cộng leo thang) | giữ cấu hình cao nhất |
| **M15** | Mở rộng ngành mới (sửa xe, điện thoại, mẹ và bé — chỉ có ở `public_test`) | view + metric riêng, kiểm tay 10 câu/ngành |
| **M16** | Đóng gói Docker + tái lập + nộp (offline, trọng số trong image) | `submission.jsonl` 100% id, `|ΔPA| < 0.01`, đúng luật thi |

Thứ tự phụ thuộc:

```text
M0 ─► M1 ─► M2 ─┐
        M3 ─────┼─► M4 ─► M5 ─► M7 ─► M8 ──► (cổng: ≥90% câu khớp bằng code)
        M6 ─────┘                         │
                                          ▼
                        M9 ─► M10 ─► M11 ─► M12 ─► M13 ─► M14
```

> **Cổng sau M8 là điểm kiểm soát quan trọng nhất.** Nếu phần deterministic chưa tái hiện được đáp án tham chiếu của train thì việc thêm LLM chỉ che lỗi chứ không sửa lỗi.

---

## Nguyên tắc bắt buộc

Áp dụng cho mọi file do LLM implementer viết. **Nguồn chuẩn: [`EXECUTION-PLAN.md`](EXECUTION-PLAN.md) §0.4** (9 quy tắc vàng + cơ chế chống out-of-scope). Danh sách dưới là bản tóm tắt cho người đọc nhanh:

- Dùng **API LLM được cấp** (OpenAI-compatible), không tự host model. `base_url`/`api_key`/`model` đọc từ `config.py` hoặc biến môi trường — **không** hard-code, **không** commit key.
- **Không** có `if business_id == ...` hay logic theo id câu hỏi.
- Cache theo `sha256` nội dung file dữ liệu, **không** theo tên business.
- Mọi sinh LLM dùng `temperature = 0` và seed cố định.
- Mọi duyệt `dict`/`set` đưa vào quyết định phải `sorted(...)` trước.
- Mọi hàm có type hints và có test trong `tests/`.
- Giữ **dấu tiếng Việt** khi so khớp tên; bản bỏ dấu chỉ dùng để so khớp, không dùng để sinh câu trả lời.
- Artefact sinh ra (`cache/`, `reports/`, `survey/`, `runs/`, `logs/`, `submission.jsonl`) bị `.gitignore` loại trừ — không commit.

---

## Tài liệu

| Tệp | Nội dung |
|---|---|
| [`EXECUTION-PLAN.md`](EXECUTION-PLAN.md) | **NGUỒN CHUẨN cho mọi quy tắc hiện thực**: đặc tả code, IN/OUT scope từng milestone, tiêu chí nghiệm thu, quy tắc vàng, cây repo, hợp đồng `dtypes.py` |
| [`Planning.md`](Planning.md) | **Rationale**: tại sao kiến trúc này, vì sao mỗi khối tồn tại, các quyết định cốt lõi ảnh hưởng kiến trúc |
| [`EXECUTION-MVP.md`](EXECUTION-MVP.md) | **Phase 1** — cùng đầy đủ step, nhưng LLM gọi **API MiniMax**, không deploy/nộp bài |
| [`DECISIONS.md`](DECISIONS.md) | **Record**: 18 quyết định đã chốt kèm lý do và nguồn (LLM & hạ tầng, cách chấm & nộp bài, phạm vi nghiệp vụ, luật nghiệp vụ D0–D12) + phụ lục dữ kiện đã khảo sát |
| `docs/mNN.md` | Thiết kế chi tiết của từng milestone — **bắt buộc có trước khi code** (M4, M5, M8, M9, M10, M12) |
| `BACKLOG.md` | Việc phát sinh, **chưa** làm — nơi đổ mọi phát sinh thay vì vá tay trong code |
| `train/rulebook.md` | Luật nghiệp vụ bộ train (10 mục: đơn hàng, thời gian, xếp hạng, công nợ, kho, định dạng đáp án…) |
| `public_test/rulebook.md` | Luật bộ test — thêm 3 ngành mới: **Mẹ và bé**, **Sửa xe**, **Cửa hàng điện thoại** |
| `data/<business>/README.md` | Mô tả cột và quy ước riêng của từng shop (input hợp lệ cho agent) |
