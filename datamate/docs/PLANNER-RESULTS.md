# Planner + Business Context — kết quả đo

Hướng triển khai: **không để LLM viết SQL tự do**. Mỗi shop được compile thành
Business Context từ README + mapping + snapshot; LLM chỉ chọn một template
truy vấn có sẵn và điền tham số trong tập đóng; code render SQL, chạy và verify.

## 1. Thay đổi chính

- `schema/context.py`: đọc đủ 4 khối BTC cung cấp (mô tả dataset, `## File`,
  `## Cột trong ...`, `## Quy ước`) + snapshot dữ liệu thật (số dòng/đơn/sản
  phẩm/khách, khoảng ngày, trạng thái, kênh, nhóm hàng, hàng mẫu).
- `engine/catalog.py`: catalog template sinh từ `REGISTRY` × subject, lọc theo
  capability thật của shop; retrieval BM25 + miền dữ liệu + chiều phân tích;
  có template `orders.threshold`, `customers.threshold`, `.window.peak`.
- `paths/path1_spec.py`: LLM trả `template_id + params + filters + time +
  confidence + evidence`; validate chéo template/param/filter/time/metric.
- `paths/path2_sql.py`: SQL tự do **tắt mặc định** (`DATAMATE_PATH2=1` mới bật).
- `decide/verify.py`: chặn SQL lỗi, rỗng với xếp hạng, NULL ở câu số, phần trăm
  ngoài miền, sai shape.
- Sửa lỗi nền:
  - cửa sổ `cumulative` bị bỏ `start` → "từ đầu năm" thành toàn bộ dữ liệu;
  - cache canonical không phụ thuộc code → thêm fingerprint mã nguồn;
  - `c_orders` rỗng thiếu cột dẫn xuất → mọi `v_*` biến mất;
  - filter sản phẩm/khách so sánh case-sensitive;
  - metric khách đếm `customer_key` rỗng thay vì fallback tên;
  - time resolver thiếu "đầu năm", "quý" viết sai, range nhiều tháng;
  - typo phổ biến trong `abbrev_vi.json` (soos, ddown, quys, ngayf, thangs…).

## 2. Bảng kết quả

Tất cả đo trên cùng bộ id hard-set của train. `DECIDER=off` = đo riêng
planner/SQL, bỏ qua calibration cũ (calibration đang học trên pipeline cũ).

| Mốc | Run | Correct | Wrong | Abstain | PA | Precision | Ghi chú |
|---|---|---:|---:|---:|---:|---:|---|
| 10 | 10a | 0 | 10 | 0 | -1.00 | 0.00 | baseline planner + deterministic vote |
| 10 | 10b | 2 | 1 | 7 | 0.10 | 0.67 | planner-only, còn lỗi subject/filter |
| 10 | 10c | 5 | 2 | 3 | 0.30 | 0.71 | thêm template `.top`, bestseller guard |
| 10 | 10d | 8 | 0 | 2 | 0.80 | 1.00 | thêm `.top`/retrieval totals |
| 10 | 10e | 9 | 1 | 0 | 0.80 | 0.90 | DECIDER=off |
| 50 | 50a | 18 | 17 | 15 | 0.02 | 0.51 | trước khi sửa cumulative/peak |
| 50 | 50b | 24 | 25 | 1 | -0.02 | 0.49 | DECIDER=off |
| 50 | run200 | 36 | 13 | 1 | 0.46 | 0.73 | sau cumulative/typo/month-range |
| 50 | 50c | 39 | 9 | 2 | 0.60 | 0.81 | kind-guard, COALESCE, entity totals |
| 50 | **50 final** | **40** | **7** | **3** | **0.66** | **0.85** | thêm filter pay_method/category |
| 100 | run100 | 37 | 54 | 9 | -0.17 | 0.41 | trước một số fix |
| 100 | run200 | 44 | 47 | 9 | -0.03 | 0.48 | sau customers.threshold |
| 100 | **100 final** | **51** | **34** | **15** | **0.17** | **0.60** | bản cuối, DECIDER=off |
| 200 | run200 | 57 | 66 | 77 | -0.045 | 0.46 | trước 3 fix cuối |
| 200 | **200 final** | **67** | **47** | **86** | **0.10** | **0.59** | 100 id sau là abstain cũ, nhiều câu khó |

