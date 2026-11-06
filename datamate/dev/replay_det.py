"""Chạy lại **đường xác định** trên một split có nhãn và chấm PA (không LLM).

Mục đích: sau khi sửa luật (schema linking, metric, cửa quyết định), đo ngay
tác động lên PA mà không phải chạy cả pipeline 2–3 giờ. Đường đi giống
``predict._answer_one`` phần xác định: spec ứng viên → thực thi → ``decide``.

    python dev/replay_det.py --split train --out runs/replay_det.jsonl
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
from decide.answerability import check as check_answerability  # noqa: E402
from decide.decider import decide  # noqa: E402
from dtypes import Answer, AnswerType, Question  # noqa: E402
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

log = logging.getLogger("replay_det")


def run(split: str, out_path: str, limit: int | None = None) -> dict[str, Any]:
    root = os.path.join(config.DATA_ROOT, split)
    questions = load_questions(os.path.join(root, "questions.jsonl"))
    answers = load_answers(os.path.join(root, "answers.jsonl"))
    if limit:
        questions = questions[:limit]
    rulebook = open(os.path.join(root, "rulebook.md"), encoding="utf-8").read()
    rules = parse_rulebook(rulebook, "", None)
    cal = load_calendar(os.path.join(root, "calendar.csv"))

    by_biz: dict[str, list[Question]] = defaultdict(list)
    for q in questions:
        by_biz[q.business_id].append(q)

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    stats: Counter[str] = Counter()
    per_type: dict[str, list[int]] = defaultdict(list)
    t0 = time.time()

    with open(out_path, "w", encoding="utf-8") as out_f, \
            open(out_path + ".decisions", "w", encoding="utf-8") as log_f:
        for biz in sorted(by_biz):
            try:
                ctx = build_context(os.path.join(root, "data", biz), rules.knobs, rules, None)
            except Exception as exc:  # noqa: BLE001
                log.warning("bỏ qua shop %s: %s", biz, exc)
                for q in by_biz[biz]:
                    out_f.write(json.dumps({"id": q.id, "type": "abstain"}) + "\n")
                    stats["error_business"] += 1
                continue
            for q in sorted(by_biz[biz], key=lambda x: x.id):
                ans, info = _answer_one(q, ctx, rules, cal)
                out_f.write(json.dumps({"id": q.id, **ans.to_json()},
                                       ensure_ascii=False) + "\n")
                log_f.write(json.dumps({"id": q.id, "business": biz,
                                        **info}, ensure_ascii=False, default=str) + "\n")
                stats[info.get("path", "?")] += 1

    n_correct = n_wrong = n_abstain = 0
    for q in questions:
        ref = answers.get(q.id)
        if ref is None:
            continue
        pred = Answer(type=AnswerType.ABSTAIN.value)
        with open(out_path, encoding="utf-8") as fh:
            for line in fh:
                obj = json.loads(line)
                if obj["id"] == q.id:
                    pred = Answer.from_jsonl(obj)
                    break
        if pred.type == AnswerType.ABSTAIN.value:
            n_abstain += 1
            score = 0
        elif is_correct(pred, ref):
            n_correct += 1
            score = 1
        else:
            n_wrong += 1
            score = -1
        per_type[str(ref.get("type"))].append(score)

    n = len(questions)
    summary = {
        "split": split, "n": n,
        "pa": round((n_correct - n_wrong) / n, 4) if n else 0.0,
        "coverage": round((n_correct + n_wrong) / n, 4) if n else 0.0,
        "precision": round(n_correct / (n_correct + n_wrong), 4)
        if (n_correct + n_wrong) else 0.0,
        "correct": n_correct, "wrong": n_wrong, "abstain": n_abstain,
        "pa_by_type": {k: round(sum(v) / len(v), 4) for k, v in sorted(per_type.items())},
        "paths": dict(stats),
        "elapsed_s": round(time.time() - t0, 1),
    }
    return summary


def _answer_one(q: Question, ctx: Any, rules: Any, cal: Any) -> tuple[Answer, dict[str, Any]]:
    info: dict[str, Any] = {"path": "abstain"}
    q_nd = expand_abbrev(nd(q.text))
    windows, _ = resolve_time(q_nd, q.as_of, rules.knobs, cal)
    entities = link_entities(q_nd, ctx.entity_index)
    having = extract_having(q_nd)
    specs = candidate_specs(q_nd, windows, entities, having, ctx.value_dict)
    ans, spec, debug = run_specs(specs, ctx, rules.knobs, windows, q.as_of)
    info["n_specs"] = len(specs)
    if ans is not None:
        dec = decide(q.text, ctx, windows, entities, candidate=ans,
                     spec_metric=spec.metric if spec else None,
                     spec_subject=spec.subject if spec else None,
                     spec_intent=spec.intent if spec else None,
                     spec_output=spec.output if spec else None,
                     as_of=q.as_of)
        info["metric"] = spec.metric if spec else None
        info["reason"] = dec.reason
        if dec.action == "answer" and dec.answer is not None:
            info["path"] = "deterministic"
            return dec.answer, info
        info["path"] = "deterministic_abstain"
        return Answer(type=AnswerType.ABSTAIN.value), info

    check = check_answerability(q.text, ctx, windows, entities, q.as_of)
    info["reason"] = check.reason
    if not check.answerable:
        info["path"] = "unanswerable"
        return Answer(type=AnswerType.UNANSWERABLE.value, reason=check.reason), info
    return Answer(type=AnswerType.ABSTAIN.value), info


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="train")
    ap.add_argument("--out", default="runs/replay_det.jsonl")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    print(json.dumps(run(args.split, args.out, args.limit), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
