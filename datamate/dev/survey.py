"""Khảo sát dữ liệu (M0) — sinh artefact trong ``survey/`` (chỉ dùng lúc dev).

Chạy:
    python dev/survey.py [--split train public_test]

Sinh:
- ``survey/columns.csv``      : business, file, sheet, cột, kiểu đoán, 5 giá trị mẫu, tỉ lệ null, số giá trị phân biệt
- ``survey/calendar_head.txt``: vài dòng đầu calendar.csv + tên cột
- ``survey/rulebook_sentences.txt``: câu rulebook đánh số (mọi tham chiếu "§" trong code trỏ tới số câu này)
- ``survey/answers_stats.json``: phân bố type, tỉ lệ null, mẫu câu null, mẫu theo type
- ``survey/as_of_stats.json`` : mỗi business có bao nhiêu as_of phân biệt, min, max
- ``survey/price_effect_samples.txt``: câu chứa "tang gia|giam gia|doi gia"
- ``survey/value_dict.json``  : tập giá trị phân biệt của các cột từ điển (≤ 50 giá trị)
- ``dev/splits.json``         : chia dev/holdout 24/6 theo seed cố định
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import re
import sys
from collections import Counter, defaultdict
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
from ingest.clean import detect_date_column, looks_numeric, nd  # noqa: E402
from ingest.reader import business_dirs, load_answers, load_business, load_questions  # noqa: E402

VALUE_DICT_HINTS = ("channel", "pay_method", "customer_group", "employee", "size",
                    "category", "status", "nhom", "phuong thuc", "kenh", "loai hinh",
                    "nhan vien", "phuong thuc tt", "don vi", "quy doi", "trang thai")


def _guess_type(s: Any) -> str:
    if s is None or len(s) == 0:
        return "empty"
    if s.dtype == object:
        vals = s.dropna()
        if vals.empty:
            return "empty"
        uniq = {str(v).strip().lower() for v in vals.head(200)}
        if len(uniq) <= 3 and all(v in ("true", "false", "0", "1", "co", "khong", "yes", "no")
                                  for v in uniq):
            return "bool"
    is_date, _has_time = detect_date_column(s)
    if is_date:
        return "date"
    if looks_numeric(s):
        return "number"
    return "string"


def _samples(s: Any, k: int = 5) -> str:
    vals = [str(v) for v in s.dropna().head(200).tolist()]
    out: list[str] = []
    for v in vals:
        if v not in out:
            out.append(v)
        if len(out) >= k:
            break
    return " | ".join(out)


def survey_columns(splits: list[str], out_dir: str) -> None:
    rows: list[dict[str, Any]] = []
    value_dict: dict[str, dict[str, list[str]]] = {}
    for split in splits:
        root = os.path.join(config.DATA_ROOT, split)
        data_root = os.path.join(root, "data")
        for biz_dir in business_dirs(data_root):
            bid = os.path.basename(biz_dir)
            tables = load_business(biz_dir)
            for t in tables:
                for col in t.df.columns:
                    if col.endswith("__nd"):
                        continue
                    s = t.df[col]
                    distinct = int(s.nunique(dropna=True))
                    rows.append({
                        "business": bid,
                        "split": split,
                        "file": t.source,
                        "sheet": t.sheet or "",
                        "table": t.name,
                        "column": col,
                        "type": _guess_type(s),
                        "null_ratio": round(float(s.isna().mean()), 4),
                        "n_distinct": distinct,
                        "samples": _samples(s),
                    })
                    cnd = nd(col)
                    if distinct <= 50 and any(h in cnd for h in VALUE_DICT_HINTS):
                        vals = sorted({str(v).strip() for v in s.dropna().head(500).tolist()})
                        key = f"{bid}:{t.name}:{col}"
                        value_dict[key] = vals
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "columns.csv")
    fields = ["business", "split", "file", "sheet", "table", "column", "type",
              "null_ratio", "n_distinct", "samples"]
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    with open(os.path.join(out_dir, "value_dict.json"), "w", encoding="utf-8") as fh:
        json.dump(value_dict, fh, ensure_ascii=False, indent=1)
    print(f"[survey] {path}: {len(rows)} cột")


def _rulebook_sentences(text: str) -> list[str]:
    """Tách rulebook thành câu (theo dòng, dấu '.', bullet)."""
    out: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        s = re.sub(r"^\s*[-*•]\s*", "", s)
        s = re.sub(r"^\s*\d+[.)]\s*", "", s)
        if not s:
            continue
        # tách theo dấu chấm khi kết thúc câu
        parts = re.split(r"(?<=[.!?])\s+(?=[A-ZÀ-Ữ*•])", s)
        for p in parts:
            p = p.strip()
            if p:
                out.append(p)
    return out


def survey_rulebook(splits: list[str], out_dir: str) -> None:
    os.makedirs(out_dir, exist_ok=True)
    all_sent: list[str] = []
    for split in splits:
        path = os.path.join(config.DATA_ROOT, split, "rulebook.md")
        if not os.path.exists(path):
            continue
        text = open(path, encoding="utf-8").read()
        sents = _rulebook_sentences(text)
        with open(os.path.join(out_dir, f"rulebook_sentences_{split}.txt"), "w",
                  encoding="utf-8") as fh:
            for i, s in enumerate(sents, 1):
                fh.write(f"{i}\t{s}\n")
        all_sent.extend(sents)
    with open(os.path.join(out_dir, "rulebook_sentences.txt"), "w", encoding="utf-8") as fh:
        for i, s in enumerate(all_sent, 1):
            fh.write(f"{i}\t{s}\n")
    print(f"[survey] rulebook_sentences.txt: {len(all_sent)} câu")


def survey_calendar(splits: list[str], out_dir: str) -> None:
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "calendar_head.txt"), "w", encoding="utf-8") as fh:
        for split in splits:
            path = os.path.join(config.DATA_ROOT, split, "calendar.csv")
            if not os.path.exists(path):
                continue
            fh.write(f"=== {split}/calendar.csv ===\n")
            with open(path, encoding="utf-8") as f:
                for i, line in enumerate(f):
                    if i > 12:
                        break
                    fh.write(line)
            fh.write("\n")
    print("[survey] calendar_head.txt")


def survey_answers(split: str, out_dir: str) -> None:
    root = os.path.join(config.DATA_ROOT, split)
    qpath = os.path.join(root, "questions.jsonl")
    apath = os.path.join(root, "answers.jsonl")
    if not os.path.exists(apath):
        return
    answers = load_answers(apath)
    questions = {q.id: q for q in load_questions(qpath)}
    type_counts: Counter[str] = Counter()
    null_ids: list[str] = []
    by_type: dict[str, list[str]] = defaultdict(list)
    for qid, ans in answers.items():
        t = str(ans.get("type", ""))
        type_counts[t] += 1
        if ans.get("answer") is None:
            null_ids.append(qid)
        else:
            by_type[t].append(qid)
    stats = {
        "split": split,
        "n": len(answers),
        "type_counts": dict(sorted(type_counts.items())),
        "null_count": len(null_ids),
        "null_rate": round(len(null_ids) / max(1, len(answers)), 4),
        "null_samples": [
            {"id": qid, "question": questions[qid].text, "business_id": questions[qid].business_id,
             "as_of": questions[qid].as_of.isoformat()}
            for qid in sorted(null_ids)[:30]
        ],
        "samples_by_type": {
            t: [{"id": qid, "question": questions[qid].text, "business_id": questions[qid].business_id,
                 "as_of": questions[qid].as_of.isoformat(), "answer": answers[qid].get("answer"),
                 "alias": answers[qid].get("alias", [])}
                for qid in sorted(ids)[:50]]
            for t, ids in sorted(by_type.items())
        },
    }
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, f"answers_stats_{split}.json"), "w", encoding="utf-8") as fh:
        json.dump(stats, fh, ensure_ascii=False, indent=1)
    print(f"[survey] answers_stats_{split}.json: {dict(sorted(type_counts.items()))}")


def survey_as_of(split: str, out_dir: str) -> None:
    qpath = os.path.join(config.DATA_ROOT, split, "questions.jsonl")
    if not os.path.exists(qpath):
        return
    qs = load_questions(qpath)
    per_biz: dict[str, list[str]] = defaultdict(list)
    for q in qs:
        per_biz[q.business_id].append(q.as_of.isoformat())
    stats = {}
    for bid, dates in sorted(per_biz.items()):
        uniq = sorted(set(dates))
        stats[bid] = {"n_questions": len(dates), "n_distinct": len(uniq),
                      "min": uniq[0], "max": uniq[-1]}
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, f"as_of_stats_{split}.json"), "w", encoding="utf-8") as fh:
        json.dump(stats, fh, ensure_ascii=False, indent=1)
    n_multi = sum(1 for v in stats.values() if v["n_distinct"] > 1)
    print(f"[survey] as_of_stats_{split}.json: {n_multi}/{len(stats)} business có nhiều as_of")


def survey_price_effect(split: str, out_dir: str) -> None:
    qpath = os.path.join(config.DATA_ROOT, split, "questions.jsonl")
    if not os.path.exists(qpath):
        return
    os.makedirs(out_dir, exist_ok=True)
    pat = re.compile(r"tang gia|giam gia|doi gia|tang giá|giảm giá|đổi giá", re.IGNORECASE)
    n = 0
    with open(os.path.join(out_dir, f"price_effect_samples_{split}.txt"), "w", encoding="utf-8") as fh:
        for q in load_questions(qpath):
            if pat.search(q.text):
                fh.write(f"{q.id}\t{q.business_id}\t{q.text}\n")
                n += 1
    print(f"[survey] price_effect_samples_{split}.txt: {n} câu")


def make_splits(split: str = "train") -> dict[str, list[str]]:
    """Chia dev/holdout 24/6 theo seed cố định (EXECUTION-MVP.md §0.6)."""
    qpath = os.path.join(config.DATA_ROOT, split, "questions.jsonl")
    if not os.path.exists(qpath):
        return {"dev": [], "holdout": []}
    ids = sorted({q.business_id for q in load_questions(qpath)})
    rng = random.Random(config.RANDOM_SEED)
    holdout = sorted(rng.sample(ids, min(config.HOLDOUT_BUSINESSES, len(ids))))
    dev = [b for b in ids if b not in set(holdout)]
    return {"dev": dev, "holdout": holdout}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", nargs="+", default=["train", "public_test"])
    args = ap.parse_args()
    out_dir = config.SURVEY_DIR
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs("dev", exist_ok=True)
    for split in args.split:
        survey_answers(split, out_dir)
        survey_as_of(split, out_dir)
        survey_price_effect(split, out_dir)
    survey_columns(args.split, out_dir)
    survey_rulebook(args.split, out_dir)
    survey_calendar(args.split, out_dir)
    splits = make_splits("train")
    with open(os.path.join("dev", "splits.json"), "w", encoding="utf-8") as fh:
        json.dump(splits, fh, ensure_ascii=False, indent=1)
    print(f"[survey] dev/splits.json: dev={len(splits['dev'])} holdout={len(splits['holdout'])}")


if __name__ == "__main__":
    main()
