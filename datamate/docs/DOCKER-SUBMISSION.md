# Docker submission — trạng thái & checklist

## Đã xong

| Hạng mục | Trạng thái |
|---|---|
| `/code/predict.sh` không tham số | ✅ |
| Đọc `/data` (read-only), ghi `/result` | ✅ |
| `submission.jsonl` + `logs/answers.jsonl` per-question | ✅ |
| Log có `id`, `answer`, `elapsed_ms`, `thinking`, `code`, `output` | ✅ |
| Model weights trong image (Qwen3-14B Q4_K_M, 14.77B) | ✅ |
| `training_code/` + train data + `data_manifest.json` | ✅ |
| `README.md` khai báo model/revision/license/data | ✅ |
| Build `linux/amd64`, CUDA 12.8, llama.cpp offline | ✅ |
| Smoke image 10 câu | ✅ 10/10, exit 0 |
| Reproducibility 10 câu | ✅ hai lần giống hệt |
| Export `.tar.gz` + md5 | ✅ |

## Artifact trên server

```text
/home/neurosus/zac_build/zaic2026_datamate_zac.tar.gz
/home/neurosus/zac_build/zaic2026_datamate_zac.tar.gz.md5
```

- Image: `zaic2026_datamate_zac:final`
- `.tar.gz`: ~11 GB
- Uncompressed `.tar`: **13,134,734,848 bytes** (< 100 GB)
- MD5: **03213806e6c16b0bb9815cafd69d7538**
- Kiểm tra: `md5sum -c zaic2026_datamate_zac.tar.gz.md5` → OK

## Chạy kiểm tra kiểu BTC

```bash
docker run --rm --gpus '"device=0,1"' --network none --shm-size=16g \
  --entrypoint bash \
  -v /path/to/public_test:/data:ro \
  -v /path/to/output:/result \
  zaic2026_datamate_zac:final /code/predict.sh
```

Máy dev 1×RTX 3060 12GB phải hạ context:

```bash
-e LLAMA_CTX=8192 -e LLAMA_PARALLEL=1 -e DATAMATE_PARALLEL=1
```

Máy chấm 2×RTX 5090 dùng mặc định `LLAMA_CTX=32768`, `LLAMA_PARALLEL=4`,
`DATAMATE_PARALLEL=4`.

## Còn lại để nộp

1. **Chốt team name** (lowercase). Nếu không phải `zac`, retag rồi export lại:
   ```bash
   docker tag zaic2026_datamate_zac:final zaic2026_datamate_<team>:final
   set -o pipefail
   docker save zaic2026_datamate_<team>:final | pigz -p 8 > zaic2026_datamate_<team>.tar.gz
   md5sum zaic2026_datamate_<team>.tar.gz > zaic2026_datamate_<team>.tar.gz.md5
   pigz -dc zaic2026_datamate_<team>.tar.gz | wc -c
   ```
2. **Upload Google Drive** file `.tar.gz` + `.md5`, để link public.
3. **Nộp form Solution Submission** kèm:
   - link `.tar.gz`
   - nội dung `.md5`
   - uncompressed size (bytes)
4. Tải lại file từ link trên máy khác và `md5sum -c` trước khi gửi.

## Ghi chú

- Image đã đóng băng sau khi nộp; không sửa code/model/config nữa.
- Thời gian đo trên 3060: trung bình **9,75 s/câu**; private 500 câu ước ~81 phút
  + load model, dưới 6 giờ. Trên 2×5090 sẽ nhanh hơn.
- Smoke 10 câu chỉ kiểm tra chức năng; nên chạy full public_test trong image một
  lần trước khi nộp nếu còn thời gian.
