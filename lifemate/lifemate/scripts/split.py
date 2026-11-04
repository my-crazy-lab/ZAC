"""Chia tập tune/heldout/dev300 (EXECUTION-PLAN.md §8.0.4).

Seed 13, tune 75% / heldout 25%, phân tầng theo nhóm act/ask/refuse.
`dev300` rút từ `tune` (phân tầng), dùng cho ablation nhanh.
"""
import json
import random
from collections import defaultdict

from _bootstrap import ROOT, SPLIT  # noqa: F401

from lifemate import config

SEED = 13
TUNE_RATIO = 0.75
DEV_N = 300


def group_of(item) -> str:
    calls = (item.get("label") or {}).get("tool_calls") or []
    if not calls:
        return "refuse"
    if any(c.get("name") == "sys.ask_missing_info" for c in calls):
        return "ask"
    return "act"


def main():
    items = []
    with open(config.samples_path(SPLIT), encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    rng = random.Random(SEED)

    by_group = defaultdict(list)
    for item in items:
        by_group[group_of(item)].append(item["id"])
    for group in by_group:
        by_group[group].sort()
        rng.shuffle(by_group[group])

    tune, heldout = [], []
    for group, ids in sorted(by_group.items()):
        cut = int(round(len(ids) * TUNE_RATIO))
        tune.extend(ids[:cut])
        heldout.extend(ids[cut:])
    tune.sort()
    heldout.sort()

    # dev300 rút từ tune, phân tầng theo nhóm
    tune_groups = defaultdict(list)
    group_by_id = {}
    for item in items:
        group_by_id[item["id"]] = group_of(item)
    for sample_id in tune:
        tune_groups[group_by_id[sample_id]].append(sample_id)
    dev = []
    total = len(tune)
    for group, ids in sorted(tune_groups.items()):
        take = int(round(DEV_N * len(ids) / total))
        dev.extend(ids[:take])
    # bù cho tới đúng DEV_N
    rest = [i for i in tune if i not in set(dev)]
    rng.shuffle(rest)
    while len(dev) < DEV_N and rest:
        dev.append(rest.pop())
    dev = sorted(dev[:DEV_N])

    root = config.REPO_ROOT
    for name, ids in (("tune_ids.txt", tune), ("heldout_ids.txt", heldout), ("dev300_ids.txt", dev)):
        (root / name).write_text("\n".join(ids) + "\n", encoding="utf-8")

    summary = {
        "seed": SEED,
        "n_total": len(items),
        "n_tune": len(tune),
        "n_heldout": len(heldout),
        "n_dev300": len(dev),
        "by_group_tune": {g: len(v) for g, v in tune_groups.items()},
        "by_group_heldout": {
            g: sum(1 for i in heldout if group_by_id[i] == g)
            for g in sorted(by_group)
        },
        "by_group_dev300": {
            g: sum(1 for i in dev if group_by_id[i] == g)
            for g in sorted(by_group)
        },
    }
    out = config.reports_dir() / "split.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
