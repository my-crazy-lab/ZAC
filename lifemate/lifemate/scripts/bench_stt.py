"""Đo proxy leaderboard: transcript STT thật + luật timeout 30s (M2b).

Giữ nguyên nhãn gold để chấm; chỉ thay transcript đầu vào bằng STT shim.
Chạy trên train với --ids (khuyến nghị subset phân tầng của heldout).
Luật điểm: mẫu quá 30s = 0 (BTC timeout), còn lại official-style
(refuse đúng-trống = 1, không thì hash khớp mới tính F1 fuzzy).
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
from lifemate.eval import metrics as M  # noqa: E402

SPLIT = "train"
TIMEOUT_S = 30.0


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Proxy leaderboard với STT thật")
    p.add_argument("--ids", required=True)
    p.add_argument("--out", default="runs/stt_bench")
    p.add_argument("--workers", type=int, default=2)
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    config.SPLIT_DEFAULT = SPLIT
    items = R.load_items(SPLIT)
    ids = R.load_ids(args.ids)
    catalog = R.Catalog(str(config.catalog_path(SPLIT)))
    fuzzy_params = M.fuzzy_params_from_catalog(catalog)
    llm = R.LLM(config.LLM_BASE_URL, config.LLM_API_KEY, config.LLM_MODEL,
                extra_body=config.LLM_EXTRA_BODY, temperature=config.LLM_TEMPERATURE,
                timeout=config.LLM_TIMEOUT, max_retries=config.LLM_MAX_RETRIES)
    agent = R.build_agent(catalog, llm, R.load_json_file(config.reports_dir() / "ref_sources.json", {}) or {})
    EnvCls = load_toolenv_class(SPLIT, config.DATA_ROOT)
    gold_hash = R.load_json_file(config.cache_dir() / "gold_hash.json", {}) or {}

    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = (config.REPO_ROOT / out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    def work(sample_id):
        t0 = time.time()
        item = dict(items[sample_id])
        label = dict(item.get("label") or {})
        try:
            stt = transcribe_file(wav_of(SPLIT, item)).strip()
        except Exception:  # noqa: BLE001
            stt = ""
        label["audio_text"] = stt
        item["label"] = label
        try:
            env = EnvCls(SPLIT, sample_id, root=config.DATA_ROOT)
            tool_calls, state_hash, debug, error, log = R.run_one(
                item, env, agent, Deadline(config.SAMPLE_DEADLINE_S))
        except Exception as e:  # noqa: BLE001
            tool_calls, state_hash, debug, error = [], "", {}, f"{type(e).__name__}: {e}"
        row = R.make_row(item, tool_calls, state_hash, gold_hash.get(sample_id),
                         debug, error, fuzzy_params)
        row["elapsed_s"] = round(time.time() - t0, 2)
        row["stt"] = stt
        row["gold_transcript"] = (items[sample_id].get("label") or {}).get("audio_text", "")
        return row

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        rows = list(pool.map(work, ids))
    by_id = {r["id"]: r for r in rows}
    ordered = [by_id[i] for i in ids if i in by_id]

    def official(r):
        if r["elapsed_s"] > TIMEOUT_S:
            return 0.0
        if r["group"] == "refuse" and r["n_calls"] == 0:
            return 1.0
        return r["f1"]["fuzzy-aware"] if r["hash_match"] else 0.0

    summary = M.summarize(ordered)
    summary["official_style"] = sum(official(r) for r in ordered) / len(ordered) if ordered else 0.0
    summary["official_style_no_timeout"] = sum(
        (1.0 if (r["group"] == "refuse" and r["n_calls"] == 0)
         else (r["f1"]["fuzzy-aware"] if r["hash_match"] else 0.0)) for r in ordered
    ) / len(ordered) if ordered else 0.0
    summary["timeout_n"] = sum(1 for r in ordered if r["elapsed_s"] > TIMEOUT_S)
    (out_dir / "per_sample.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in ordered), encoding="utf-8")
    (out_dir / "metrics.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                          encoding="utf-8")
    print(json.dumps({k: summary[k] for k in (
        "n", "official_style", "official_style_no_timeout", "f1_call_fuzzy-aware",
        "f1_call_strict", "hash_match", "timeout_n")}, ensure_ascii=False, indent=2))
    print(f"→ {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
