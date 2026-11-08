"""Hiệu chỉnh bộ quyết định (M12) từ dữ liệu thật.

Hai nguồn dữ liệu:

* ``--build`` (mặc định): chạy **đường tất định** trên câu hỏi train, ghi lại
  đáp án đầu tiên và nó **đúng hay không** ⇒ nhãn 1/0 cho logistic regression.
  Đây là tín hiệu đúng với PA (sai = −1, bỏ = 0).
* ``--from-run``: dùng kết quả ``dev/enumerate_match.py`` (bank = khớp, unmatched = không).

    python dev/calibrate.py --build --split train --scope dev
    python dev/calibrate.py --from-run --run survey/run_dev
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
from decide.calibrate import fit, save_model  # noqa: E402
from decide.features import extract_features  # noqa: E402
from dtypes import Question  # noqa: E402
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


def _load_split(split: str):
    root = os.path.join(config.DATA_ROOT, split)
    rules = parse_rulebook(open(os.path.join(root, "rulebook.md"), encoding="utf-8").read(),
                            "", None)
    cal = load_calendar(os.path.join(root, "calendar.csv"))
    questions = load_questions(os.path.join(root, "questions.jsonl"))
    answers = load_answers(os.path.join(root, "answers.jsonl"))
    return root, rules, cal, questions, answers


def _build_samples(split: str, scope: str, limit: int | None):
    root, rules, cal, questions, answers = _load_split(split)
    if scope != "all":
        splits_path = os.path.join("dev", "splits.json")
        if os.path.exists(splits_path):
            with open(splits_path, encoding="utf-8") as fh:
                sp = json.load(fh)
            keep = set(sp.get(scope, []))
            questions = [q for q in questions if q.business_id in keep]
    if limit:
        questions = questions[:limit]

    samples: list[tuple[dict[str, float], int]] = []
    ctxs: dict[str, object] = {}
    stats = defaultdict(int)
    for q in questions:
        biz = q.business_id
        if biz not in ctxs:
            ctxs[biz] = build_context(os.path.join(root, "data", biz), rules.knobs, rules, None)
        ctx = ctxs[biz]
        q_nd = expand_abbrev(nd(q.text))
        windows, _ = resolve_time(q_nd, q.as_of, rules.knobs, cal)
        entities = link_entities(q_nd, ctx.entity_index)
        having = extract_having(q_nd)
        specs = candidate_specs(q_nd, windows, entities, having, ctx.value_dict)
        ans, spec, _dbg = run_specs(specs, ctx, rules.knobs, windows, q.as_of)
        feats = extract_features(q.text, ctx, windows, entities,
                                 spec.metric if spec else None,
                                 spec.subject if spec else None,
                                 spec.intent if spec else None,
                                 spec.output if spec else None,
                                 candidate_path="deterministic",
                                 candidate_agreement=1.0,
                                 verifier_score=1.0 if ans is not None else 0.0)
        ref = answers.get(q.id)
        ok = bool(ans and ref and is_correct(ans, ref))
        samples.append((feats, 1 if ok else 0))
        stats["correct" if ok else "wrong"] += 1
    return samples, dict(stats)


def _samples_from_run(run_dir: str):
    """Dùng kết quả enumerate_match (bank = khớp)."""
    bank_path = os.path.join(run_dir, "bank.jsonl")
    unmatched_path = os.path.join(run_dir, "unmatched.jsonl")
    split = "train"
    root, rules, cal, questions, answers = _load_split(split)
    qmap: dict[str, Question] = {q.id: q for q in questions}
    ctxs: dict[str, object] = {}
    samples: list[tuple[dict[str, float], int]] = []

    def _feats(qid: str, metric=None, subject=None, intent=None, output=None):
        q: Question = qmap[qid]
        biz = q.business_id
        if biz not in ctxs:
            ctxs[biz] = build_context(os.path.join(root, "data", biz), rules.knobs, rules, None)
        ctx = ctxs[biz]
        q_nd = expand_abbrev(nd(q.text))
        windows, _ = resolve_time(q_nd, q.as_of, rules.knobs, cal)
        entities = link_entities(q_nd, ctx.entity_index)
        return extract_features(q.text, ctx, windows, entities, metric, subject, intent, output)

    if os.path.exists(bank_path):
        for line in open(bank_path, encoding="utf-8"):
            obj = json.loads(line)
            samples.append((_feats(obj["id"], obj.get("metric"), obj.get("subject"),
                                   obj.get("intent")), 1))
    if os.path.exists(unmatched_path):
        for line in open(unmatched_path, encoding="utf-8"):
            obj = json.loads(line)
            samples.append((_feats(obj["id"]), 0))
    return samples, {"n": len(samples)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true", help="chạy đường tất định để gán nhãn")
    ap.add_argument("--from-run", default=None, help="dùng kết quả enumerate_match")
    ap.add_argument("--run", default="survey/run_dev")
    ap.add_argument("--split", default="train")
    ap.add_argument("--scope", default="dev", choices=["dev", "holdout", "all"])
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    if args.from_run:
        samples, stats = _samples_from_run(args.from_run)
    else:
        samples, stats = _build_samples(args.split, args.scope, args.limit)

    if not samples:
        print("không có mẫu để huấn luyện")
        return
    model = fit(samples)
    model["threshold"] = _choose_threshold_pa(model, samples)
    save_model(model)
    print(json.dumps({"n": len(samples), "stats": stats,
                      "threshold": model["threshold"],
                      "model_path": os.path.join(config.MODELS_DIR, "calibration.json")},
                     ensure_ascii=False, indent=1))


def _choose_threshold_pa(model, samples) -> float:
    """Chọn ngưỡng **tối đa PA** (đúng +1, sai −1, bỏ 0)."""
    from decide.calibrate import predict_proba

    best_t, best_pa = 0.0, -1e9
    for i in range(0, 101):
        t = i / 100
        pa = 0.0
        for feats, label in samples:
            p = predict_proba(model, feats)
            if p >= t:
                pa += 1 if label else -1
            else:
                pa += 0
        if pa > best_pa:
            best_pa, best_t = pa, t
    return best_t


if __name__ == "__main__":
    main()
