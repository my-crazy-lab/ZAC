"""Metric: F1-call, hash-match, ask accuracy, taxonomy lỗi (EXECUTION-PLAN.md §9).

Ba kiểu khớp: `strict`, `fuzzy-aware` (ưu tiên), `soft`.
"""
import json
import re
from collections import Counter

from lifemate.vi_norm import normalize

ASK_TOOL = "sys.ask_missing_info"

TIME_HINTS = ("time", "giờ", "ngày", "thời gian", "at", "date", "start", "end", "when")
NUMBER_HINTS = ("amount", "tiền", "giá", "price", "count", "số lượng", "quantity")
ENTITY_HINTS = ("query", "title", "content", "body", "subject", "note", "name", "text", "label")


# ---------------------------------------------------------------------------
# so khớp call
# ---------------------------------------------------------------------------


def _norm_value(value):
    if isinstance(value, float) and float(value).is_integer():
        return int(value)
    return value


def _args_equal(a: dict, b: dict) -> bool:
    if set(a.keys()) != set(b.keys()):
        return False
    for key in a:
        va = _norm_value(a.get(key))
        vb = _norm_value(b.get(key))
        if va != vb:
            return False
        if isinstance(va, float) and isinstance(vb, float):
            if abs(va - vb) > 1e-9:
                return False
    return True


def _token_f1(a: str, b: str) -> float:
    ta = normalize(a).split()
    tb = normalize(b).split()
    if not ta and not tb:
        return 1.0
    if not ta or not tb:
        return 0.0
    common = Counter(ta) & Counter(tb)
    same = sum(common.values())
    if same == 0:
        return 0.0
    precision = same / len(ta)
    recall = same / len(tb)
    return 2 * precision * recall / (precision + recall)


def _is_ask(call) -> bool:
    return isinstance(call, dict) and call.get("name") == ASK_TOOL


def _ask_equal(a: dict, b: dict) -> bool:
    args_a = a.get("arguments") or {}
    args_b = b.get("arguments") or {}
    if args_a.get("tool_name") != args_b.get("tool_name"):
        return False
    return set(args_a.get("params") or []) == set(args_b.get("params") or [])


def call_matches(pred: dict, gold: dict, mode: str = "fuzzy-aware", fuzzy_params=None) -> bool:
    """Hai call có khớp không (theo mode)."""
    if _is_ask(pred) or _is_ask(gold):
        return _is_ask(pred) and _is_ask(gold) and _ask_equal(pred, gold)
    if pred.get("name") != gold.get("name"):
        return False
    if mode == "soft":
        return True
    args_p = pred.get("arguments") or {}
    args_g = gold.get("arguments") or {}
    if mode == "strict":
        return _args_equal(args_p, args_g)
    # fuzzy-aware
    fuzzy = (fuzzy_params or {}).get(pred.get("name"), set())
    if set(args_p.keys()) != set(args_g.keys()):
        return False
    for key in args_p:
        vp = args_p.get(key)
        vg = args_g.get(key)
        if key in fuzzy and isinstance(vp, str) and isinstance(vg, str):
            if _token_f1(vp, vg) < 0.8 - 1e-9:
                return False
        elif not _args_equal({key: vp}, {key: vg}):
            return False
    return True


def match_calls(pred_calls, gold_calls, mode="fuzzy-aware", fuzzy_params=None) -> int:
    """Số cặp khớp (multiset)."""
    remaining = list(gold_calls or [])
    matched = 0
    for pred in pred_calls or []:
        for idx, gold in enumerate(remaining):
            if call_matches(pred, gold, mode, fuzzy_params):
                remaining.pop(idx)
                matched += 1
                break
    return matched


def f1_call(pred_calls, gold_calls, mode="fuzzy-aware", fuzzy_params=None) -> dict:
    """F1 trên multiset call."""
    n_pred = len(pred_calls or [])
    n_gold = len(gold_calls or [])
    tp = match_calls(pred_calls, gold_calls, mode, fuzzy_params)
    precision = tp / n_pred if n_pred else (1.0 if n_gold == 0 else 0.0)
    recall = tp / n_gold if n_gold else (1.0 if n_pred == 0 else 0.0)
    if n_pred == 0 and n_gold == 0:
        f1 = 1.0
    elif precision + recall == 0:
        f1 = 0.0
    else:
        f1 = 2 * precision * recall / (precision + recall)
    return {"precision": precision, "recall": recall, "f1": f1, "tp": tp,
            "n_pred": n_pred, "n_gold": n_gold}


# ---------------------------------------------------------------------------
# taxonomy lỗi
# ---------------------------------------------------------------------------


def classify_error(gold_calls, pred_calls, debug=None, fuzzy_params=None, exception=None):
    """Gán đúng một nhãn lỗi theo thứ tự ưu tiên §9.2 (None nếu đúng)."""
    if exception:
        return "exception"
    gold_calls = gold_calls or []
    pred_calls = pred_calls or []
    if not pred_calls and gold_calls:
        return "scope_false_refuse"
    if gold_calls and not pred_calls:
        return "scope_missed_refuse"
    gold_ask = any(_is_ask(c) for c in gold_calls)
    pred_ask = any(_is_ask(c) for c in pred_calls)
    if pred_ask and not gold_ask:
        return "ask_vs_act"
    if gold_ask and not pred_ask:
        return "act_vs_ask"
    if _gate_dropped_valid(debug, gold_calls):
        return "gate_dropped_valid"
    gold_names = Counter(c.get("name") for c in gold_calls)
    pred_names = Counter(c.get("name") for c in pred_calls)
    if gold_names != pred_names:
        return "wrong_tool"
    for pred in pred_calls:
        gold = _find_gold(pred, gold_calls)
        if gold is None:
            return "wrong_tool"
        diff = _classify_arg_diff(pred, gold, fuzzy_params)
        if diff:
            return diff
    return None


