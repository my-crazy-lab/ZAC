"""Quy tắc chính sách dạng câu (EXECUTION-PLAN.md §8.9), bật bằng `ENABLE_POLICY_RULES`.

Đọc `reports/policy_rules.json` (sinh bởi `scripts/mine_policy.py`).
"""
import json

from lifemate import config

MAX_RULES = 6


def load_rules(path=None):
    path = path or (config.reports_dir() / "policy_rules.json")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:  # noqa: BLE001 - không có file ⇒ không có quy tắc
        return {}
    return data if isinstance(data, dict) else {}


def build_policy_text(rules: dict, installed_tools: set) -> str:
    """Sinh tối đa `MAX_RULES` câu theo mẫu §8.9."""
    lines = []
    for tool, params in (rules or {}).items():
        if tool not in (installed_tools or set()):
            continue
        for param, sources in (params or {}).items():
            if not isinstance(sources, dict):
                continue
            for source, count in sources.items():
                if count < 20:
                    continue
                total = sum(sources.values())
                if total <= 0 or count / total < 0.9:
                    continue
                if source.startswith("profile."):
                    key = source.split(".", 1)[1]
                    lines.append(f"Khi gọi {tool}, nếu người dùng không nói rõ {param}, dùng hồ sơ: {key}.")
                elif source == "current_location":
                    lines.append(f"Khi gọi {tool}, nếu người dùng không nói rõ {param}, dùng vị trí hiện tại.")
                if len(lines) >= MAX_RULES:
                    return "\n".join(lines)
                break
    return "\n".join(lines)
