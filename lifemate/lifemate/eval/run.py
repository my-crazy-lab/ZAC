"""Chạy agent trên một split và báo cáo metric (EXECUTION-PLAN.md §9.3).

    python eval/run.py --split train --ids dev300_ids.txt --out runs/mvp1
    python eval/run.py --split train --ids tune_ids.txt --tune-scope --out runs/mvp3_scope

MVP: transcript lấy thẳng từ `label.audio_text` (không có STT, không xuất file nộp bài).
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lifemate import config  # noqa: E402
from lifemate.agent import Agent, write_debug  # noqa: E402
from lifemate.catalog import Catalog  # noqa: E402
from lifemate.envloader import load_toolenv_class  # noqa: E402
from lifemate.eval import metrics as M  # noqa: E402
from lifemate.llm import LLM  # noqa: E402
from lifemate.scope import bm25_scope_features  # noqa: E402
from lifemate.datatypes import Deadline  # noqa: E402


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Chạy harness trên một split")
    parser.add_argument("--split", default=config.SPLIT_DEFAULT)
    parser.add_argument("--ids", default=None, help="file danh sách id (mỗi dòng một id)")
    parser.add_argument("--out", default=None, help="thư mục kết quả (runs/<tên>)")
    parser.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                        help="ghi đè cấu hình cho lần chạy này")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--tune-scope", action="store_true")
    parser.add_argument("--debug", action="store_true", help="ghi debug/<id>.json")
    parser.add_argument("--no-scope", action="store_true", help="bỏ qua bước scope (ablation)")
    return parser.parse_args(argv)


def load_items(split: str) -> dict:
    path = config.samples_path(split)
    items = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            items[item["id"]] = item
    return items


def load_ids(path) -> list:
    if not path:
        return []
    p = Path(path)
    if not p.is_file():
        p = config.REPO_ROOT / path
    ids = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                ids.append(line)
    return ids


def load_json_file(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return default


def build_fewshot_index(items, split):
    """Chỉ mục few-shot: mẫu train trong `tune_ids` (không gồm heldout)."""
    if not config.ENABLE_FEWSHOT:
        return None
    from lifemate.retrieval import FewShotIndex
    tune_path = config.REPO_ROOT / "tune_ids.txt"
    tune_ids = set()
    if tune_path.is_file():
        with open(tune_path, encoding="utf-8") as f:
            tune_ids = {line.strip() for line in f if line.strip()}
    samples = [it for it in items.values()
               if it["id"] in tune_ids and (it.get("label") or {}).get("tool_calls") is not None]
    if not samples:
        samples = list(items.values())
    return FewShotIndex(samples)


def build_agent(catalog, llm, ref_sources, fewshot_index=None):
    policy_rules = load_json_file(config.reports_dir() / "policy_rules.json", {}) or {}
    return Agent(catalog, llm, ref_sources=ref_sources, fewshot_index=fewshot_index,
                 policy_rules=policy_rules)


def run_one(item, env, agent, deadline):
    """Chạy một mẫu; luôn trả về (tool_calls, state_hash, debug, error)."""
    log = []
    error = None
    debug = {}
    try:
        debug = agent.run(item, env, config.split_dir(config.SPLIT_DEFAULT), deadline, log) or {}
    except Exception as e:  # noqa: BLE001 - một mẫu lỗi không được làm sập lượt chạy
        error = f"{type(e).__name__}: {e}"
    try:
        tool_calls = env.get_tool_calls()
    except Exception:  # noqa: BLE001
        tool_calls = []
    try:
        state_hash = env.get_state_hash()
    except Exception:  # noqa: BLE001
        state_hash = ""
    return tool_calls, state_hash, debug, error, log


def make_row(item, tool_calls, state_hash, gold_hash, debug, error, fuzzy_params):
    gold_calls = ((item.get("label") or {}).get("tool_calls")) or []
    group = M.sample_group(item)
    row = {"id": item["id"], "group": group, "n_calls": len(tool_calls)}
    row["f1"] = {}
    for mode in ("strict", "fuzzy-aware", "soft"):
        res = M.f1_call(tool_calls, gold_calls, mode, fuzzy_params)
        row["f1"][mode] = res["f1"]
        row["f1"][f"{mode}_precision"] = res["precision"]
        row["f1"][f"{mode}_recall"] = res["recall"]
    row["hash_match"] = bool(gold_hash) and state_hash == gold_hash
    gold_ask = [c for c in gold_calls if M._is_ask(c)]
    pred_ask = [c for c in tool_calls if M._is_ask(c)]
    row["ask_correct"] = bool(
        gold_ask and pred_ask
        and gold_ask[0].get("arguments", {}).get("tool_name") == pred_ask[0].get("arguments", {}).get("tool_name")
        and set(gold_ask[0].get("arguments", {}).get("params") or [])
        == set(pred_ask[0].get("arguments", {}).get("params") or [])
    )
    gold_keys = {(c.get("name"), json.dumps(c.get("arguments") or {}, sort_keys=True, ensure_ascii=False))
                 for c in gold_calls}
    row["extra_reads"] = sum(
        1 for c in tool_calls
        if c.get("name", "").split(".")[-1].startswith(("get", "list", "search", "read", "status", "check"))
        and (c.get("name"), json.dumps(c.get("arguments") or {}, sort_keys=True, ensure_ascii=False)) not in gold_keys
    )
    apps = sorted({c.get("name", "").split(".")[0] for c in tool_calls if c.get("name")})
    row["apps"] = apps
    row["error"] = M.classify_error(gold_calls, tool_calls, debug, fuzzy_params, exception=error)
    row["exception"] = error
    return row


def tune_scope(items, ids, catalog, llm, log_path):
    """Quét lưới ngưỡng scope trên `ids` (tín hiệu từ vựng, không cần gọi LLM)."""
    feats = {}
    for sample_id in ids:
        item = items.get(sample_id)
        if item is None:
            continue
        transcript = item.get("audio_text") or (item.get("label") or {}).get("audio_text") or ""
        installed = (item.get("context") or {}).get("installed_apps") or {}
        tools = catalog.tools_for(installed)
        f = bm25_scope_features(transcript, tools, catalog.all_tools())
        group = M.sample_group(item)
        feats[sample_id] = (f, group)

    results = []
    for ratio in [round(0.1 * i, 1) for i in range(2, 10)]:
        for coverage in [round(0.1 * i, 1) for i in range(0, 7)]:
            tp = fp = fn = 0
            act_ok = 0
            act_n = 0
            for sample_id, (f, group) in feats.items():
                out_of_scope = (f["ratio"] < ratio) or (f["coverage"] < coverage)
                gold_refuse = group == "refuse"
                if gold_refuse and out_of_scope:
                    tp += 1
                elif gold_refuse and not out_of_scope:
                    fn += 1
                elif not gold_refuse and out_of_scope:
                    fp += 1
                else:
                    act_ok += 1
                if group in ("act", "ask"):
                    act_n += 1
            precision = tp / (tp + fp) if (tp + fp) else 0.0
            recall = tp / (tp + fn) if (tp + fn) else 0.0
            f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
            results.append({
                "ratio_threshold": ratio,
                "coverage_threshold": coverage,
                "refuse_f1": f1,
                "refuse_precision": precision,
                "refuse_recall": recall,
                "act_ask_recall": (act_ok / act_n) if act_n else 0.0,
            })
    best = None
    for row in results:
        if row["act_ask_recall"] < 0.99:
            continue
        if best is None or row["refuse_f1"] > best["refuse_f1"]:
            best = row
    payload = {"results": results, "best": best, "n_ids": len(feats)}
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def main(argv=None):
    args = parse_args(argv)
    overrides = config.apply_overrides(args.set)
    split = args.split
    config.SPLIT_DEFAULT = split

    items = load_items(split)
    ids = load_ids(args.ids) or list(items.keys())
    if args.limit:
        ids = ids[:args.limit]
    catalog = Catalog(str(config.catalog_path(split)))
    fuzzy_params = M.fuzzy_params_from_catalog(catalog)

    # đường dẫn tương đối ⇒ tính theo thư mục gốc dự án (nơi có runs/, debug/, reports/)
    out_dir = Path(args.out) if args.out else (config.runs_dir() / "run")
    if not out_dir.is_absolute():
        out_dir = (config.REPO_ROOT / out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    llm = LLM(config.LLM_BASE_URL, config.LLM_API_KEY, config.LLM_MODEL,
              extra_body=config.LLM_EXTRA_BODY, temperature=config.LLM_TEMPERATURE,
              timeout=config.LLM_TIMEOUT, max_retries=config.LLM_MAX_RETRIES)
    ref_sources = load_json_file(config.reports_dir() / "ref_sources.json", {}) or {}
    gold_hash = load_json_file(config.cache_dir() / "gold_hash.json", {}) or {}
    fewshot_index = build_fewshot_index(items, split)
    agent = build_agent(catalog, llm, ref_sources, fewshot_index=fewshot_index)

    if args.tune_scope:
        payload = tune_scope(items, ids, catalog, llm, config.reports_dir() / "scope_tune.json")
        print(json.dumps(payload["best"], ensure_ascii=False, indent=2))
        return 0

    EnvCls = load_toolenv_class(split, config.DATA_ROOT)
    rows = []
    per_sample_path = out_dir / "per_sample.jsonl"
    submission_path = out_dir / "submission.jsonl"
    errors = []
    started = time.time()

    with open(per_sample_path, "w", encoding="utf-8") as f_per, \
            open(submission_path, "w", encoding="utf-8") as f_sub:
        for sample_id in ids:
            item = items.get(sample_id)
            if item is None:
                continue
            env = None
            try:
                env = EnvCls(split, sample_id, root=config.DATA_ROOT)   # đúng 1 ToolEnv cho mỗi mẫu
            except Exception as e:  # noqa: BLE001
                errors.append({"id": sample_id, "error": f"env: {type(e).__name__}: {e}"})
            if env is None:
                continue
            deadline = Deadline(config.SAMPLE_DEADLINE_S)
            tool_calls, state_hash, debug, error, log = run_one(item, env, agent, deadline)
            row = make_row(item, tool_calls, state_hash, gold_hash.get(sample_id), debug, error,
                           fuzzy_params)
            row["elapsed_s"] = round(time.time() - started, 2)
            rows.append(row)
            f_per.write(json.dumps(row, ensure_ascii=False) + "\n")
            f_sub.write(json.dumps({"id": sample_id, "tool_calls": tool_calls,
                                    "state_hash": state_hash}, ensure_ascii=False) + "\n")
            if args.debug:
                write_debug({"id": sample_id, **(debug or {}), "log": log})

    summary = M.summarize(rows)
    summary["elapsed_s"] = round(time.time() - started, 2)
    summary["split"] = split
    summary["n_requested"] = len(ids)
    (out_dir / "metrics.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                           encoding="utf-8")
    (out_dir / "errors.json").write_text(json.dumps(
        {"counts": summary.get("errors", {}), "samples": [r for r in rows if r.get("error")]},
        ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "overrides.json").write_text(json.dumps(overrides, ensure_ascii=False, indent=2),
                                            encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("n", "f1_call_fuzzy-aware", "f1_call_strict",
                                               "f1_call_soft", "hash_match", "ask_accuracy")
                      if k in summary}, ensure_ascii=False, indent=2))
    print(f"→ {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
