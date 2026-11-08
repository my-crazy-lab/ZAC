"""LLM judge cho submission không có đáp án (public_test).

Với mỗi câu đã trả lời: dựng lại Spec → SQL → kết quả trên context của shop,
rồi đưa câu hỏi + đáp án dự đoán + SQL/kết quả + ngữ cảnh shop cho LLM chấm
correct / incorrect / uncertain.

Đây là **proxy**, không phải điểm chấm chính thức của BTC.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
from dtypes import Answer, Question, Spec, TimeWindow  # noqa: E402
from engine.compile import compile_spec  # noqa: E402
from engine.executor import run_sql  # noqa: E402
from ingest.reader import load_questions  # noqa: E402
from llm.client import build_client  # noqa: E402
from rules.rulebook_parser import parse_rulebook  # noqa: E402
from schema.context import render_context  # noqa: E402
from schema.views import build_context  # noqa: E402
from text.normalize import expand_abbrev, nd  # noqa: E402
from timeutil.calendar_vi import load_calendar  # noqa: E402
from timeutil.resolver import resolve_time  # noqa: E402

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["correct", "incorrect", "uncertain"]},
        "confidence": {"type": "number"},
        "reason": {"type": "string"},
    },
    "required": ["verdict", "confidence", "reason"],
    "additionalProperties": False,
}

PROMPT = """Bạn là giám khảo bài toán hỏi đáp dữ liệu bán hàng. Hãy chấm đáp án
dự đoán dựa trên ngữ cảnh shop, câu hỏi, và bằng chứng SQL/kết quả bên dưới.

[NGỮ CẢNH SHOP]
{context}

[SCHEMA CARD]
{card}

[CÂU HỎI]
{question}

[AS_OF] {as_of}

[ĐÁP ÁN DỰ ĐOÁN]
type={answer_type} value={answer_value}

[ĐƯỜNG ĐÃ CHỌN] {path}

[SPEC ĐÃ CHỌN]
{spec}

[SQL ĐÃ CHẠY]
{sql}

[KẾT QUẢ SQL]
{rows}

[CÁCH CHẤM]
- correct: SQL/spec đúng metric, subject, thời gian, filter; đáp án khớp kết quả
  và đúng định dạng câu hỏi.
- incorrect: sai metric/miền, sai kỳ, thiếu filter đối tượng, nhầm đơn vị/doanh
  thu/trạng thái, hoặc đáp án không khớp kết quả SQL.
- uncertain: thiếu bằng chứng để kết luận chắc chắn.
- KHÔNG được coi kết quả 0 là sai chỉ vì bạn nghĩ dữ liệu "phải có". Nếu SQL/spec
  đúng metric, kỳ, filter và kết quả là 0 thì chấm correct hoặc uncertain.
