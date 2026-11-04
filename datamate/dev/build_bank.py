"""Gộp ngân hàng ví dụ đã xác minh (M8).

    python dev/build_bank.py --runs survey/run_dev survey/run_holdout --out survey/bank.jsonl

Mỗi dòng: một câu hỏi đã **khớp đáp án thật bằng thực thi** kèm spec và cửa sổ
thời gian — dùng làm ví dụ few-shot cho Path 1 và để đo tỉ lệ khớp khi đổi mô hình.
"""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", nargs="+", default=["survey/run_dev"])
    ap.add_argument("--out", default="survey/bank.jsonl")
    args = ap.parse_args()

    seen: dict[str, dict] = {}
    for run in args.runs:
        path = os.path.join(run, "bank.jsonl")
        if not os.path.exists(path):
            print(f"bỏ qua {path} (không có)")
            continue
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                obj = json.loads(line)
                seen.setdefault(obj["id"], obj)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        for qid in sorted(seen):
            fh.write(json.dumps(seen[qid], ensure_ascii=False) + "\n")

    metrics = Counter(o.get("metric") for o in seen.values())
    intents = Counter(o.get("intent") for o in seen.values())
    print(json.dumps({"out": args.out, "n": len(seen),
                      "by_metric": dict(metrics.most_common()),
                      "by_intent": dict(intents.most_common())},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
