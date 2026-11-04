"""Phân tích train: ask / refuse / act, nguồn tham số, ref_sources (EXECUTION-PLAN.md §8.0.5).

Sinh: `reports/policy.json`, `reports/ask_analysis.json`, `reports/ask_unexplained.json`,
`reports/refuse_analysis.json`, `reports/ref_sources.json`, `cache/entities_train.json`.
"""
import json
import re
from collections import Counter, defaultdict

from _bootstrap import ROOT, SPLIT  # noqa: F401

from lifemate import config
from lifemate.bm25 import BM25, tokenize
from lifemate.catalog import Catalog
from lifemate.state_store import StateStore
from lifemate.vi_norm import normalize, strip_accents

ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}")


def load_items():
    items = []
    with open(config.samples_path(SPLIT), encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


def group_of(item) -> str:
    calls = (item.get("label") or {}).get("tool_calls") or []
    if not calls:
        return "refuse"
    if any(c.get("name") == "sys.ask_missing_info" for c in calls):
        return "ask"
    return "act"


def main():
    items = load_items()
    catalog = Catalog(str(config.catalog_path(SPLIT)))
    all_tools = catalog.all_tools()
    reports = config.reports_dir()
    reports.mkdir(parents=True, exist_ok=True)

    groups = Counter(group_of(it) for it in items)

    # ---------------------------------------------------------------- ask
    ask_rows = []
    unexplained = []
    ask_kinds = Counter()
    for item in items:
        calls = ((item.get("label") or {}).get("tool_calls")) or []
        ask_call = next((c for c in reversed(calls) if c.get("name") == "sys.ask_missing_info"), None)
        if ask_call is None:
            continue
        args = ask_call.get("arguments") or {}
        tool_name = args.get("tool_name")
        params = list(args.get("params") or [])
        tool = all_tools.get(tool_name)
        preceding = calls[:calls.index(ask_call)]
        provided = set()
        for call in preceding:
            provided.update((call.get("arguments") or {}).keys())
        required = list(tool.required) if tool else []
        one_of = tool.one_of if tool else []
        missing_required = [p for p in required if p not in provided]
        is_required_set = set(params) == set(missing_required) and bool(params)
        one_of_group = None
        for group in one_of:
            if len(params) == 1 and params[0] in group:
                one_of_group = group
                break
        kind = "required" if is_required_set else ("one_of" if one_of_group else "unexplained")
        ask_kinds[kind] += 1
        row = {
            "id": item["id"],
            "tool_name": tool_name,
            "params": params,
            "preceding": [{"name": c.get("name"), "args": c.get("arguments")} for c in preceding],
            "required": required,
            "one_of": one_of,
            "missing_required": missing_required,
            "kind": kind,
            "transcript": item.get("audio_text"),
        }
        ask_rows.append(row)
        if kind == "unexplained":
            unexplained.append({
                "id": item["id"],
                "transcript": item.get("audio_text"),
                "tool_name": tool_name,
                "params": params,
                "required": required,
                "one_of": one_of,
                "preceding": row["preceding"],
                "tool_schema": tool.parameters if tool else None,
            })
    (reports / "ask_analysis.json").write_text(json.dumps({
        "n_ask": len(ask_rows),
        "kinds": dict(ask_kinds),
        "rows": ask_rows,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    (reports / "ask_unexplained.json").write_text(json.dumps({
        "n": len(unexplained),
        "rows": unexplained,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    # -------------------------------------------------------------- refuse
    docs = []
    tool_list = []
    for tool in all_tools.values():
        tool_list.append(tool)
        docs.append(" ".join([tool.app or "", tool.app_name_vi or "", tool.app_description or "",
                              tool.name or "", tool.description or ""]))
    index = BM25(docs)
    refuse_rows = []
    refuse_kinds = Counter()
    for item in items:
        if group_of(item) != "refuse":
            continue
        transcript = item.get("audio_text") or ""
        installed = (item.get("context") or {}).get("installed_apps") or {}
        query = [t for t in tokenize(transcript)]
        ranked = index.rank(query)
        best_tool = tool_list[ranked[0][0]] if ranked else None
        best_app = best_tool.app if best_tool else ""
        app_installed = best_app in installed
        kind = "app_not_installed" if (best_tool and not app_installed) else (
            "app_installed" if best_tool else "no_match")
        refuse_kinds[kind] += 1
        refuse_rows.append({
            "id": item["id"],
            "transcript": transcript,
            "installed_apps": sorted(installed.keys()),
            "best_tool": best_tool.name if best_tool else None,
            "best_app": best_app,
            "app_installed": app_installed,
            "kind": kind,
        })
    (reports / "refuse_analysis.json").write_text(json.dumps({
        "n_refuse": len(refuse_rows),
        "kinds": dict(refuse_kinds),
        "rows": refuse_rows,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    # ----------------------------------------------------------------- act
    write_counts = Counter()
    act_with_read = 0
    act_multi_write = 0
    read_only = 0
    for item in items:
        if group_of(item) != "act":
            continue
        calls = ((item.get("label") or {}).get("tool_calls")) or []
        writes = [c for c in calls if all_tools.get(c.get("name"), None)
                  and all_tools[c["name"]].kind == "write"]
        reads = [c for c in calls if all_tools.get(c.get("name"), None)
                 and all_tools[c["name"]].kind == "read"]
        write_counts[len(writes)] += 1
        if reads:
            act_with_read += 1
        if len(writes) > 1:
            act_multi_write += 1
        if not writes:
            read_only += 1
    n_act = groups["act"]

    # giả định "đọc không đổi hash": replay có/không lệnh đọc
    from lifemate.envloader import load_toolenv_class
    EnvCls = load_toolenv_class(SPLIT, config.DATA_ROOT)
    hash_diff = []
    checked = 0
    for item in items:
        if group_of(item) != "act":
            continue
        calls = ((item.get("label") or {}).get("tool_calls")) or []
        reads = [c for c in calls if all_tools.get(c.get("name"), None)
                 and all_tools[c["name"]].kind == "read"]
        if not reads:
            continue
        checked += 1
        if checked > 30:
            break
        env_full = EnvCls(SPLIT, item["id"], root=config.DATA_ROOT)
        for call in calls:
            if call.get("name") == "sys.ask_missing_info":
                continue
            env_full.call(call.get("name", ""), call.get("arguments") or {})
        env_no_read = EnvCls(SPLIT, item["id"], root=config.DATA_ROOT)
        for call in calls:
            if call.get("name") == "sys.ask_missing_info":
                continue
            tool = all_tools.get(call.get("name"))
            if tool is not None and tool.kind == "read":
                continue
            env_no_read.call(call.get("name", ""), call.get("arguments") or {})
        hash_diff.append(env_full.get_state_hash() == env_no_read.get_state_hash())

    # --------------------------------------------------------- ref_sources
    ref_sources = defaultdict(Counter)
    ref_alignment_total = 0
    ref_alignment_hit = 0
    for item in items:
        calls = ((item.get("label") or {}).get("tool_calls")) or []
        results = ((item.get("label") or {}).get("tool_results")) or []
        store = StateStore()
        for idx, call in enumerate(calls):
            tool = all_tools.get(call.get("name"))
            result = results[idx] if idx < len(results) else None
            if tool is not None and tool.kind == "write":
                for pname, pspec in (tool.props or {}).items():
                    if not isinstance(pspec, dict) or "x-ref" not in pspec:
                        continue
                    coll = str(pspec["x-ref"]).split(".")[-1]
                    value = (call.get("arguments") or {}).get(pname)
                    if value is None:
                        continue
                    ref_alignment_total += 1
                    if value in store.ids.get(coll, set()) or value in store.ids.get("*", set()):
                        ref_alignment_hit += 1
                    # tool đọc nào trước đó đã trả về ID đó?
                    for src_tool, src_ids in store.ids.items():
                        if src_tool == "*":
                            continue
                        if value in src_ids:
                            ref_sources[coll][src_tool] += 1
            if result is not None:
                store.ingest(call.get("name", ""), call.get("arguments") or {}, result)
    ref_sources_out = {coll: dict(counter) for coll, counter in ref_sources.items()}
    (reports / "ref_sources.json").write_text(json.dumps(ref_sources_out, ensure_ascii=False, indent=2),
                                               encoding="utf-8")

    # ------------------------------------------------------ entities cho ASR
    entities = {}
    for item in items:
        calls = ((item.get("label") or {}).get("tool_calls")) or []
        values = []
        for call in calls:
            tool = all_tools.get(call.get("name"))
            if tool is None:
                continue
            for pname, pspec in (tool.props or {}).items():
                if not isinstance(pspec, dict):
                    continue
                value = (call.get("arguments") or {}).get(pname)
                if not isinstance(value, str) or not value:
                    continue
                if pspec.get("x-ref") or pspec.get("x-match") == "fuzzy" or pname in ("title", "content",
                                                                                        "body", "subject",
                                                                                        "note", "query",
                                                                                        "label", "name"):
                    if not ISO_RE.match(value):
                        values.append(value)
        if values:
            entities[item["id"]] = values
    (config.cache_dir() / "entities_train.json").write_text(
        json.dumps(entities, ensure_ascii=False, indent=0), encoding="utf-8")

    # ----------------------------------------------------------- policy.json
    policy = {
        "n_act": n_act,
        "n_ask": groups["ask"],
        "n_refuse": groups["refuse"],
        "act_write_count_hist": dict(write_counts),
        "act_with_read_ratio": (act_with_read / n_act) if n_act else 0,
        "act_multi_write_ratio": (act_multi_write / n_act) if n_act else 0,
        "act_read_only": read_only,
        "read_does_not_change_hash": (sum(1 for x in hash_diff if x) / len(hash_diff)) if hash_diff else None,
        "read_hash_checked": len(hash_diff),
        "ask_kinds": dict(ask_kinds),
        "refuse_kinds": dict(refuse_kinds),
        "ref_alignment_ratio": (ref_alignment_hit / ref_alignment_total) if ref_alignment_total else None,
        "ref_alignment_total": ref_alignment_total,
    }
    (reports / "policy.json").write_text(json.dumps(policy, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(policy, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
