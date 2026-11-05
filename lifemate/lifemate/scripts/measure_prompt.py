"""Đo kích thước prompt thật bằng tokenizer của server (M5, giới hạn 16K).

Với mỗi mẫu: dựng messages như agent (transcript vàng) + tools JSON theo
installed_apps, đếm token từng phần qua POST /tokenize. Chạy ở cả 2 chế độ
prefetch để thấy chi phí snapshot.
"""
import argparse
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lifemate import config  # noqa: E402
from lifemate.catalog import Catalog, to_llm_tools  # noqa: E402
from lifemate.datatypes import Hyp  # noqa: E402
from lifemate.envloader import load_toolenv_class  # noqa: E402
from lifemate.history import history_turns  # noqa: E402
from lifemate.prefetch import run_prefetch, select_prefetch_tools  # noqa: E402
from lifemate.prompt import build_messages  # noqa: E402
from lifemate.resolver import build_hints  # noqa: E402
from lifemate.state_store import StateStore  # noqa: E402

BASE = "http://100.109.54.207:5011"


def count_tokens(text: str) -> int:
    req = urllib.request.Request(
        BASE + "/tokenize", data=json.dumps({"content": text or ""}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return len(json.load(resp)["tokens"])


def parse_args(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--ids", required=True)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--mode", default="off", help="prefetch off|deps")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    from lifemate.eval import run as R
    config.SPLIT_DEFAULT = "train"
    items = R.load_items("train")
    ids = R.load_ids(args.ids)
    if args.limit:
        ids = ids[:args.limit]
    catalog = Catalog(str(config.catalog_path("train")))
    EnvCls = load_toolenv_class("train", config.DATA_ROOT)
    rows = []
    for i, sid in enumerate(ids):
        item = items[sid]
        try:
            from lifemate.agent import transcript_of, history_user_texts, _now_of
            installed = (item.get("context") or {}).get("installed_apps") or {}
            tools = catalog.tools_for(installed)
            transcript = transcript_of(item)
            hyps = [Hyp(text=transcript, score=1.0)]
            env = EnvCls("train", sid, root=config.DATA_ROOT)
            store = StateStore()
            pt = select_prefetch_tools(tools, transcript, {}, args.mode, config.PREFETCH_MAX_READS)
            if pt:
                run_prefetch(env, store, pt, [])
            hints = build_hints(hyps, store, _now_of(item))
            messages = build_messages(item, hyps, history_user_texts(item), hints, store,
                                      tools=tools, transcript=transcript)
            tools_json = json.dumps(to_llm_tools(tools), ensure_ascii=False)
            n_sys = count_tokens(messages[0]["content"])
            n_user = count_tokens(messages[1]["content"])
            n_tools = count_tokens(tools_json)
            rows.append({"id": sid, "sys": n_sys, "user": n_user, "tools": n_tools,
                         "total": n_sys + n_user + n_tools,
                         "n_tools": len(tools), "prefetch": len(pt)})
        except Exception as e:  # noqa: BLE001
            rows.append({"id": sid, "error": f"{type(e).__name__}: {e}"})
        if (i + 1) % 50 == 0:
            print(f"... {i + 1}/{len(ids)}", flush=True)
    ok = [r for r in rows if "error" not in r]
    totals = sorted(r["total"] for r in ok)
    import statistics
    summary = {
        "n": len(ok), "errors": len(rows) - len(ok), "mode": args.mode,
        "max": max(totals), "p95": totals[int(len(totals) * 0.95) - 1],
        "median": int(statistics.median(totals)),
        "over_16k": sum(1 for t in totals if t > 16384),
        "over_8k": sum(1 for t in totals if t > 8192),
        "worst": sorted(ok, key=lambda r: -r["total"])[:5],
    }
    print(json.dumps({k: v for k, v in summary.items() if k != "worst"},
                     ensure_ascii=False, indent=1))
    Path(f"/tmp/prompt_sizes_{args.mode}.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
