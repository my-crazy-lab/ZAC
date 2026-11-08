"""Sinh data_manifest.json cho Docker submission.

Hash toàn bộ training data + model weights trong image, kèm counts và nguồn
base model. Chạy trong Dockerfile sau khi COPY.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any


def sha256(path: str, chunk: int = 8 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def walk(root: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not os.path.isdir(root):
        return out
    for base, dirs, files in os.walk(root):
        dirs.sort()
        for name in sorted(files):
            path = os.path.join(base, name)
            if not os.path.isfile(path):
                continue
            out.append({
                "path": os.path.relpath(path, root),
                "size_bytes": os.path.getsize(path),
                "sha256": sha256(path),
            })
    return out


def count_lines(path: str) -> int:
    if not os.path.exists(path):
        return 0
    with open(path, "rb") as fh:
        return sum(1 for line in fh if line.strip())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="/code/training_code/data")
    ap.add_argument("--models", default="/code/models")
    args = ap.parse_args()

    data_files = walk(args.data)
    model_files = walk(args.models)
    train_dir = os.path.join(args.data, "train")
    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": "Zalo AI Challenge 2026 DataMate - offline inference + verification",
        "base_model": {
            "name": "Qwen/Qwen3-14B",
            "source": "https://huggingface.co/Qwen/Qwen3-14B",
            "revision": "40c069824f4251a91eefaf281ebe4c544efd3e18",
            "license": "Apache-2.0",
            "parameters": 14768307200,
            "release_date": "2025-04-29",
            "local_weights": "models/Qwen3-14B-Q4_K_M.gguf",
            "quantization": "GGUF Q4_K_M",
        },
        "training": {
            "llm_finetuning": False,
            "data_generation": False,
            "calibration": {
                "type": "logistic_regression",
                "code": "training_code/calibrate.py",
                "output": "models/calibration.json",
            },
        },
        "counts": {
            "train_questions": count_lines(os.path.join(train_dir, "questions.jsonl")),
            "train_answers": count_lines(os.path.join(train_dir, "answers.jsonl")),
            "data_files": len(data_files),
            "model_files": len(model_files),
        },
        "data_root": args.data,
        "models_root": args.models,
        "data_files": data_files,
        "model_files": model_files,
    }
    print(json.dumps(manifest, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
