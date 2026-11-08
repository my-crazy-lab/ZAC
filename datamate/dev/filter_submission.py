"""Tạo submission lọc theo độ tin cậy để test public leaderboard.

Modes:
- det: chỉ giữ câu do đường deterministic trả lời.
- conf: chỉ giữ câu trả lời ở shop có schema_conf >= --min-conf và không
  phải đường escalate; unanswerable đổi thành abstain.

Mọi câu bị loại ghi abstain để đủ id.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
from ingest.reader import load_questions  # noqa: E402
from rules.rulebook_parser import parse_rulebook  # noqa: E402
from schema.views import build_context  # noqa: E402


def load_latest(path: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if not os.path.exists(path):
        return out
    for line in open(path, encoding="utf-8"):
        if not line.strip():
            continue
        try:
            o = json.loads(line)
        except ValueError:
            continue
        out[str(o.get("id"))] = o
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="public_test")
    ap.add_argument("--submission", default="public_test/submission.jsonl")
    ap.add_argument("--decisions", default="public_test/logs/decisions.jsonl")
    ap.add_argument("--out", required=True)
    ap.add_argument("--mode", choices=["det", "conf"], default="conf")
    ap.add_argument("--min-conf", type=float, default=0.75)
    ap.add_argument("--allow-templates", default="",
                    help="danh sách template_id cách nhau dấu phẩy; rỗng = cho tất cả")
    args = ap.parse_args()

    split_dir = os.path.join(config.DATA_ROOT, args.split)
    questions = load_questions(os.path.join(split_dir, "questions.jsonl"))
    sub = {}
    for line in open(args.submission, encoding="utf-8"):
        if line.strip():
            o = json.loads(line)
            sub[str(o["id"])] = o
    dec = load_latest(args.decisions)
    rules = parse_rulebook(
        open(os.path.join(split_dir, "rulebook.md"), encoding="utf-8").read(),
        open(os.path.join(config.DATA_ROOT, "train", "rulebook.md"), encoding="utf-8").read(),
        None,
    )

    conf: dict[str, float] = {}
    if args.mode == "conf":
        for biz in sorted({q.business_id for q in questions}):
            try:
                ctx = build_context(os.path.join(split_dir, "data", biz), rules.knobs, rules, None)
                conf[biz] = float(ctx.schema_conf)
            except Exception:  # noqa: BLE001
                conf[biz] = 0.0

    allow = {x.strip() for x in args.allow_templates.split(",") if x.strip()}
    kept = 0
    types: Counter[str] = Counter()
    by_biz: Counter[str] = Counter()
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        for q in questions:
            row = sub.get(q.id) or {"id": q.id, "type": "abstain"}
            typ = str(row.get("type", "abstain"))
            info = dec.get(q.id) or {}
            path = str(info.get("path") or "")
            ok = typ not in ("abstain", "unanswerable")
            if args.mode == "det":
                ok = ok and "deterministic" in path
            else:
                ok = ok and conf.get(q.business_id, 0.0) >= args.min_conf
                ok = ok and path != "escalate"
                tpl = str((info.get("path1") or {}).get("template") or "")
                if allow and tpl not in allow:
                    ok = False
            if ok:
                out = row
                kept += 1
                types[typ] += 1
                by_biz[q.business_id] += 1
            else:
                out = {"id": q.id, "type": "abstain"}
            fh.write(json.dumps(out, ensure_ascii=False) + "\n")
    print(json.dumps({"out": args.out, "kept": kept, "types": dict(types),
                      "by_business": dict(sorted(by_biz.items()))},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
