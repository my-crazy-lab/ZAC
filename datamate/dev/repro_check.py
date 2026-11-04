"""Kiểm tra tái lập (reproducibility): chạy 2 lần và so kết quả.

    python dev/repro_check.py --split train --limit 200
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from predict import run  # noqa: E402


def _digest(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()[:16]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="train")
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--out-a", default="/tmp/repro_a.jsonl")
    ap.add_argument("--out-b", default="/tmp/repro_b.jsonl")
    args = ap.parse_args()

    run(args.split, args.out_a, args.limit, use_llm=False)
    run(args.split, args.out_b, args.limit, use_llm=False)

    a = [json.loads(l) for l in open(args.out_a, encoding="utf-8")]
    b = [json.loads(l) for l in open(args.out_b, encoding="utf-8")]
    same = a == b
    diff = [x["id"] for x, y in zip(a, b) if x != y]
    print(json.dumps({
        "split": args.split, "n": len(a),
        "identical": same, "digest_a": _digest(args.out_a), "digest_b": _digest(args.out_b),
        "n_diff": len(diff), "diff_sample": diff[:10],
    }, ensure_ascii=False, indent=1))
    if not same:
        sys.exit(1)


if __name__ == "__main__":
    main()
