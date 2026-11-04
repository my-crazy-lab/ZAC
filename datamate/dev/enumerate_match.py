"""Enumerate-and-match (M8): sinh spec ứng viên bằng luật → thực thi → khớp đáp án.

Mục tiêu: kiểm chứng toàn bộ phần deterministic trên đáp án thật và dựng
ngân hàng ví dụ đã xác minh bằng thực thi.

    python dev/enumerate_match.py --split train --scope dev --out survey/run_1
    python dev/enumerate_match.py --split train --scope holdout --summary-only
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from collections import Counter, defaultdict
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
from dtypes import Question  # noqa: E402
from dev.tag_group import tag_group  # noqa: E402
from engine.answer import candidate_specs, run_specs  # noqa: E402
from fmt.compare import is_correct  # noqa: E402
from ingest.reader import load_answers, load_questions  # noqa: E402
from rules.rulebook_parser import parse_rulebook  # noqa: E402
from schema.views import build_context  # noqa: E402
from text.entity_linker import link_entities  # noqa: E402
from text.normalize import expand_abbrev, nd  # noqa: E402
from text.numeric_filters import extract_having  # noqa: E402
from timeutil.calendar_vi import load_calendar  # noqa: E402
from timeutil.resolver import resolve_time  # noqa: E402

log = logging.getLogger(__name__)

MAX_SPECS = 24

def run_split(split: str, scope: str, out_dir: str, limit: int | None = None,
              summary_only: bool = False) -> dict[str, Any]:
    os.makedirs(out_dir, exist_ok=True)
    root = os.path.join(config.DATA_ROOT, split)
    questions = load_questions(os.path.join(root, "questions.jsonl"))
    answers = load_answers(os.path.join(root, "answers.jsonl")) if \
        os.path.exists(os.path.join(root, "answers.jsonl")) else {}
    cal = load_calendar(os.path.join(root, "calendar.csv"))
    rulebook_text = open(os.path.join(root, "rulebook.md"), encoding="utf-8").read()
    train_rulebook = ""
    train_path = os.path.join(config.DATA_ROOT, "train", "rulebook.md")
    if os.path.exists(train_path):
        train_rulebook = open(train_path, encoding="utf-8").read()
    rules = parse_rulebook(rulebook_text, train_rulebook, None)

    with open(os.path.join("dev", "splits.json"), encoding="utf-8") as fh:
        splits = json.load(fh)
    scope_biz = set(splits.get("dev", [])) if scope == "dev" else set(splits.get("holdout", []))

    by_biz: dict[str, list[Question]] = defaultdict(list)
    for q in questions:
        if scope_biz and q.business_id not in scope_biz:
            continue
        by_biz[q.business_id].append(q)

    bank_f = open(os.path.join(out_dir, "bank.jsonl"), "w", encoding="utf-8")
    unmatched_f = open(os.path.join(out_dir, "unmatched.jsonl"), "w", encoding="utf-8")
    stats = Counter()
    group_stats = Counter()
    group_total = Counter()
    t0 = time.time()

    for biz in sorted(by_biz):
        ctx = build_context(os.path.join(root, "data", biz), rules.knobs, rules, None)
        for q in sorted(by_biz[biz], key=lambda x: x.id):
            q_nd = expand_abbrev(nd(q.text))
            windows, unresolved = resolve_time(q_nd, q.as_of, rules.knobs, cal)
            entities = link_entities(q_nd, ctx.entity_index)
            having = extract_having(q_nd)
            specs = candidate_specs(q_nd, windows, entities, having, ctx.value_dict)
            ref = answers.get(q.id)
            is_null = bool(ref) and ref.get("answer") is None
            grp = tag_group(q_nd, is_null)
            group_total[grp] += 1
            matched = False
            reason = "no_spec"
            first_err = ""

            def _accept(ans, spec):
                if ref is None:
                    return True
                return is_correct(ans, ref)

            ans, spec, debug = run_specs(specs, ctx, rules.knobs, windows, q.as_of,
                                         accept=_accept)
            if ans is not None and spec is not None:
                bank_f.write(json.dumps({
                    "id": q.id, "business": biz, "question_nd": q_nd,
                    "spec": spec.to_dict(), "metric": spec.metric,
                    "intent": spec.intent,
                    "window_labels": [w.label for w in windows],
                }, ensure_ascii=False) + "\n")
                stats["matched"] += 1
                group_stats[grp] += 1
                matched = True
            else:
                if debug.get("errors"):
                    first_err = debug["errors"][0]
                    reason = ("exec_error" if str(first_err).startswith("exec:")
                              else "no_spec")
                else:
                    reason = "wrong_value"
            if not matched:
                unmatched_f.write(json.dumps({
                    "id": q.id, "business": biz, "question": q.text,
                    "question_nd": q_nd, "group": grp,
                    "ref_type": (ref or {}).get("type"),
                    "ref_answer": (ref or {}).get("answer"),
                    "reason": reason,
                    "first_err": first_err,
                    "n_specs": len(specs),
                }, ensure_ascii=False) + "\n")
                stats["unmatched"] += 1
                stats[f"reason_{reason}"] += 1
            if limit and stats["matched"] + stats["unmatched"] >= limit:
                break
        if limit and stats["matched"] + stats["unmatched"] >= limit:
            break

    bank_f.close()
    unmatched_f.close()
    total = stats["matched"] + stats["unmatched"]
    summary = {
        "split": split, "scope": scope, "n": total,
        "matched": stats["matched"], "unmatched": stats["unmatched"],
        "rate": round(stats["matched"] / total, 4) if total else 0.0,
        "by_group": {g: {"matched": group_stats[g], "total": group_total[g],
                         "rate": round(group_stats[g] / group_total[g], 4)
                         if group_total[g] else 0.0}
                     for g in sorted(group_total)},
        "reasons": {k: v for k, v in stats.items() if k.startswith("reason_")},
        "elapsed_s": round(time.time() - t0, 1),
    }
    with open(os.path.join(out_dir, "summary.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=1)
    return summary


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="train")
    ap.add_argument("--scope", default="dev", choices=["dev", "holdout", "all"])
    ap.add_argument("--out", default="survey/run")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--summary-only", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    summary = run_split(args.split, args.scope, args.out, args.limit, args.summary_only)
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
