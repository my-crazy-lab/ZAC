"""Khảo sát dữ liệu train (EXECUTION-PLAN.md §8.0.1).

Sinh: `reports/inspect.json`, `reports/history_format.md`.
"""
import json
from collections import Counter

from _bootstrap import ROOT, SPLIT  # noqa: F401

from lifemate import config
from lifemate.catalog import Catalog
from lifemate.envloader import load_toolenv_class

SPLIT_DIR = config.split_dir(SPLIT)


def main():
    items = []
    with open(config.samples_path(SPLIT), encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))

    report = {"split": SPLIT, "n_samples": len(items)}

    # 1) khoá của một record
    sample = items[0]
    report["record_keys"] = sorted(sample.keys())
    report["context_keys"] = sorted((sample.get("context") or {}).keys())
    report["label_keys"] = sorted((sample.get("label") or {}).keys())
    installed = (sample.get("context") or {}).get("installed_apps") or {}
    report["installed_apps_example"] = {
        "n_apps": len(installed),
        "shape": {app: list(spec.keys()) for app, spec in list(installed.items())[:3]},
        "tools_type": type(list(installed.values())[0].get("tools")).__name__ if installed else None,
    }

    # 2) lịch sử: nguyên văn 3 mẫu + định dạng
    with_history = [it for it in items if it.get("history")]
    report["n_with_history"] = len(with_history)
    history_examples = []
    for it in with_history[:3]:
        history_examples.append({
            "id": it["id"],
            "audio_text": it.get("audio_text"),
            "history": json.dumps(it.get("history"), ensure_ascii=False, indent=2)[:2500],
        })
    report["history_examples"] = history_examples

    role_keys = Counter()
    turn_keys = Counter()
    user_keys = Counter()
    assistant_keys = Counter()
    for it in with_history:
        for turn in it.get("history") or []:
            turn_keys.update(turn.keys())
            role = str(turn.get("role", "")).lower()
            role_keys[role] += 1
            if role == "user":
                user_keys.update(turn.keys())
            else:
                assistant_keys.update(turn.keys())
    report["history_roles"] = dict(role_keys)
    report["history_turn_keys"] = dict(turn_keys)
    report["history_user_keys"] = dict(user_keys)
    report["history_assistant_keys"] = dict(assistant_keys)

    # 3) gọi tool đọc trên 5 mẫu
    EnvCls = load_toolenv_class(SPLIT, config.DATA_ROOT)
    catalog = Catalog(str(config.catalog_path(SPLIT)))
    reads_info = []
    for it in items[:5]:
        env = EnvCls(SPLIT, it["id"], root=config.DATA_ROOT)
        installed = (it.get("context") or {}).get("installed_apps") or {}
        tools = catalog.tools_for(installed)
        entry = {"id": it["id"], "tools": {}}
        for name, tool in tools.items():
            if tool.kind != "read" or tool.required:
                continue
            res = env.call(name, {})
            list_keys = [k for k, v in (res.items() if isinstance(res, dict) else []) if isinstance(v, list)]
            entry["tools"][name] = {
                "ok": (res or {}).get("ok") if isinstance(res, dict) else None,
                "list_keys": list_keys,
                "sample": json.dumps(res, ensure_ascii=False)[:1500],
            }
        reads_info.append(entry)
    report["read_tools_probe"] = reads_info

    # 4) vị trí của x-one-of / x-ref / x-match trong catalog
    one_of_param = []
    one_of_prop = []
    refs = Counter()
    fuzzy = Counter()
    for app in catalog.raw.get("apps", []):
        for tool in app.get("tools", []):
            params = tool.get("parameters") or {}
            if "x-one-of" in params:
                one_of_param.append({"tool": tool["name"], "value": params["x-one-of"]})
            for pname, pspec in (params.get("properties") or {}).items():
                if not isinstance(pspec, dict):
                    continue
                if "x-one-of" in pspec:
                    one_of_prop.append({"tool": tool["name"], "param": pname, "value": pspec["x-one-of"]})
                if "x-ref" in pspec:
                    refs[pspec["x-ref"]] += 1
                if pspec.get("x-match") == "fuzzy":
                    fuzzy[pname] += 1
    report["x_one_of_parameters"] = one_of_param
    report["x_one_of_properties"] = one_of_prop
    report["x_ref_values"] = dict(refs)
    report["x_match_fuzzy_params"] = dict(fuzzy)

    # 5) sys.ask_missing_info
    ask = catalog.all_tools().get("sys.ask_missing_info")
    report["ask_tool"] = {
        "in_catalog": ask is not None,
        "schema": ask.parameters if ask is not None else None,
        "kind": ask.kind if ask is not None else None,
    }

    # số liệu nhanh
    groups = Counter()
    for it in items:
        calls = (it.get("label") or {}).get("tool_calls") or []
        if not calls:
            groups["refuse"] += 1
        elif any(c.get("name") == "sys.ask_missing_info" for c in calls):
            groups["ask"] += 1
        else:
            groups["act"] += 1
    report["groups"] = dict(groups)

    out = config.reports_dir() / "inspect.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---- reports/history_format.md ----
    md = []
    md.append("# Định dạng `history` (train)\n")
    md.append(f"- Số mẫu có history: **{len(with_history)} / {len(items)}**")
    md.append(f"- Vai trò lượt: {dict(role_keys)}")
    md.append(f"- Khoá của lượt (tất cả): {sorted(turn_keys)}")
    md.append(f"- Khoá lượt `user`: {sorted(user_keys)}")
    md.append(f"- Khoá lượt `assistant`: {sorted(assistant_keys)}\n")
    md.append("## Kết luận (dùng làm hằng số `history.py`)\n")
    md.append("| Vai trò | Khoá vai trò | Khoá nội dung | Khoá audio | Ghi chú |")
    md.append("|---|---|---|---|---|")
    md.append("| user | `role` | `audio_text` | `audio` | lượt user trong history có `audio_text` |")
    md.append("| assistant | `role` | `text` | — | có `tool_calls` + `tool_results` |")
    md.append("\nHằng số dùng trong `history.py`:")
    md.append("```python")
    md.append('HIST_ROLE_KEYS  = ("role", "speaker", "from")')
    md.append('HIST_TEXT_KEYS  = ("text", "audio_text", "content")')
    md.append('HIST_AUDIO_KEYS = ("audio", "audio_path")')
    md.append("```\n")
    md.append("## Ví dụ nguyên văn\n")
    for ex in history_examples:
        md.append(f"### {ex['id']} (audio_text: {ex['audio_text']!r})\n")
        md.append("```json")
        md.append(ex["history"])
        md.append("```\n")
    (config.reports_dir() / "history_format.md").write_text("\n".join(md), encoding="utf-8")

    print(json.dumps({
        "n_samples": len(items),
        "groups": dict(groups),
        "n_with_history": len(with_history),
        "x_one_of_param_tools": len(one_of_param),
        "x_ref_kinds": len(refs),
        "→": str(out),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
