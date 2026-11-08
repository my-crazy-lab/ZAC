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
from concurrent.futures import ThreadPoolExecutor, as_completed
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
from ingest.reader import load_answers  # noqa: E402
from fmt.compare import is_correct  # noqa: E402
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
        limit: int | None = None, use_llm: bool = True,
        resume: bool = False, parallel: int = 1,
        ids: set[str] | None = None) -> dict[str, Any]:
    root = os.path.join(config.DATA_ROOT, split)
    questions = load_questions(os.path.join(root, "questions.jsonl"))
    if ids is not None:
        questions = [q for q in questions if q.id in ids]
    if limit:
        questions = questions[:limit]
    rules = _read_rules(root)
    cal = load_calendar(os.path.join(root, "calendar.csv"))
    llm = build_client() if use_llm and parallel <= 1 else None

    by_biz: dict[str, list[Question]] = defaultdict(list)
    for q in questions:
        by_biz[q.business_id].append(q)

    stats: Counter[str] = Counter()
    out_path = out_path or config.out_path(split)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    log_dir = config.log_dir(split)
    os.makedirs(log_dir, exist_ok=True)
    t0 = time.time()

    done: set[str] = set()
    if resume and os.path.exists(out_path):
        with open(out_path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        done.add(str(json.loads(line)["id"]))
                    except (ValueError, KeyError):
                        pass
        if done:
            log.info("resume: bỏ qua %d câu đã có trong %s", len(done), out_path)

    mode = "a" if resume and done else "w"
    with open(out_path, mode, encoding="utf-8") as out_f, \
            open(os.path.join(log_dir, "decisions.jsonl"), mode, encoding="utf-8") as log_f:
        businesses = [biz for biz in sorted(by_biz)
                      if not done.issuperset(q.id for q in by_biz[biz])]

        def write_business(biz: str, rows: list[tuple[Question, Answer, dict[str, Any]]]) -> None:
            for q, ans, info in rows:
                payload = {"id": q.id, **ans.to_json()}
                out_f.write(json.dumps(payload, ensure_ascii=False) + "\n")
                log_f.write(json.dumps({"id": q.id, "business": biz, "type": ans.type,
                                       **info}, ensure_ascii=False, default=str) + "\n")
                stats[ans.type] += 1

        def process_business(biz: str) -> tuple[str, list[tuple[Question, Answer, dict[str, Any]]]]:
            worker_llm = build_client() if use_llm else None
            try:
                ctx = build_context(os.path.join(root, "data", biz), rules.knobs, rules,
                                    worker_llm)
            except Exception as exc:  # noqa: BLE001
                log.warning("bỏ qua shop %s: %s", biz, exc)
                return biz, [(q, Answer(type=AnswerType.ABSTAIN.value),
                              {"path": "error_business", "error": str(exc)})
                             for q in by_biz[biz] if q.id not in done]
            rows = []
            for q in sorted(by_biz[biz], key=lambda x: x.id):
                if q.id not in done:
                    rows.append((q, *_answer_one(q, ctx, rules, cal, worker_llm)))
            return biz, rows

        if parallel > 1 and len(businesses) > 1:
            # openpyxl lazy-imports modules; initialize it before threads to avoid
            # circular-import races when several shops load xlsx simultaneously.
            import openpyxl  # noqa: F401
            log.info("parallel business workers=%d, businesses=%d", parallel, len(businesses))
            with ThreadPoolExecutor(max_workers=parallel) as pool:
                futures = [pool.submit(process_business, biz) for biz in businesses]
                for future in as_completed(futures):
                    biz, rows = future.result()
                    write_business(biz, rows)
                    out_f.flush()
                    log_f.flush()
        else:
            for biz in businesses:
                try:
                    ctx = build_context(os.path.join(root, "data", biz), rules.knobs, rules, llm)
                except Exception as exc:  # noqa: BLE001
                    log.warning("bỏ qua shop %s: %s", biz, exc)
                    write_business(biz, [(q, Answer(type=AnswerType.ABSTAIN.value),
                                         {"path": "error_business", "error": str(exc)})
                                        for q in by_biz[biz] if q.id not in done])
                    continue
                for q in sorted(by_biz[biz], key=lambda x: x.id):
                    if q.id in done:
                        continue
                    ans, info = _answer_one(q, ctx, rules, cal, llm)
                    write_business(biz, [(q, ans, info)])

    summary = {"split": split, "n": len(questions), "by_type": dict(stats),
               "elapsed_s": round(time.time() - t0, 1), "out": out_path}
    log.info("xong: %s", summary)
    return summary


def _error_ids(paths: list[str], limit: int) -> set[str]:
    """Build a stable hard-set: wrong predictions first, abstains as fill."""
    answers = load_answers(os.path.join(config.DATA_ROOT, "train", "answers.jsonl"))
    seen: set[str] = set()
    wrong: list[str] = []
    abstain: list[str] = []
    for path in paths:
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                obj = json.loads(line)
                qid = str(obj.get("id", ""))
                if not qid or qid in seen or qid not in answers:
                    continue
                pred = Answer.from_jsonl(obj)
                if pred.type != AnswerType.ABSTAIN.value and not is_correct(pred, answers[qid]):
                    wrong.append(qid)
                    seen.add(qid)
    seen.clear()
    for path in paths:
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                obj = json.loads(line)
                qid = str(obj.get("id", ""))
                if not qid or qid in seen or qid not in answers:
                    continue
                if Answer.from_jsonl(obj).type == AnswerType.ABSTAIN.value:
                    abstain.append(qid)
                    seen.add(qid)
    return set((wrong + abstain)[:limit])


def _answer_one(q: Question, ctx: Any, rules: Any, cal: Any, llm: Any
                ) -> tuple[Answer, dict[str, Any]]:
    info: dict[str, Any] = {}
    q_nd = expand_abbrev(nd(q.text))
    windows, unresolved = resolve_time(q_nd, q.as_of, rules.knobs, cal)
    entities = link_entities(q_nd, ctx.entity_index)
    having = extract_having(q_nd)
    info["windows"] = [w.label for w in windows]
    info["entities"] = [e.canonical_name for e in entities][:3]
    # Có cụm thời gian nhưng không dựng được cửa sổ ⇒ không thể trả lời đúng
    # kỳ. Thà abstain (0) còn hơn chạy toàn bộ dữ liệu và bị −1.
    if unresolved and not windows:
        info["path"] = "unresolved_time"
        info["unresolved"] = unresolved[:3]
        return Answer(type=AnswerType.ABSTAIN.value), info

    # 1. đường xác định
    specs = candidate_specs(q_nd, windows, entities, having, ctx.value_dict)
    ans, spec, debug = run_specs(specs, ctx, rules.knobs, windows, q.as_of)
    info["deterministic"] = {"tried": debug.get("tried"), "spec": debug.get("spec"),
                              "errors": debug.get("errors", [])[:3]}
    # 2. trả lời được không?
    check = check_answerability(q_nd, ctx, windows, entities, q.as_of)
    info["answerability"] = {"ok": check.answerable, "reason": check.reason,
                             "p": check.p_unanswerable}
    if not check.answerable:
        info["path"] = "unanswerable"
        return Answer(type=AnswerType.UNANSWERABLE.value, reason=check.reason), info

    # Planner là đường chính khi bật: LLM chỉ chọn template có sẵn, nên chạy
    # trước và ưu tiên hơn deterministic. Deterministic vẫn là fallback khi
    # planner không có template/kết quả.
    planner_mode = os.environ.get("DATAMATE_PLANNER", "1").lower() not in (
        "0", "legacy", "off")
    det_first = os.environ.get("DATAMATE_DETERMINISTIC_FIRST", "0") == "1"
    force_llm = os.environ.get("DATAMATE_FORCE_LLM", "0") == "1"
    if ans is not None and not force_llm and (det_first or not planner_mode):
        det_dec = decide(q_nd, ctx, windows, entities, candidate=ans,
                         spec_metric=spec.metric if spec else None,
                         spec_subject=spec.subject if spec else None,
                         spec_intent=spec.intent if spec else None,
                         spec_output=spec.output if spec else None,
                         as_of=q.as_of, candidate_path="deterministic")
        if det_dec.action == "answer" and det_dec.answer is not None:
            info["decision"] = {"action": det_dec.action, "reason": det_dec.reason,
                                "p_unanswerable": det_dec.p_unanswerable}
            info["path"] = "deterministic"
            return det_dec.answer, info

    candidates: list[tuple[str, Answer, Any]] = []
    llm_only = os.environ.get("DATAMATE_LLM_ONLY", "0") == "1"
    det_candidate = None if llm_only or ans is None else ("deterministic", ans, spec)

    # Tối đa ba candidate độc lập: planner, deterministic (fallback), LLM SQL.
    ent_names = [f"{e.kind}: {e.canonical_name}" for e in entities[:3]]
    ans, p1 = run_path1(q.text, ctx, rules.knobs, windows, ent_names, q.as_of, llm)
    info["path1"] = p1
    if ans is not None:
        candidates.append(("path1_spec", ans, p1.get("spec") or {}))
    if det_candidate is not None:
        candidates.append(det_candidate)
    ans, p2 = run_path2(q.text, ctx, rules.knobs, windows, q.as_of, llm)
    info["path2"] = p2
    if ans is not None:
        candidates.append(("path2_sql", ans, {}))

    accepted: list[tuple[str, Answer, float]] = []
    for path, candidate, meta in candidates[:3]:
        if isinstance(meta, dict):
            metric, subject = meta.get("metric"), meta.get("subject")
            intent, output = meta.get("intent"), meta.get("output")
        else:
            metric, subject = getattr(meta, "metric", None), getattr(meta, "subject", None)
            intent, output = getattr(meta, "intent", None), getattr(meta, "output", None)
        dec = decide(q_nd, ctx, windows, entities, candidate=candidate,
                     spec_metric=metric, spec_subject=subject,
                     spec_intent=intent, spec_output=output, as_of=q.as_of,
                     candidate_path=path)
        if dec.action == "answer" and dec.answer is not None:
            accepted.append((path, dec.answer, 1.0 - dec.p_unanswerable))
    if accepted:
        # Vote trên giá trị đã execute, không vote trên SQL. Hoà thì ưu tiên
        # planner > deterministic > SQL khi planner là đường chính.
        counts: Counter[str] = Counter(_answer_key(a) for _, a, _ in accepted)
        order = (["path1_spec", "deterministic", "path2_sql"] if planner_mode
                 else ["deterministic", "path1_spec", "path2_sql"])
        best = max(accepted, key=lambda x: (counts[_answer_key(x[1])],
                                             -order.index(x[0]),
                                             x[2]))
        info["ensemble"] = {"candidates": len(candidates), "accepted": len(accepted),
                            "agreement": counts[_answer_key(best[1])]}
        info["path"] = "ensemble_" + best[0]
        return best[1], info

    # 5. escalate / abstain
    ans, esc = escalate(q.text, ctx, llm, windows)
    info["escalate"] = esc
    dec = decide(q_nd, ctx, windows, entities, candidate=ans, as_of=q.as_of)
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


def _answer_key(answer: Answer) -> str:
    return json.dumps({"type": answer.type, "value": answer.value},
                      ensure_ascii=False, sort_keys=True, default=str)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default=config.SPLIT)
    ap.add_argument("--out", default=None)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--resume", action="store_true",
                    help="bỏ qua các câu đã có id trong file out (chạy tiếp lượt dở)")
    ap.add_argument("--parallel", type=int, default=1,
                    help="số business xử lý đồng thời; dùng >=2 cho API benchmark")
    ap.add_argument("--ids-file", default=None,
                    help="file chứa các question id cần chạy, mỗi dòng một id")
    ap.add_argument("--error-from", default=None,
                    help="submission files comma-separated để tạo hard-set")
    ap.add_argument("--error-limit", type=int, default=1000)
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO),
                        format="%(asctime)s %(levelname)s %(message)s")
    ids = None
    if args.ids_file:
        with open(args.ids_file, encoding="utf-8") as fh:
            ids = {line.strip() for line in fh if line.strip()}
    elif args.error_from:
        ids = _error_ids([p for p in args.error_from.split(",") if p], args.error_limit)
    summary = run(args.split, args.out, args.limit, use_llm=not args.no_llm,
                  resume=args.resume, parallel=max(1, args.parallel), ids=ids)
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