def _find_gold(pred, gold_calls):
    for gold in gold_calls:
        if gold.get("name") == pred.get("name"):
            if _is_ask(pred) and _is_ask(gold):
                return gold
            if _is_ask(pred) or _is_ask(gold):
                return None
            return gold
    return None


def _classify_arg_diff(pred, gold, fuzzy_params=None):
    args_p = pred.get("arguments") or {}
    args_g = gold.get("arguments") or {}
    fuzzy = (fuzzy_params or {}).get(pred.get("name"), set())
    for key in set(args_p) | set(args_g):
        vp = args_p.get(key)
        vg = args_g.get(key)
        if vp == vg:
            continue
        if _norm_value(vp) == _norm_value(vg):
            continue
        text = f"{key} {str(vg or '')}".lower()
        if key in fuzzy:
            return "wrong_arg_entity"
        if re.search(r"(amount|tiền|giá|price|quantity|số lượng)", key.lower()):
            return "wrong_arg_number"
        if re.search(r"(time|giờ|ngày|thời gian|date|start|end|when)", key.lower()):
            return "wrong_arg_time"
        if isinstance(vp, str) and isinstance(vg, str) and (ENTITY_HINTS and key.lower() in ENTITY_HINTS):
            return "wrong_arg_entity"
        if isinstance(vp, (int, float)) and isinstance(vg, (int, float)):
            return "wrong_arg_number"
        if isinstance(vp, str) and re.search(r"\d{4}-\d{2}-\d{2}", vp):
            return "wrong_arg_time"
        if key.endswith("_id") or key.startswith("id"):
            return "wrong_id"
        return "wrong_arg_other"
    return None


def _gate_dropped_valid(debug, gold_calls):
    notes = (debug or {}).get("gate_notes") or []
    flat = []
    for entry in notes:
        if isinstance(entry, list):
            flat.extend(entry)
        elif isinstance(entry, str):
            flat.append(entry)
    for note in flat:
        if not isinstance(note, str) or "drop" not in note:
            continue
        for gold in gold_calls:
            name = gold.get("name", "")
            if name and name in note:
                return True
    return False


# ---------------------------------------------------------------------------
# tổng hợp
# ---------------------------------------------------------------------------


def fuzzy_params_from_catalog(catalog) -> dict:
    """{tool_name: {param}} cho tham số `x-match: fuzzy`."""
    out = {}
    for name, tool in (catalog.all_tools() if catalog is not None else {}).items():
        params = set()
        for pname, pspec in (tool.props or {}).items():
            if isinstance(pspec, dict) and pspec.get("x-match") == "fuzzy":
                params.add(pname)
        if params:
            out[name] = params
    return out


def sample_group(item) -> str:
    calls = ((item or {}).get("label") or {}).get("tool_calls") or []
    if not calls:
        return "refuse"
    if any(_is_ask(c) for c in calls):
        return "ask"
    return "act"


def summarize(rows: list) -> dict:
    """Tổng hợp các bản ghi per-sample."""
    out = {"n": len(rows)}
    if not rows:
        return out
    groups = {}
    for row in rows:
        group = row.get("group", "act")
        groups.setdefault(group, []).append(row)
    for mode in ("strict", "fuzzy-aware", "soft"):
        values = [row.get("f1", {}).get(mode, 0.0) for row in rows]
        out[f"f1_call_{mode}"] = sum(values) / len(values)
        out[f"precision_{mode}"] = sum(row.get("f1", {}).get(f"{mode}_precision", 0.0) for row in rows) / len(rows)
        out[f"recall_{mode}"] = sum(row.get("f1", {}).get(f"{mode}_recall", 0.0) for row in rows) / len(rows)
    out["hash_match"] = sum(1 for row in rows if row.get("hash_match")) / len(rows)
    ask_rows = [r for r in rows if r.get("group") == "ask"]
    out["ask_accuracy"] = (sum(1 for r in ask_rows if r.get("ask_correct")) / len(ask_rows)) if ask_rows else 0.0
    out["n_ask"] = len(ask_rows)
    out["extra_reads"] = sum(row.get("extra_reads", 0) for row in rows) / len(rows)
    out["by_group"] = {}
    for group, group_rows in groups.items():
        out["by_group"][group] = {
            "n": len(group_rows),
            "f1_call_fuzzy-aware": sum(r.get("f1", {}).get("fuzzy-aware", 0.0) for r in group_rows) / len(group_rows),
            "f1_call_strict": sum(r.get("f1", {}).get("strict", 0.0) for r in group_rows) / len(group_rows),
            "f1_call_soft": sum(r.get("f1", {}).get("soft", 0.0) for r in group_rows) / len(group_rows),
            "hash_match": sum(1 for r in group_rows if r.get("hash_match")) / len(group_rows),
            "ask_accuracy": (sum(1 for r in group_rows if r.get("ask_correct")) / len(group_rows))
            if group_rows and group_rows[0].get("group") == "ask" else None,
        }
    out["by_app"] = {}
    app_rows = {}
    for row in rows:
        for app in row.get("apps", []):
            app_rows.setdefault(app, []).append(row)
    for app, group_rows in app_rows.items():
        out["by_app"][app] = {
            "n": len(group_rows),
            "f1_call_fuzzy-aware": sum(r.get("f1", {}).get("fuzzy-aware", 0.0) for r in group_rows) / len(group_rows),
            "hash_match": sum(1 for r in group_rows if r.get("hash_match")) / len(group_rows),
        }
    errors = Counter(row.get("error") for row in rows if row.get("error"))
    out["errors"] = dict(errors)
    return out


def load_jsonl(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows
