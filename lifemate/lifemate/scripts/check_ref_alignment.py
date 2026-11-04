"""Kiểm tra x-ref có khớp collection không (EXECUTION-PLAN.md §8.0.5.7).

Sinh: `reports/ref_alignment.json` + kết luận `XREF_MODE`.
"""
import json
from collections import Counter

from _bootstrap import ROOT, SPLIT  # noqa: F401

from lifemate import config
from lifemate.catalog import Catalog, readers_for
from lifemate.envloader import load_toolenv_class
from lifemate.state_store import StateStore


def main():
    items = []
    with open(config.samples_path(SPLIT), encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    catalog = Catalog(str(config.catalog_path(SPLIT)))
    all_tools = catalog.all_tools()
    EnvCls = load_toolenv_class(SPLIT, config.DATA_ROOT)

    stats = Counter()
    misses = []
    for item in items:
        calls = ((item.get("label") or {}).get("tool_calls")) or []
        results = ((item.get("label") or {}).get("tool_results")) or []
        ctx = (item.get("context") or {}).get("installed_apps") or {}
        tools = catalog.tools_for(ctx)
        store = StateStore()
        for idx, call in enumerate(calls):
            tool = all_tools.get(call.get("name"))
            if tool is not None and tool.kind == "write":
                for pname, pspec in (tool.props or {}).items():
                    if not isinstance(pspec, dict) or "x-ref" not in pspec:
                        continue
                    coll = str(pspec["x-ref"]).split(".")[-1]
                    value = (call.get("arguments") or {}).get(pname)
                    if value is None:
                        continue
                    stats["total"] += 1
                    read_before = coll in store.collections_read
                    hit = value in store.ids.get(coll, set())
                    if hit:
                        stats["hit_preceding"] += 1
                    else:
                        stats["miss"] += 1
                        if read_before:
                            stats["miss_but_collection_read"] += 1
                            misses.append({
                                "id": item["id"], "tool": call.get("name"), "param": pname,
                                "coll": coll, "value": value,
                                "ids_known": sorted(store.ids.get(coll, set()))[:10],
                            })
                    if read_before:
                        stats["with_collection_read"] += 1
                        if hit:
                            stats["hit_when_read"] += 1
            if idx < len(results):
                store.ingest(call.get("name", ""), call.get("arguments") or {}, results[idx])

    total = stats["total"] or 1
    ratio_preceding = stats["hit_preceding"] / total
    ratio_when_read = (stats["hit_when_read"] / stats["with_collection_read"]) if stats["with_collection_read"] else None

    # ID có lấy được bằng cách đọc collection không? (đọc thật qua ToolEnv)
    readable = Counter()
    for item in items[:400]:
        calls = ((item.get("label") or {}).get("tool_calls")) or []
        ctx = (item.get("context") or {}).get("installed_apps") or {}
        tools = catalog.tools_for(ctx)
        env = EnvCls(SPLIT, item["id"], root=config.DATA_ROOT)
        for call in calls:
            tool = all_tools.get(call.get("name"))
            if tool is None or tool.kind != "write":
                continue
            for pname, pspec in (tool.props or {}).items():
                if not isinstance(pspec, dict) or "x-ref" not in pspec:
                    continue
                coll = str(pspec["x-ref"]).split(".")[-1]
                value = (call.get("arguments") or {}).get(pname)
                if value is None:
                    continue
                readers = readers_for(coll, tools, None)
                found = False
                for reader in readers:
                    res = env.call(reader.name, {})
                    store = StateStore()
                    store.ingest(reader.name, {}, res)
                    if value in store.ids.get(coll, set()) or value in store.ids.get("*", set()):
                        found = True
                        break
                readable["total"] += 1
                readable["readable" if found else "not_readable"] += 1

    payload = {
        "total_xref_in_gold_writes": stats["total"],
        "hit_after_preceding_results": stats["hit_preceding"],
        "ratio_preceding": round(ratio_preceding, 4),
        "writes_with_collection_read_before": stats["with_collection_read"],
        "ratio_when_collection_read": (round(ratio_when_read, 4) if ratio_when_read is not None else None),
        "miss_but_collection_read": stats["miss_but_collection_read"],
        "readable_probe": dict(readable),
        "suggested_xref_mode": "lenient" if ratio_preceding < 0.95 else "strict",
        "examples_missing_even_when_read": misses[:20],
    }
    out = config.reports_dir() / "ref_alignment.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
