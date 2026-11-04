"""Chấm điểm một file submission trên tập có nhãn (M0).

    python dev/evaluate.py --submission public_test/submission.jsonl --answers train/answers.jsonl

In ra: PA tổng, PA theo type, theo business, coverage (không abstain), precision.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dtypes import Answer, AnswerType  # noqa: E402
from fmt.compare import is_correct  # noqa: E402
from ingest.reader import load_answers, load_questions  # noqa: E402


def load_submission(path: str) -> dict[str, Answer]:
    out: dict[str, Answer] = {}
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            out[str(obj["id"])] = Answer.from_jsonl(obj)
    return out


def evaluate(submission: dict[str, Answer], answers: dict[str, dict[str, Any]],
             questions: dict[str, Any] | None = None) -> dict[str, Any]:
    per_type: dict[str, list[int]] = defaultdict(list)
    per_biz: dict[str, list[int]] = defaultdict(list)
    all_scores: list[int] = []
    n_answered = 0
    n_correct = 0
    n_abstain = 0
    missing = 0
    detail_wrong: list[dict[str, Any]] = []

    for qid, ref in answers.items():
        pred = submission.get(qid)
        if pred is None:
            missing += 1
            pred = Answer(type=AnswerType.ABSTAIN.value)
        if pred.type == AnswerType.ABSTAIN.value:
            n_abstain += 1
        else:
            n_answered += 1
        correct = is_correct(pred, ref)
        score = 1 if correct else (-1 if pred.type != AnswerType.ABSTAIN.value else 0)
        if correct:
            n_correct += 1
        all_scores.append(score)
        per_type[str(ref.get("type"))].append(score)
        if questions is not None:
            q = questions.get(qid)
            if q is not None:
                per_biz[q.business_id].append(score)
        if not correct and pred.type != AnswerType.ABSTAIN.value and len(detail_wrong) < 40:
            detail_wrong.append({
                "id": qid,
                "type": ref.get("type"),
                "pred_type": pred.type,
                "pred": pred.value,
                "ref": ref.get("answer"),
                "business_id": q.business_id if questions and qid in questions else "",
                "question": questions[qid].text if questions and qid in questions else "",
            })

    n = len(answers)
    pa = (sum(all_scores) / n) if n else 0.0
    return {
        "n": n,
        "pa": round(pa, 4),
        "n_answered": n_answered,
        "n_abstain": n_abstain,
        "n_missing": missing,
        "coverage": round(n_answered / n, 4) if n else 0.0,
        "precision": round(n_correct / n_answered, 4) if n_answered else 0.0,
        "pa_by_type": {k: round(sum(v) / len(v), 4) for k, v in sorted(per_type.items())},
        "n_by_type": {k: len(v) for k, v in sorted(per_type.items())},
        "pa_by_business": {k: round(sum(v) / len(v), 4) for k, v in sorted(per_biz.items())},
        "wrong_examples": detail_wrong,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--submission", required=True)
    ap.add_argument("--answers", required=True)
    ap.add_argument("--questions", default=None)
    ap.add_argument("--json", action="store_true", help="in ra JSON")
    ap.add_argument("--show-wrong", type=int, default=0)
    args = ap.parse_args()

    answers = load_answers(args.answers)
    submission = load_submission(args.submission)
    questions = None
    qpath = args.questions
    if qpath is None:
        guess = os.path.join(os.path.dirname(args.answers), "questions.jsonl")
        qpath = guess if os.path.exists(guess) else None
    if qpath:
        questions = {q.id: q for q in load_questions(qpath)}

    res = evaluate(submission, answers, questions)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=1))
        return
    print(f"PA = {res['pa']:.4f}   (n={res['n']})")
    print(f"coverage = {res['coverage']:.4f}   precision = {res['precision']:.4f}   "
          f"abstain = {res['n_abstain']}   thiếu dòng = {res['n_missing']}")
    print("\nPA theo type:")
    for t, pa in res["pa_by_type"].items():
        print(f"  {t:<14} {pa:>8.4f}   (n={res['n_by_type'][t]})")
    if res["pa_by_business"]:
        print("\nPA theo business:")
        for b, pa in res["pa_by_business"].items():
            print(f"  {b:<12} {pa:>8.4f}")
    for w in res["wrong_examples"][: args.show_wrong]:
        print(f"\nSAI {w['id']} [{w['type']}] {w['question']}")
        print(f"   pred={w['pred']!r} ({w['pred_type']})  ref={w['ref']!r}")


if __name__ == "__main__":
    main()
