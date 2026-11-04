"""Khai thác quy tắc chính sách từ gold (EXECUTION-PLAN.md §8.0.6).

Sinh: `reports/policy_rules.json` — nguồn của giá trị mỗi tham số trong lệnh ghi.
"""
import json
from collections import Counter, defaultdict

from _bootstrap import ROOT, SPLIT  # noqa: F401

from lifemate import config
from lifemate.catalog import Catalog
from lifemate.vi_norm import normalize

MIN_OBS = 20
MIN_RATIO = 0.9


def source_of(value, item, results_text):
    """Nguồn của một giá trị tham số."""
    if value is None:
        return None
    ctx = item.get("context") or {}
    profile = ctx.get("user_profile") or {}
    text_value = str(value)
    norm = normalize(text_value)

    for key, val in profile.items():
        if isinstance(val, str) and val and normalize(val) == norm:
            return f"profile.{key}"
    location = ctx.get("location") or {}
    for key, val in location.items():
        if str(val) == text_value:
            return "current_location"
    current_time = ctx.get("current_time")
    if current_time and str(current_time) == text_value:
        return "current_time"
    if norm and norm in normalize(item.get("audio_text") or ""):
        return "transcript"
    if norm and norm in results_text:
        return "read_result"
    return "other"


def main():
    items = []
    with open(config.samples_path(SPLIT), encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    catalog = Catalog(str(config.catalog_path(SPLIT)))
    all_tools = catalog.all_tools()

    stats = defaultdict(lambda: defaultdict(Counter))
    for item in items:
        calls = ((item.get("label") or {}).get("tool_calls")) or []
        results = ((item.get("label") or {}).get("tool_results")) or []
        # chỉ tính kết quả của các lệnh ĐỌC trước lệnh ghi (kết quả ghi tự echo lại giá trị)
        read_texts = []
        for call in calls:
            tool = all_tools.get(call.get("name"))
            if tool is None:
                continue
            if tool.kind == "write":
                results_text = " ".join(read_texts)
                for pname, value in (call.get("arguments") or {}).items():
                    src = source_of(value, item, results_text)
                    if src:
                        stats[tool.name][pname][src] += 1
                continue
            idx = calls.index(call)
            if idx < len(results) and results[idx] is not None:
                read_texts.append(normalize(json.dumps(results[idx], ensure_ascii=False)))

    out = {}
    rules = {}
    for tool_name, params in stats.items():
        out[tool_name] = {}
        for param, counter in params.items():
            total = sum(counter.values())
            out[tool_name][param] = dict(counter)
            dominant, count = counter.most_common(1)[0]
            rule = None
            if total >= MIN_OBS and dominant == "current_location" and (count / total) >= MIN_RATIO:
                rule = {"source": dominant, "count": count, "total": total,
                        "ratio": round(count / total, 3)}
            elif total >= MIN_OBS:
                profile_counts = {k: v for k, v in counter.items() if k.startswith("profile.")}
                profile_total = sum(profile_counts.values())
                if profile_total and (profile_total / total) >= MIN_RATIO:
                    key, key_count = max(profile_counts.items(), key=lambda kv: kv[1])
                    if (key_count / profile_total) >= 0.6:   # khoá hồ sơ không mơ hồ
                        rule = {"source": key, "count": key_count, "total": total,
                                "ratio": round(profile_total / total, 3),
                                "profile_keys": profile_counts}
            if rule:
                rules.setdefault(tool_name, {})[param] = rule

    reports = config.reports_dir()
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "policy_rules.json").write_text(json.dumps(rules, ensure_ascii=False, indent=2),
                                               encoding="utf-8")
    (reports / "policy_sources.json").write_text(json.dumps(out, ensure_ascii=False, indent=2),
                                                 encoding="utf-8")
    print(json.dumps({"n_tools": len(out), "n_rules": len(rules),
                      "rules": rules}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
