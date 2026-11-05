"""Chạy đề public_test: STT shim → transcript → agent → submission.jsonl (M2 khói).

public_test không có nhãn/transcript nên `eval/run.py` không dùng được
(`transcript_of` sẽ raise). Script này gắn transcript STT vào mỗi item
rồi tái dùng `Agent` + `run_one` của eval.

    python lifemate/scripts/run_public.py --out runs/public_stt --workers 4

`Agent.run` không giữ state dùng chung giữa các mẫu nên chạy ThreadPool
an toàn; mỗi mẫu vẫn đúng 1 ToolEnv và luôn ghi đúng 1 dòng submission (R8).
"""
import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lifemate import config  # noqa: E402
from lifemate.asr import transcribe_file, wav_of  # noqa: E402
from lifemate.datatypes import Deadline  # noqa: E402
from lifemate.envloader import load_toolenv_class  # noqa: E402
from lifemate.eval import run as R  # noqa: E402

SPLIT = "public_test"


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Chạy public_test qua STT + agent")
    p.add_argument("--out", default="runs/public_stt")
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--ids", default=None, help="file danh sách id (mỗi dòng một id)")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    config.SPLIT_DEFAULT = SPLIT
    items = R.load_items(SPLIT)
    ids = R.load_ids(args.ids) or list(items.keys())
    if args.limit:
        ids = ids[:args.limit]

    catalog = R.Catalog(str(config.catalog_path(SPLIT)))
    llm = R.LLM(config.LLM_BASE_URL, config.LLM_API_KEY, config.LLM_MODEL,
                extra_body=config.LLM_EXTRA_BODY, temperature=config.LLM_TEMPERATURE,
                timeout=config.LLM_TIMEOUT, max_retries=config.LLM_MAX_RETRIES)
    agent = R.build_agent(catalog, llm, R.load_json_file(config.reports_dir() / "ref_sources.json", {}) or {})
    EnvCls = load_toolenv_class(SPLIT, config.DATA_ROOT)

    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = (config.REPO_ROOT / out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    def work(sample_id):
        t0 = time.time()
        row = {"id": sample_id, "transcript": "", "n_calls": 0,
               "tool_calls": [], "state_hash": "", "error": None,
               "stt_s": 0.0, "agent_s": 0.0}
        try:
            item = dict(items[sample_id])
            t_stt = time.time()
            row["transcript"] = transcribe_file(wav_of(SPLIT, item)).strip()
            row["stt_s"] = round(time.time() - t_stt, 2)
            item["label"] = {"audio_text": row["transcript"]}
            env = EnvCls(SPLIT, sample_id, root=config.DATA_ROOT)
            t_agent = time.time()
            tool_calls, state_hash, _debug, error, _log = R.run_one(
                item, env, agent, Deadline(config.SAMPLE_DEADLINE_S))
            row["agent_s"] = round(time.time() - t_agent, 2)
            row["tool_calls"] = tool_calls
            row["state_hash"] = state_hash
            row["n_calls"] = len(tool_calls)
            row["error"] = error
        except Exception as e:  # noqa: BLE001 - một mẫu lỗi không được làm sập lượt chạy
            row["error"] = f"{type(e).__name__}: {e}"
        row["elapsed_s"] = round(time.time() - t0, 2)
        return row

    started = time.time()
    rows = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        for row in pool.map(work, ids):
            rows.append(row)
    by_id = {r["id"]: r for r in rows}

    with open(out_dir / "submission.jsonl", "w", encoding="utf-8") as f:
        for sample_id in ids:
            r = by_id[sample_id]
            f.write(json.dumps({"id": sample_id, "tool_calls": r["tool_calls"],
                                "state_hash": r["state_hash"]}, ensure_ascii=False) + "\n")
    with open(out_dir / "run_log.jsonl", "w", encoding="utf-8") as f:
        for sample_id in ids:
            f.write(json.dumps(by_id[sample_id], ensure_ascii=False) + "\n")
    total = round(time.time() - started, 2)
    summary = {
        "n": len(rows),
        "elapsed_s": total,
        "avg_s": round(total / len(rows), 2) if rows else 0,
        "max_s": max((r["elapsed_s"] for r in rows), default=0),
        "over_30s": sum(1 for r in rows if r["elapsed_s"] > 30),
        "empty_transcript": sum(1 for r in rows if not r["transcript"]),
        "empty_calls": sum(1 for r in rows if not r["tool_calls"]),
        "errors": sum(1 for r in rows if r["error"]),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                          encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"→ {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
