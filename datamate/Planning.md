# Planning.md — Kiến trúc & lý do

> **Vai trò của file này:** giải thích **tại sao** hệ thống được thiết kế như hiện tại. **Không phải đặc tả để code** — và **không phải nguồn chuẩn**: khi có xung đột về quy tắc hiện thực, `EXECUTION-MVP.md` (phase 1) hoặc `EXECUTION-PLAN.md` (bản cuối) thắng.
>
> | File | Vai trò | Khi nào đọc |
> |---|---|---|
> | [`EXECUTION-MVP.md`](EXECUTION-MVP.md) | **nguồn chuẩn phase 1** — đầy đủ step, LLM gọi API, không deploy/nộp bài | đang code |
> | [`EXECUTION-PLAN.md`](EXECUTION-PLAN.md) | **bản cuối** — thêm M16 (Docker, model local offline, luật thi) | khi chuẩn bị nộp bài |
> | [`DECISIONS.md`](DECISIONS.md) | **record** — 25 quyết định đã chốt kèm lý do | khi cần biết "vì sao chọn thế này" |
> | [`README.md`](README.md) | **điểm vào** — bài toán, dữ liệu, cách chạy, định dạng nộp | lần đầu tiên |
> | [`BACKLOG.md`](BACKLOG.md) | việc phát sinh, **chưa** làm | khi phát hiện thiếu sót |

---

## 1. Kiến trúc

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

PA là **+1 đúng, 0 abstain, −1 sai**, nên mỗi quyết định thiết kế phục vụ các nguyên tắc sau:

1. **Nghiệp vụ nằm ở code, không ở LLM.** Rulebook (doanh thu, loại đơn huỷ/trả, đơn vị cơ bản, công nợ…) được áp **một lần** trong view và registry. Vì vậy phải xong M1→M5 trước khi nối LLM.
2. **Hai lớp dữ liệu.** `c_*` (canonical) hấp thụ mọi khác biệt giữa các archetype; `v_*` (view) áp rulebook và **giống nhau cho mọi business**. Metric/Spec chỉ biết `v_*`.
3. **LLM chỉ chọn trong tập đóng.** Ngày → nhãn do `resolve_time` cấp; thực thể → mã từ danh sách ứng viên; metric/intent/subject → enum. Đường 1 = *điền chỗ trống* vào khung SQL.
4. **Hai đường độc lập một phần.** Đường 2 (SQL tự do) dùng biểu diễn khác nên bắt lỗi tầng câu hỏi; **không** bắt được lỗi tầng dữ liệu/rulebook dùng chung (việc của bất biến M4).
5. **Unanswerable suy ra bằng code** từ capability **dữ liệu**; không chắc thì abstain (đoán sai −1).
6. **Calibration quyết định trả lời.** Chỉ trả khi `p̂ − margin > 0.5`.
7. **Tổng quát hoá sang business/loại hình lạ** là mục tiêu chính của test private. Vì vậy: archetype `UNKNOWN` có đường đi riêng, holdout tách riêng, ngành mới (M15) xếp sau lõi.
8. **Tái lập:** greedy, seed cố định, sort mọi thứ, đo ΔPA giữa hai lần chạy.

---

## 2. Vì sao mỗi khối tồn tại

