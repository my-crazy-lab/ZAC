# Submission log — DataMate

## 2026-11-09

### Trạng thái

- Chỉ nộp **JSONL** cho public test; Docker tạm hoãn, sẽ làm lại sau.
- Server mới: `100.109.54.207` (hostname `staging-master`).
  Endpoint LLM: `http://100.109.54.207:5011/v1`, model `Qwen3-14B-Q4_K_M.gguf`.
- Docker image/archive trên server đã xoá; service LLM `qwen3_14b_gguf` vẫn chạy.

### Điểm public leaderboard

| Bản nộp | Answered | Score / PA | Net |
|---|---:|---:|---:|
| Full pipeline | 234 | **-0.131** | -131 |
| safe85 (4 shop conf≥0.85) | 109 | -0.015 | -15 |
| strict (conf + template whitelist) | 52 | -0.016 | -16 |
| dev_006 only | 29 | -0.029 | -29 |
| dev_009 only | 17 | -0.003 | -3 |
| dev_001 only | 44 | **+0.007** | +7 |
| dev_001 + dev_010 | 63 | **+0.017** | +17 |

Suy ra:
- `dev_010` net = +10 (19 câu, precision ~76%).
- `dev_001` net = +7 (44 câu, precision ~58%).
- 125 câu ngoài 4 shop tốt có precision ~3.6% → gần như sai hết.
- `dev_006` sai gần như toàn bộ dù `schema_conf=0.95`.

### File giữ lại

```text
public_test/submission.jsonl            # full 1000 câu, baseline -0.131
public_test/submission_dev001_010.jsonl # best public, +0.017
```

Các bản `safe75/safe85/strict/dev_*/group_*` đã xoá; có thể tạo lại bằng
`dev/filter_submission.py` nếu cần (phải có decisions/submission tương ứng).

### Đánh giá trung thực

- Việc tăng từ -0.131 lên +0.017 **không phải** pipeline hiểu câu hỏi tốt hơn.
  Đó là **abstain nhiều hơn + chọn shop theo điểm public** (leaderboard overfit).
- Docker/private chạy pipeline đầy đủ, không dùng filter chọn shop; điểm private
  sẽ không phải +0.017.
- Không đưa business ID/leaderboard feedback vào code Docker.

### Cleanup repo

- Xoá `__pycache__`, `.pytest_cache`, `train/logs`, `public_test/logs`,
  toàn bộ `train/submission_*`, `train/benchmark_*`, và các `public_test/submission_*`
  thử nghiệm (giữ 2 file ở trên).
- Giữ nguyên `train/data`, `public_test/data`, questions/answers/rulebook/calendar,
  source, docs, tests, `models/calibration.json`.
- `.venv` giữ lại để chạy test.

### Việc tiếp theo (khi làm lại)

1. Sửa mapping `dev_006` (SQLite): 29/29 câu sai, gần như chắc chắn sai bảng/cột
   doanh thu/ngày/trạng thái. Đây là lỗi thật, không phải calibration.
2. Thêm guard tổng quát: thiếu filter category/pay_method/product/customer thì
   abstain; validate doanh thu/orders theo nghiệp vụ; top-k mapping + invariants.
3. Train lại calibration trên output planner; đánh giá trên **train holdout**,
   không dùng điểm public làm feature.
4. Chỉ mở coverage lại sau khi precision trên holdout > 50–60%.
5. Docker: làm lại theo `docs/DOCKER-SUBMISSION.md` khi cần; server mới
   `100.109.54.207`.

### Lệnh chạy lại public

```bash
cd datamate
export DATAMATE_LLM_BASE_URL=http://100.109.54.207:5011/v1
export DATAMATE_LLM_MODEL=Qwen3-14B-Q4_K_M.gguf
export DATAMATE_PLANNER=1
.venv/bin/python predict.py --split public_test \
  --out public_test/submission.jsonl --parallel 4
```
