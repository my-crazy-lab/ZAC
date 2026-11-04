# M<n> — <tên milestone>

> Detail sheet bắt buộc trước khi code milestone n (xem `EXECUTION-PLAN.md` mục 0.2).
> Thứ tự ưu tiên khi mâu thuẫn: `docs/mNN.md` (chi tiết hành vi) → `EXECUTION-PLAN.md` (nguồn chuẩn) → `Planning.md` (rationale) → `DECISIONS.md` (record).
> Copy file này thành `docs/mNN.md`, điền đủ 7 mục dưới. **Milestone chưa có file này thì không được code.**
> Trạng thái: ☐ đang viết · ☐ chờ review · ☐ đã duyệt · ☐ đã code xong

**Phụ thuộc:** (cổng đã qua) …
**Người viết:** … · **Người review:** … · **Ngày:** …

---

## 1. Vào / Ra

**Input:**
- (file, hàm, kiểu dữ liệu)

**Output:**
- (file, hàm, kiểu dữ liệu)

**KHÔNG làm (nhắc lại OUT scope):**
- …

---

## 2. Dữ liệu thật liên quan

| Business / file | Cột / dòng dùng làm mẫu | Trích dẫn |
|---|---|---|
| biz_xxx | `Tên cột` | `survey/columns.csv` dòng … |

> Phần này là lý do detail sheet viết **sau** milestone trước: có `survey/` rồi mới chốt được heuristic trên dữ liệu thật.

---

## 3. Thuật toán

*(pseudocode hoặc mô tả từng bước — đủ để viết code mà không phải tự quyết)*

```
1. …
2. …
```

---

## 4. SQL / Prompt đầy đủ

*(nếu milestone có SQL hoặc prompt: ghi **nguyên văn**, không mô tả bằng lời)*

```sql
-- metric: revenue
…
```

```text
-- prompt đường 1
…
```

---

## 5. Test

| # | Input | Output mong đợi | Ghi chú |
|---|---|---|---|
| 1 | | | |

Lệnh chạy: `…`

---

## 6. Rủi ro & cách xử lý

| Rủi ro | Dấu hiệu | Xử lý |
|---|---|---|
| | | |

---

## 7. Lệch so với EXECUTION-PLAN.md / Planning.md

*(nếu không có gì thì ghi "không". nếu có → nêu rõ và cập nhật cả 2 file trong cùng commit)*

| Nội dung | EXECUTION-PLAN.md | Planning.md | Sửa ở commit nào |
|---|---|---|---|
| | | | |