Điểm đáng chú ý: mốc 50 tăng từ PA 0.02 → 0.66 sau các lỗi hệ thống được sửa
(cumulative window, typo/range thời gian, metric khách, kind-guard, COALESCE,
entity totals, filter pay_method/category). Mốc 100 tăng từ -0.17 → +0.17.
Mốc 200 tăng từ -0.045 → +0.10; 100 id sau của tập 200 là abstain cũ nên
coverage chỉ 57% và PA bị kéo xuống.

## 3. Lỗi còn lại (từ run 200)

| Nhóm | Số câu | Nguyên nhân | Hướng sửa |
|---|---:|---|---|
| `revenue.total` sai | 17 | thiếu filter category/product; mapping shop | guard entity→filter, kiểm mapping từng shop |
| `qty.total` sai | 8 | size/unit, `is_service`, tuần lệch biên | filter size + kiểm tra cửa sổ tuần |
| `customers.threshold` | 6 | câu hỏi % thay vì đếm; lệch walk-in | thêm template share theo ngưỡng |
| `planner_retries_exhausted` | 67 abstain | không có template phù hợp / hết retry | bổ sung capability còn thiếu |
| `unresolved_time` | 9 abstain | cụm thời gian lạ/typo chưa phủ | mở rộng resolver |
| `decide:list/count_q_badpred` | 9 abstain | kiểu đáp án chưa khớp câu hỏi | bổ sung pattern "N đối tượng" |
| `price.product.total` | 1 | giá theo đơn vị (thùng vs gói) | quy đổi unit_price về đơn vị câu hỏi |
| `v_imports` rỗng | nhiều | mapper không map bảng nhập | bổ sung mapping imports |
| `.window.trend` | 2 | id LLM bịa / chuỗi nhiều kỳ | siết prompt + validate id |

## 4. public_test — chấm proxy bằng LLM judge

public_test không có file đáp án. Đã chạy 311/1.000 câu (4 shop xong:
`dev_001`, `dev_002`, `dev_004`, `dev_005`), rồi dừng để chấm bằng
`dev/judge_submission.py`: dựng lại đúng spec của đường đã chọn → SQL → kết quả,
đưa ngữ cảnh shop + SQL/kết quả cho LLM chấm correct/incorrect/uncertain.

| Chỉ số | Giá trị |
|---|---:|
| Câu đã có submission | 311 |
| Câu trả lời (graded) | 109 |
| Correct | 87 |
| Incorrect | 22 |
| PA trên câu trả lời | **0.596** |
| PA trên 311 câu (abstain = 0) | **0.209** |
| Precision proxy | **0.798** |

Theo type: number 0.61, list 0.45, string 0.71, date 0.60, percent 0.33.
Theo shop: `dev_001` 0.86, `dev_002` 0.78, `dev_004` 0.41, `dev_005` 0.17.

Đây là **proxy**, không phải điểm BTC: judge không có ground truth, chỉ kiểm tra
spec/SQL/kết quả/định dạng. Các lỗi còn lại tập trung ở shop yếu (`dev_005`),
filter nhóm hàng và quy đổi đơn vị.

## 5. Cách chạy lại

```bash
cd datamate
export DATAMATE_LLM_BASE_URL=http://192.168.1.87:5011/v1
export DATAMATE_LLM_MODEL=Qwen3-14B-Q4_K_M.gguf
export DATAMATE_PLANNER=1 DATAMATE_LLM_ONLY=1 DATAMATE_DECIDER=off

.venv/bin/python predict.py --split train \
  --ids-file train/planner_eval_ids_50.txt \
  --out train/submission_planner_50c.jsonl

.venv/bin/python dev/subset_eval.py \
  --submission train/submission_planner_50c.jsonl \
  --ids train/planner_eval_ids_50.txt \
  --decisions train/logs/decisions_planner_50c.jsonl
```

Lưu ý: `DECIDER=off` chỉ dùng để đo planner. Pipeline nộp bài phải train lại
calibration trên feature/đường đi mới trước khi bật lại.