- Chỉ chấm incorrect khi có lỗi cụ thể trong spec/SQL/đáp án, không suy đoán.
Chỉ dựa vào bằng chứng được cung cấp; không bịa dữ liệu ngoài.
Trả JSON: verdict, confidence (0..1), reason (ngắn, nêu lỗi cụ thể nếu sai)."""


def _load_jsonl(path: str) -> list[dict[str, Any]]:
    out = []
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
    return out


def _rules(split_dir: str) -> Any:
    text = open(os.path.join(split_dir, "rulebook.md"), encoding="utf-8").read()
    train_path = os.path.join(config.DATA_ROOT, "train", "rulebook.md")
    train = open(train_path, encoding="utf-8").read() if os.path.exists(train_path) else ""
    return parse_rulebook(text, train, None)


def _spec_of(info: dict[str, Any]) -> dict[str, Any] | None:
    """Lấy đúng spec của đường đã tạo ra đáp án cuối, không mặc định path1."""
    path = str(info.get("path") or "")
    p1 = info.get("path1") or {}
    det = info.get("deterministic") or {}
    if "deterministic" in path and det.get("spec"):
        return det["spec"]
    if "path1" in path and p1.get("spec"):
        return p1["spec"]
    if p1.get("spec"):
        return p1["spec"]
    if det.get("spec"):
        return det["spec"]
    return None


class Judge:
    def __init__(self) -> None:
        self._local = threading.local()

    def llm(self) -> Any:
        if not hasattr(self._local, "llm"):
            self._local.llm = build_client()
        return self._local.llm

    def grade(self, prompt: str) -> dict[str, Any]:
        try:
            outs = self.llm().generate([prompt], json_schema=JUDGE_SCHEMA)
            text = (outs or [""])[0]
            obj = json.loads(text)
            verdict = str(obj.get("verdict", "uncertain"))
            if verdict not in ("correct", "incorrect", "uncertain"):
                verdict = "uncertain"
            return {"verdict": verdict,
                    "confidence": float(obj.get("confidence", 0.0) or 0.0),
                    "reason": str(obj.get("reason", ""))[:300]}
        except Exception as exc:  # noqa: BLE001
            return {"verdict": "uncertain", "confidence": 0.0, "reason": f"judge_error:{exc}"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="public_test")
    ap.add_argument("--submission", default="public_test/submission_planner_1000.jsonl")
    ap.add_argument("--decisions", default="public_test/logs/decisions.jsonl")
    ap.add_argument("--out", default="public_test/logs/judge_public_test.jsonl")
    ap.add_argument("--summary", default="public_test/logs/judge_summary.json")
    ap.add_argument("--workers", type=int, default=3)
    args = ap.parse_args()

    split_dir = os.path.join(config.DATA_ROOT, args.split)
    questions = {q.id: q for q in load_questions(os.path.join(split_dir, "questions.jsonl"))}
    sub = {str(r["id"]): r for r in _load_jsonl(args.submission)}
    dec = {str(r["id"]): r for r in _load_jsonl(args.decisions)}
    rules = _rules(split_dir)
    cal = load_calendar(os.path.join(split_dir, "calendar.csv"))
    judge = Judge()

    answered = [(qid, r) for qid, r in sub.items()
                if r.get("type") not in ("abstain", "unanswerable") and qid in questions]
    contexts: dict[str, Any] = {}
    evidence: list[dict[str, Any]] = []

    for qid, row in answered:
        q = questions[qid]
        biz = q.business_id
        if biz not in contexts:
            try:
                contexts[biz] = build_context(os.path.join(split_dir, "data", biz),
                                              rules.knobs, rules, None)
            except Exception as exc:  # noqa: BLE001
                contexts[biz] = exc
        ctx = contexts[biz]
        info = dec.get(qid, {})
        spec_dict = _spec_of(info)
        sql, rows_text = "", "(không dựng lại được SQL)"
        if not isinstance(ctx, Exception) and spec_dict:
            try:
                spec = Spec.from_dict(spec_dict)
                windows, _ = resolve_time(expand_abbrev(nd(q.text)), q.as_of,
                                          rules.knobs, cal)
                plan = compile_spec(spec, ctx, rules.knobs, windows, q.as_of)
                res = run_sql(ctx.con, plan.sql)
                sql = plan.sql
                if res.error:
                    rows_text = f"ERROR: {res.error}"
                else:
                    rows_text = json.dumps([list(r) for r in (res.rows or [])[:5]],
                                           ensure_ascii=False, default=str)
            except Exception as exc:  # noqa: BLE001
                rows_text = f"ERROR: {type(exc).__name__}: {exc}"
        context_text = "" if isinstance(ctx, Exception) else render_context(ctx.context)
        card = "" if isinstance(ctx, Exception) else getattr(ctx, "card", "")
        evidence.append({
            "id": qid, "business_id": biz, "question": q.text, "as_of": q.as_of.isoformat(),
            "answer": row, "spec": spec_dict, "sql": sql, "rows": rows_text,
            "prompt": PROMPT.format(
                context=context_text[:2600], card=card[:1800], question=q.text,
                as_of=q.as_of.isoformat(), answer_type=row.get("type"),
                answer_value=row.get("answer"), path=info.get("path", ""),
                spec=json.dumps(spec_dict, ensure_ascii=False),
                sql=sql[:2500], rows=rows_text[:1200]),
        })

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        verdicts = list(pool.map(lambda e: judge.grade(e["prompt"]), evidence))

    counts = Counter()
    by_type: dict[str, list[int]] = defaultdict(list)
    by_biz: dict[str, list[int]] = defaultdict(list)
    out_rows = []
    for e, v in zip(evidence, verdicts):
        counts[v["verdict"]] += 1
        score = 1 if v["verdict"] == "correct" else (-1 if v["verdict"] == "incorrect" else 0)
        by_type[str(e["answer"].get("type"))].append(score)
        by_biz[e["business_id"]].append(score)
        out_rows.append({**{k: e[k] for k in ("id", "business_id", "question", "as_of",
                                              "answer", "spec", "sql")},
                         "judge": v})

    n = len(out_rows)
    n_all = len(sub)
    correct, incorrect = counts["correct"], counts["incorrect"]
    summary = {
        "split": args.split,
        "n_submission": n_all,
        "n_graded": n,
        "correct": correct,
        "incorrect": incorrect,
        "uncertain": counts["uncertain"],
        "pa_on_graded": round((correct - incorrect) / n, 4) if n else 0.0,
        "pa_on_all_submission": round((correct - incorrect) / n_all, 4) if n_all else 0.0,
        "precision_proxy": round(correct / (correct + incorrect), 4)
        if (correct + incorrect) else 0.0,
        "pa_by_type": {k: round(sum(v) / len(v), 4) for k, v in sorted(by_type.items())},
        "pa_by_business": {k: round(sum(v) / len(v), 4) for k, v in sorted(by_biz.items())},
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        for row in out_rows:
            fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    with open(args.summary, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=1)
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
