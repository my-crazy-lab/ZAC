#!/usr/bin/env bash
# Entry point BTC: /code/predict.sh (không tham số)
set -euo pipefail

MODEL="${MODEL:-/code/models/Qwen3-14B-Q4_K_M.gguf}"
LLAMA_CTX="${LLAMA_CTX:-16384}"
LLAMA_PARALLEL="${LLAMA_PARALLEL:-4}"
LLAMA_THREADS="${LLAMA_THREADS:-16}"
LLAMA_NGL="${LLAMA_NGL:-999}"
DATAMATE_PARALLEL="${DATAMATE_PARALLEL:-4}"
DATAMATE_DECIDER="${DATAMATE_DECIDER:-on}"

mkdir -p /result/logs /tmp/datamate_cache

if [ ! -f "$MODEL" ]; then
    echo "missing model: $MODEL" >&2
    exit 1
fi

/app/llama-server \
    -m "$MODEL" \
    --host 127.0.0.1 --port 8080 \
    --ctx-size "$LLAMA_CTX" \
    --parallel "$LLAMA_PARALLEL" \
    --n-gpu-layers "$LLAMA_NGL" \
    --threads "$LLAMA_THREADS" \
    --cache-type-k q4_0 --cache-type-v q4_0 \
    --flash-attn auto \
    --chat-template-kwargs '{"enable_thinking":false}' \
    > /result/logs/llama-server.log 2>&1 &
LLM_PID=$!
trap 'kill "$LLM_PID" 2>/dev/null || true' EXIT

for _ in $(seq 1 180); do
    if curl -sf http://127.0.0.1:8080/health >/dev/null 2>&1; then
        break
    fi
    sleep 2
done
if ! curl -sf http://127.0.0.1:8080/health >/dev/null 2>&1; then
    echo "llama-server not ready; see /result/logs/llama-server.log" >&2
    exit 1
fi

export DATAMATE_LLM_BASE_URL="http://127.0.0.1:8080/v1"
export DATAMATE_LLM_MODEL="Qwen3-14B-Q4_K_M.gguf"
export DATAMATE_LLM_API_KEY=""
export DATAMATE_DATA_ROOT="/data"
export DATAMATE_LOG_DIR="/result/logs"
export DATAMATE_CACHE_DIR="/tmp/datamate_cache"
export DATAMATE_PLANNER=1
export DATAMATE_DECIDER="$DATAMATE_DECIDER"

LIMIT_ARGS=()
if [ -n "${DATAMATE_LIMIT:-}" ]; then
    LIMIT_ARGS=(--limit "$DATAMATE_LIMIT")
fi

python3 /code/src/predict.py \
    --split "" \
    --out /result/submission.jsonl \
    --parallel "$DATAMATE_PARALLEL" \
    "${LIMIT_ARGS[@]}"
