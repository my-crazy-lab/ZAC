"""Đường cong PA theo ngưỡng quyết định (dev/holdout) — dùng khi hiệu chỉnh.

    python dev/pa_curve.py --split train --scope dev
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
from decide.calibrate import load_model, predict_proba  # noqa: E402
from decide.features import extract_features  # noqa: E402
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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="train")
    ap.add_argument("--scope", default="dev", choices=["dev", "holdout", "all"])
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    root = os.path.join(config.DATA_ROOT, args.split)
    rules = parse_rulebook(open(os.path.join(root, "rulebook.md"), encoding="utf-8").read(),
                            "", None)
    cal = load_calendar(os.path.join(root, "calendar.csv"))
    questions = load_questions(os.path.join(root, "questions.jsonl"))
    answers = load_answers(os.path.join(root, "answers.jsonl"))
    with open(os.path.join("dev", "splits.json"), encoding="utf-8") as fh:
        sp = json.load(fh)
    if args.scope != "all":
        keep = set(sp.get(args.scope, []))
        questions = [q for q in questions if q.business_id in keep]
    if args.limit:
        questions = questions[:args.limit]

    model = load_model()
    ctxs: dict[str, object] = {}
    rows: list[tuple[float, bool]] = []
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
        ans, spec, _ = run_specs(specs, ctx, rules.knobs, windows, q.as_of)
        if ans is None:
            continue
        feats = extract_features(q.text, ctx, windows, entities,
                                 spec.metric if spec else None,
                                 spec.subject if spec else None,
                                 spec.intent if spec else None,
                                 spec.output if spec else None)
        p = predict_proba(model, feats)
        ref = answers.get(q.id)
        ok = bool(ref and is_correct(ans, ref))
        rows.append((p, ok))

    out = []
    for i in range(0, 101):
        t = i / 100
        pa = sum(1 if ok else -1 for p, ok in rows if p >= t)
        cov = sum(1 for p, _ in rows if p >= t)
        out.append({"threshold": t, "pa": round(pa / max(1, len(rows)), 4),
                    "coverage": round(cov / max(1, len(rows)), 4)})
    best = max(out, key=lambda r: r["pa"])
    print(json.dumps({"scope": args.scope, "n_answered": len(rows),
                      "best": best,
                      "curve": [r for r in out if r["threshold"] in
                                (0.0, 0.1, 0.2, 0.3, 0.4, 0.47, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)]},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
