"""Tính gold hash + kiểm tra replay (EXECUTION-PLAN.md §8.0.3).

Sinh: `cache/gold_hash.json` (1545 mẫu).
"""
import json
import random

from _bootstrap import ROOT, SPLIT  # noqa: F401

from lifemate import config
from lifemate.envloader import load_toolenv_class


def main():
    items = []
    with open(config.samples_path(SPLIT), encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    EnvCls = load_toolenv_class(SPLIT, config.DATA_ROOT)

    gold_hash = {}
    replay_mismatch = []
    for item in items:
        env = EnvCls(SPLIT, item["id"], root=config.DATA_ROOT)
        calls = ((item.get("label") or {}).get("tool_calls")) or []
        for call in calls:
            if call.get("name") == "sys.ask_missing_info":
                continue
            env.call(call.get("name", ""), call.get("arguments") or {})
        gold_hash[item["id"]] = env.get_state_hash()
        final_state = (item.get("label") or {}).get("final_state")
        if final_state:
            state = env.get_state()
            for app, expected in final_state.items():
                if state.get(app) != expected:
                    replay_mismatch.append({"id": item["id"], "app": app})
                    break

    # hash khởi tạo phải giống nhau giữa các lần tạo ToolEnv
    random.seed(13)
    sample_ids = random.sample([it["id"] for it in items], min(60, len(items)))
    init_mismatch = []
    for sample_id in sample_ids:
        env_a = EnvCls(SPLIT, sample_id, root=config.DATA_ROOT)
        env_b = EnvCls(SPLIT, sample_id, root=config.DATA_ROOT)
        if env_a.get_state_hash() != env_b.get_state_hash():
            init_mismatch.append(sample_id)

    out = config.cache_dir() / "gold_hash.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(gold_hash, ensure_ascii=False, indent=0), encoding="utf-8")

    print(json.dumps({
        "n": len(gold_hash),
        "replay_mismatch": len(replay_mismatch),
        "init_hash_mismatch": len(init_mismatch),
        "examples": replay_mismatch[:5],
        "->": str(out),
    }, ensure_ascii=False, indent=2))
    if replay_mismatch or init_mismatch:
        raise SystemExit("gold_hash: có mẫu không khớp — xem báo cáo ở trên")


if __name__ == "__main__":
    main()
