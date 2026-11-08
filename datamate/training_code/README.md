# Training code / verification

## Không fine-tune LLM

Solution **không train hay fine-tune** Qwen3-14B, không sinh dữ liệu huấn luyện.
Model dùng nguyên bản (quantize Q4_K_M để chạy offline).

Base model:
- `Qwen/Qwen3-14B`
- revision `40c069824f4251a91eefaf281ebe4c544efd3e18`
- Apache-2.0
- 14,768,307,200 parameters
- https://huggingface.co/Qwen/Qwen3-14B

## Calibration

Bộ quyết định `answer/abstain` dùng logistic regression nhỏ, train từ train set
của BTC. Code:

- `training_code/calibrate.py` (bản sao `dev/calibrate.py`)
- `training_code/splits.json`
- `training_code/data/train/` (questions, answers, rulebook, dữ liệu shop)

Lệnh tái lập (chạy trong image, sau khi có model):

```bash
export DATAMATE_DATA_ROOT=/code/training_code/data
export DATAMATE_MODELS_DIR=/code/models
PYTHONPATH=/code/src python3 /code/training_code/calibrate.py \
  --build --split train --scope dev
```

Kết quả ghi vào `/code/models/calibration.json`. File này đã có sẵn trong image
và được dùng trực tiếp khi inference.

## Data manifest

`training_code/data_manifest.json` được sinh trong lúc build bởi
`training_code/make_manifest.py`: path, size, SHA-256, số câu hỏi/đáp án,
nguồn và revision model.

## Hardware / runtime

- Build/test trên server dev (1×RTX 3060 12GB) cho kiểm tra chức năng.
- Máy chấm: 2×RTX 5090 32GB, CUDA ≥12.8; image dùng llama.cpp CUDA 12.8.
- Model load + inference nằm trong giới hạn 6 giờ của BTC.