| Khối | Trách nhiệm | Vì sao tách riêng |
|---|---|---|
| **ingest/** | CSV/XLSX/SQLite → bảng DuckDB sạch `t_*` | Dữ liệu thô có ~10 kiểu bố cục. Nếu để lẫn với mô hình nghiệp vụ thì mọi tầng sau phải đối mặt với bẩn. |
| **schema/** | map cột → role, **canonicalize** ra `c_*`, bất biến, dựng view `v_*` | **Chốt chặn lỗi tương quan theo business** — nguồn mất điểm lớn nhất. Tách `canon.py` khỏi `views.py` vì: `canon` hấp thụ *khác biệt kiểu dữ liệu*, `views` áp *luật nghiệp vụ*. Trộn hai tầng thì đổi luật là phải sửa lại adapter của từng shop. |
| **rules/** | `rulebook.md` → `Knobs` + `RuleSpec` | Rulebook **đổi theo split** (public_test thêm 3 ngành mới, sửa/bớt luật). Biến nó thành tham số có kiểu thay vì hard-code. `RuleSpec.features` (luật có nhắc) tách khỏi capability dữ liệu: luật thiếu ⇒ hạ độ tin cậy, **không** đoán unanswerable. |
| **timeutil/** | câu hỏi → `TimeWindow` | LLM không được tự tính ngày — "tháng này so với tháng trước lấy cùng số ngày" là loại luật dễ sai nhất. |
| **text/** | bỏ dấu, viết tắt, khớp tên, rút điều kiện số | Câu hỏi thiếu dấu, viết tắt, sai chính tả; tên hàng trong dữ liệu có dấu. Tách riêng để **đo được độc lập** thay vì trộn vào prompt LLM. |
| **engine/** | registry metric + templates SQL + compile + executor + sandbox | Nghiệp vụ nằm ở code → đường 1 không có lỗi nghiệp vụ ngẫu nhiên. Sandbox chặn SQL ghi/xoá vì đường 2 để LLM tự viết SQL. Registry tách khỏi templates để thêm metric của ngành mới (M15) không đụng phần lõi. |
| **llm/** | client API + schema JSON + prompt + `fake.py` | Tách client khỏi prompt để đổi backend (API ↔ model local) không đụng logic. `fake.py` để test M3/M4/M9 không cần mạng. |
| **paths/** | đường 1 (điền Spec) + đường 2 (SQL tự do) | Hai **biểu diễn khác nhau** của cùng một câu để lấy tín hiệu đồng thuận; đường 2 còn phủ câu ngoài taxonomy và business loại hình lạ (`raw_mode`). |
| **decide/** | answerability, feature, calibration, leo thang | Vì −1 cho câu sai: phải **cân đoán có trả hay không**, và phải đo được mức tin cậy thay vì chỉ so khớp đáp án. |
| **fmt/** | compare (chấm điểm) + formatter (ghi) | Chấm và ghi là hai chiều khác nhau: so khớp thì bỏ khoảng trắng/hoa thường nhưng **giữ dấu** (rulebook §9), còn ghi ra thì phải đúng định dạng submission từng type. |
| **domains/** | sửa xe, điện thoại, mẹ và bé | Ba ngành **chỉ có ở public_test** (không có đáp án để kiểm) và mô hình dữ liệu khác hẳn bán hàng. Xếp sau lõi (M15) để không hy sinh tính tổng quát của phần chung. |
| **dev/** | survey, evaluate, enumerate-match, calibration, ablation, splits | Mọi thứ phải **đo trên train**; phần deterministic phải tái hiện được đáp án tham chiếu trước khi nối LLM — nếu không, LLM chỉ che lỗi chứ không sửa lỗi. `splits.json` tách dev/holdout để đo khả năng tổng quát hoá. |

---

## 3. Thứ tự làm và phụ thuộc

```
M0 ─► M1 ─► M6 ─┐
        M2 ─────┼─► M4 ─► M5 ─► M7 ─► M8 ──► (cổng G2) ─► M9 ─► M10 ─► M11 ─► M12 ─► M13 ─► {M14, M15}
        M3 ─────┘
```

Ba cổng chặn:

- **G1 (design)** — M4, M5, M8, M9, M12 chưa có `docs/mNN.md` (nhật ký phát hiện từ dữ liệu thật) thì **không code**.
- **G2 (nghiệm thu M8)** — không sang M9 nếu phần deterministic chưa khớp ≥95% câu lõi / ≥80% câu đuôi / ≥90% tổng trên dev, **và** holdout không lệch dev quá 8 điểm.
- **G3 (end-to-end)** — M14/M15 chỉ bắt đầu khi `submission.jsonl` hợp lệ cho 100% id.

**Cổng G2 là điểm kiểm soát quan trọng nhất.** Nếu phần deterministic chưa tái hiện được đáp án tham chiếu của train thì việc thêm LLM chỉ che lỗi chứ không sửa lỗi.

---

## 4. Các quyết định cốt lõi ảnh hưởng kiến trúc

(Đầy đủ 25 quyết định + lý do + nguồn ở [`DECISIONS.md`](DECISIONS.md). Ở đây chỉ những cái **định hình kiến trúc**.)

| # | Quyết định | Ảnh hưởng kiến trúc |
|---|---|---|
| 1 | **Rulebook áp ở tầng view, không phải ở prompt** | sinh ra `schema/views.py`; LLM không bao giờ thấy luật nghiệp vụ dạng văn bản |
| 2 | **Hai đường LLM (Spec + SQL)** | sinh ra `paths/` gồm 2 module; đồng thuận là *feature* cho calibrator, không phải luật cứng |
| 3 | **Answerability suy từ capability *dữ liệu*** | `ctx.data_caps` (từ `c_*`) tách khỏi `RuleSpec.features` (từ rulebook); thiếu cap ⇒ unanswerable, thiếu luật ⇒ chỉ hạ `p` |
| 4 | **`as_of` là thuộc tính câu hỏi, không phải của view** | mọi cắt theo `as_of` do `compile_spec` chèn vào SQL ⇒ một bộ view dùng cho mọi câu, không dựng lại view 1000 lần |
| 5 | **Hai lớp dữ liệu `c_*` / `v_*`** | `canon.py` hấp thụ khác biệt archetype; `views.py` áp rulebook; metric/Spec chỉ biết `v_*` |
| 6 | **Cổng G2 (khớp ≥90% bằng code)** | quyết định thứ tự milestone: phần deterministic **trước**, LLM **sau** |
| 7 | **Abstain có giá trị (0 điểm) nên phải cân đoán** | sinh ra `decide/calibrate.py` + `decide/escalate.py` |
| 8 | **Dev/holdout tách, sửa lỗi chỉ trên dev** | sinh ra `dev/splits.json` + quy tắc "holdout chỉ xem số liệu tổng hợp" |
| 9 | **Không hardcode theo business** | mọi khác biệt phải đến từ cấu trúc / tên cột / README / rulebook → sinh ra catalog archetype + đường đi riêng cho `UNKNOWN` |
| 10 | **3 ngành mới ở M15, sau lõi** | vì chỉ có ở `public_test` (không có đáp án để kiểm) và test private còn có loại hình khác |
| 11 | **LLM qua API ở phase 1; model local khi nộp** | `llm/client.py` là HTTP client async 16 luồng, không đổi logic khi đổi backend |

---

## 5. Điều chưa biết

Các điểm chưa chắc đã được chuyển thành **bước khảo sát có đầu ra rõ ràng** (M0/M8/M15) hoặc **quyết định đã chốt** (`DECISIONS.md`) — không còn điểm nào phải đoán trong code. Danh sách đầy đủ và mặc định tạm ở mục 8 của `EXECUTION-PLAN.md`.

---

## 6. Liên kết

| File | Vai trò | Khi nào đọc |
|---|---|---|
| `README.md` | **điểm vào**: bài toán, dữ liệu, cách cài/chạy, định dạng nộp bài | lần đầu tiên |
| `EXECUTION-MVP.md` | **nguồn chuẩn phase 1**: đặc tả code, rào phạm vi, tiêu chí nghiệm thu, quy tắc vàng | đang code |
| `EXECUTION-PLAN.md` | **bản cuối**: như trên + M16 (Docker, model local offline, luật thi BTC) | khi chuẩn bị nộp bài |
| `docs/mNN.md` | nhật ký phát hiện dữ liệu thật của milestone (M4, M5, M8, M9, M12) | ngay trước milestone đó |
| `DECISIONS.md` | biên bản 25 quyết định đã chốt (record, không phải spec) | khi cần biết "vì sao lại chọn thế này" |
| `BACKLOG.md` | việc phát sinh, **chưa** làm — nơi đổ mọi phát sinh thay vì vá tay | khi phát hiện thiếu sót |
| `docs/detail-template.md` | template để copy khi tạo `docs/mNN.md` | khi bắt đầu milestone mới |
