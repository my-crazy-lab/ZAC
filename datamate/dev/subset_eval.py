"""Chấm một submission trên một tập id cố định + phân tích lỗi planner.

    python dev/subset_eval.py --submission train/submission_planner_10.jsonl \\
        --decisions train/logs/decisions_10.jsonl --ids train/planner_eval_ids_10.txt
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
from dtypes import Answer, AnswerType  # noqa: E402
from fmt.compare import is_correct  # noqa: E402
from ingest.reader import load_answers  # noqa: E402


def _answers(path: str | None = None) -> dict[str, dict[str, Any]]:
    return load_answers(path or os.path.join(config.DATA_ROOT, "train", "answers.jsonl"))


def _submission(path: str) -> dict[str, Answer]:
    out: dict[str, Answer] = {}
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            obj = json.loads(line)
            out[str(obj["id"])] = Answer.from_jsonl(obj)
    return out


def _decisions(path: str | None) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if not path or not os.path.exists(path):
        return out
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            obj = json.loads(line)
            out[str(obj.get("id"))] = obj
    return out


def _ids(path: str | None, fallback: list[str]) -> list[str]:
    if not path or not os.path.exists(path):
        return fallback
    with open(path, encoding="utf-8") as fh:
        return [line.strip() for line in fh if line.strip()]


def _reason(info: dict[str, Any] | None) -> str:
    if not info:
        return "no_decision"
    p1 = info.get("path1") or {}
    if p1.get("error"):
        return f"planner:{p1['error']}"
    if p1.get("errors"):
        return "planner_validate:" + ",".join(str(e).split(":")[0] for e in p1["errors"])
    if p1.get("verify_errors"):
        return "verify:" + ",".join(str(e).split(":")[0] for e in p1["verify_errors"])
    dec = info.get("decision") or {}
    if dec.get("reason"):
        return "decide:" + str(dec["reason"])
    return str(info.get("path") or "unknown")


def evaluate(submission_path: str, ids_path: str | None, decisions_path: str | None,
             answers_path: str | None = None) -> dict[str, Any]:
    answers = _answers(answers_path)
    sub = _submission(submission_path)
    decisions = _decisions(decisions_path)
    ids = _ids(ids_path, list(sub))
    ids = [qid for qid in ids if qid in answers]

    per_biz: dict[str, list[int]] = defaultdict(list)
    per_type: dict[str, list[int]] = defaultdict(list)
    templates: dict[str, dict[str, int]] = defaultdict(
        lambda: {"correct": 0, "wrong": 0, "abstain": 0})
    reasons: Counter[str] = Counter()
    correct = wrong = abstain = missing = 0
    prompt_chars: list[int] = []

    for qid in ids:
        ref = answers[qid]
        pred = sub.get(qid)
        info = decisions.get(qid)
        if pred is None:
            missing += 1
            pred = Answer(type=AnswerType.ABSTAIN.value)
        if pred.type == AnswerType.ABSTAIN.value:
            abstain += 1
            score = 0
        elif is_correct(pred, ref):
            correct += 1
            score = 1
        else:
            wrong += 1
            score = -1
            reasons[_reason(info)] += 1
        if pred.type == AnswerType.ABSTAIN.value:
            reasons["abstain:" + _reason(info)] += 1
        biz = str(ref.get("business_id") or "")
        per_biz[biz].append(score)
        per_type[str(ref.get("type") or "?")].append(score)
        tpl = (info or {}).get("path1", {}).get("template") if info else None
        if tpl:
            templates[str(tpl)]["correct" if score > 0 else
                                "wrong" if score < 0 else "abstain"] += 1
        pc = (info or {}).get("path1", {}).get("prompt_chars") if info else None
        if pc:
            prompt_chars.append(int(pc))

    n = len(ids)
    pa = (correct - wrong) / n if n else 0.0
    answered = correct + wrong
    out = {
        "n": n,
        "correct": correct,
        "wrong": wrong,
        "abstain": abstain,
        "missing": missing,
        "pa": round(pa, 4),
        "answered": answered,
        "coverage": round(answered / n, 4) if n else 0.0,
        "precision": round(correct / answered, 4) if answered else 0.0,
        "answered_pa": round((correct - wrong) / answered, 4) if answered else 0.0,
        "avg_prompt_chars": round(sum(prompt_chars) / len(prompt_chars), 1)
        if prompt_chars else 0,
        "failure_reasons": dict(reasons.most_common(20)),
        "templates": {k: v for k, v in sorted(templates.items(),
                                              key=lambda kv: -(kv[1]["correct"] + kv[1]["wrong"]))},
        "pa_by_type": {k: round(sum(v) / len(v), 4) for k, v in sorted(per_type.items())},
        "businesses": {k: round(sum(v) / len(v), 4) for k, v in sorted(per_biz.items())
                       if any(x != 0 for x in v)},
    }
    return out


def render(result: dict[str, Any]) -> str:
    lines = [
        f"n={result['n']} correct={result['correct']} wrong={result['wrong']} "
        f"abstain={result['abstain']} missing={result['missing']}",
        f"PA={result['pa']} coverage={result['coverage']} "
        f"precision={result['precision']} answered_PA={result['answered_pa']}",
        f"avg_prompt_chars={result['avg_prompt_chars']}",
        "failure_reasons:",
    ]
    lines += [f"  {r}: {c}" for r, c in result["failure_reasons"].items()]
    lines.append("templates (correct/wrong/abstain):")
    for tpl, stat in list(result["templates"].items())[:15]:
        lines.append(f"  {tpl}: {stat['correct']}/{stat['wrong']}/{stat['abstain']}")
    lines.append(f"pa_by_type: {result['pa_by_type']}")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--submission", required=True)
    ap.add_argument("--ids", default=None)
    ap.add_argument("--decisions", default=None)
    ap.add_argument("--answers", default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    result = evaluate(args.submission, args.ids, args.decisions, args.answers)
    text = render(result)
    print(text)
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(result, fh, ensure_ascii=False, indent=1)
        print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
