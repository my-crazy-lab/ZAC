FROM ghcr.io/ggml-org/llama.cpp:server-cuda

# Không dùng entrypoint mặc định của llama.cpp; BTC chạy /code/predict.sh.
ENTRYPOINT []

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    NCCL_P2P_DISABLE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-pip curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /code

COPY requirements.txt /code/requirements.txt
RUN python3 -m pip install --no-cache-dir --break-system-packages \
        -r /code/requirements.txt

# Inference code
COPY predict.py config.py dtypes.py /code/src/
COPY decide/ /code/src/decide/
COPY engine/ /code/src/engine/
COPY fmt/ /code/src/fmt/
COPY ingest/ /code/src/ingest/
COPY llm/ /code/src/llm/
COPY paths/ /code/src/paths/
COPY rules/ /code/src/rules/
COPY schema/ /code/src/schema/
COPY text/ /code/src/text/
COPY timeutil/ /code/src/timeutil/

# Fallback rulebook train (dùng khi /data chỉ có rulebook của split)
COPY train/rulebook.md /code/src/train/rulebook.md

# Model weights + calibration (bắt buộc nằm trong image)
COPY models/ /code/models/

# Training code + train/validation data + verification
COPY train/ /code/training_code/data/train/
COPY dev/calibrate.py /code/training_code/calibrate.py
COPY dev/evaluate.py /code/training_code/evaluate.py
COPY dev/splits.json /code/training_code/splits.json
COPY training_code/ /code/training_code/

COPY docker/predict.sh /code/predict.sh
COPY docker/README_solution.md /code/README.md
RUN chmod +x /code/predict.sh

# Manifest bắt buộc của BTC: path, size, SHA-256, counts, nguồn model.
RUN python3 /code/training_code/make_manifest.py \
        --data /code/training_code/data \
        --models /code/models \
        > /code/training_code/data_manifest.json

CMD ["bash", "/code/predict.sh"]
