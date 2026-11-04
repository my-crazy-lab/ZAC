#!/usr/bin/env python
"""DataMate — sinh submission cho một split (M13).

    python predict.py --split public_test --out public_test/submission.jsonl

Thứ tự xử lý mỗi câu hỏi:
1. **Đường xác định** (luật → spec → SQL) — nhanh, tái lập được.
2. Kiểm tra trả lời được (rulebook §4.10) ⇒ ``unanswerable``.
3. **Path 1** (LLM → Spec → validate → SQL) nếu có API.
4. **Path 2** (LLM → SQL → sandbox) nếu có API.
5. **Escalate / abstain** theo bộ quyết định (M12).
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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config  # noqa: E402
from decide.answerability import check as check_answerability  # noqa: E402
from decide.decider import decide  # noqa: E402
from decide.escalate import escalate  # noqa: E402
from dtypes import Answer, AnswerType, Question  # noqa: E402
from engine.answer import candidate_specs, run_specs  # noqa: E402
from ingest.reader import load_questions  # noqa: E402
from llm.client import build_client  # noqa: E402
from paths.path1_spec import run_path1  # noqa: E402
from paths.path2_sql import run_path2  # noqa: E402
from rules.rulebook_parser import parse_rulebook  # noqa: E402
from schema.views import build_context  # noqa: E402
from text.entity_linker import link_entities  # noqa: E402
from text.normalize import expand_abbrev, nd  # noqa: E402
from text.numeric_filters import extract_having  # noqa: E402
from timeutil.calendar_vi import load_calendar  # noqa: E402
from timeutil.resolver import resolve_time  # noqa: E402

log = logging.getLogger("datamate")


def _read_rules(split_dir: str) -> Any:
    path = os.path.join(split_dir, "rulebook.md")
    text = open(path, encoding="utf-8").read() if os.path.exists(path) else ""
    train_path = os.path.join(config.DATA_ROOT, "train", "rulebook.md")
    train_text = ""
    if os.path.exists(train_path):
        train_text = open(train_path, encoding="utf-8").read()
    return parse_rulebook(text, train_text, None)


def run(split: str = "public_test", out_path: str | None = None,
        limit: int | None = None, use_llm: bool = True) -> dict[str, Any]:
    root = os.path.join(config.DATA_ROOT, split)
    questions = load_questions(os.path.join(root, "questions.jsonl"))
    if limit:
        questions = questions[:limit]
    rules = _read_rules(root)
    cal = load_calendar(os.path.join(root, "calendar.csv"))
    llm = build_client() if use_llm else None

    by_biz: dict[str, list[Question]] = defaultdict(list)
    for q in questions:
        by_biz[q.business_id].append(q)

    stats: Counter[str] = Counter()
    out_path = out_path or config.out_path(split)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    log_dir = config.log_dir(split)
    os.makedirs(log_dir, exist_ok=True)
    t0 = time.time()

    with open(out_path, "w", encoding="utf-8") as out_f, \
            open(os.path.join(log_dir, "decisions.jsonl"), "w", encoding="utf-8") as log_f:
        for biz in sorted(by_biz):
            try:
                ctx = build_context(os.path.join(root, "data", biz), rules.knobs, rules, llm)
            except Exception as exc:  # noqa: BLE001
                log.warning("bỏ qua shop %s: %s", biz, exc)
                for q in by_biz[biz]:
                    out_f.write(json.dumps({"id": q.id, "type": AnswerType.ABSTAIN.value},
                                           ensure_ascii=False) + "\n")
                    stats["error_business"] += 1
                continue
            for q in sorted(by_biz[biz], key=lambda x: x.id):
                ans, info = _answer_one(q, ctx, rules, cal, llm)
                payload = {"id": q.id, **ans.to_json()}
                out_f.write(json.dumps(payload, ensure_ascii=False) + "\n")
                log_f.write(json.dumps({"id": q.id, "business": biz, "type": ans.type,
                                        **info}, ensure_ascii=False, default=str) + "\n")
                stats[ans.type] += 1

    summary = {"split": split, "n": len(questions), "by_type": dict(stats),
               "elapsed_s": round(time.time() - t0, 1), "out": out_path}
    log.info("xong: %s", summary)
    return summary


def _answer_one(q: Question, ctx: Any, rules: Any, cal: Any, llm: Any
                ) -> tuple[Answer, dict[str, Any]]:
    info: dict[str, Any] = {}
    q_nd = expand_abbrev(nd(q.text))
    windows, unresolved = resolve_time(q_nd, q.as_of, rules.knobs, cal)
    entities = link_entities(q_nd, ctx.entity_index)
    having = extract_having(q_nd)
    info["windows"] = [w.label for w in windows]
    info["entities"] = [e.canonical_name for e in entities][:3]

    # 1. đường xác định
    specs = candidate_specs(q_nd, windows, entities, having, ctx.value_dict)
    ans, spec, debug = run_specs(specs, ctx, rules.knobs, windows, q.as_of)
    info["deterministic"] = {"tried": debug.get("tried"), "spec": debug.get("spec"),
                              "errors": debug.get("errors", [])[:3]}
    if ans is not None:
        dec = decide(q.text, ctx, windows, entities, candidate=ans,
                     spec_metric=spec.metric if spec else None,
                     spec_subject=spec.subject if spec else None,
                     spec_intent=spec.intent if spec else None,
                     spec_output=spec.output if spec else None,
                     as_of=q.as_of)
        info["decision"] = {"action": dec.action, "reason": dec.reason,
                            "p_unanswerable": dec.p_unanswerable}
        if dec.action == "answer" and dec.answer is not None:
            info["path"] = "deterministic"
            return dec.answer, info
        # không chắc chắn ⇒ bỏ trống (sai = −1, bỏ = 0)
        info["path"] = "deterministic_abstain"
        return Answer(type=AnswerType.ABSTAIN.value), info

    # 2. trả lời được không?
    check = check_answerability(q.text, ctx, windows, entities, q.as_of)
    info["answerability"] = {"ok": check.answerable, "reason": check.reason,
                             "p": check.p_unanswerable}
    if not check.answerable:
        info["path"] = "unanswerable"
        return Answer(type=AnswerType.UNANSWERABLE.value, reason=check.reason), info

    # 3-4. đường LLM
    ent_names = [f"{e.kind}: {e.canonical_name}" for e in entities[:3]]
    ans, p1 = run_path1(q.text, ctx, rules.knobs, windows, ent_names, q.as_of, llm)
    info["path1"] = p1
    if ans is not None:
        info["path"] = "path1_spec"
        return ans, info
    ans, p2 = run_path2(q.text, ctx, rules.knobs, windows, q.as_of, llm)
    info["path2"] = p2
    if ans is not None:
        info["path"] = "path2_sql"
        return ans, info

    # 5. escalate / abstain
    ans, esc = escalate(q.text, ctx, llm, windows)
    info["escalate"] = esc
    dec = decide(q.text, ctx, windows, entities, candidate=ans, as_of=q.as_of)
    info["decision"] = {"action": dec.action, "reason": dec.reason,
                        "p_unanswerable": dec.p_unanswerable}
    if dec.answer is not None and dec.action in ("answer", "escalate"):
        info["path"] = "escalate"
        return dec.answer, info
    if dec.action == "unanswerable":
        info["path"] = "decide_unanswerable"
        return Answer(type=AnswerType.UNANSWERABLE.value, reason=dec.reason), info
    info["path"] = "abstain"
    return Answer(type=AnswerType.ABSTAIN.value), info


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default=config.SPLIT)
    ap.add_argument("--out", default=None)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO),
                        format="%(asctime)s %(levelname)s %(message)s")
    summary = run(args.split, args.out, args.limit, use_llm=not args.no_llm)
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
