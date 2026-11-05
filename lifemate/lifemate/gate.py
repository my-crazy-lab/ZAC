"""Gate: kiểm tra tất định theo catalog + snapshot (EXECUTION-PLAN.md §8.15).

Đây là module quan trọng nhất: mọi kiểm tra lấy từ catalog (`required`, `enum`,
`x-ref`, `x-one-of`) và dữ liệu đã đọc — không tin lời tự khai của mô hình.
"""
import difflib

from lifemate import config
from lifemate.catalog import readers_for, resolve_tool_name
from lifemate.resolver import match_entities
from lifemate.datatypes import Ask, GateResult
from lifemate.state_store import args_key
from lifemate.vi_norm import strip_accents, tokenize_vi

EMPTY_VALUES = (None, "", [], {})

_TIME_HINTS = ("time", "giờ", "ngày", "thời gian", "at", "date")
_MONEY_HINTS = ("amount", "tiền", "giá", "price")


def _is_empty(value) -> bool:
    return value in EMPTY_VALUES or (isinstance(value, str) and not value.strip())


def sanitize_ask(args: dict, tools: dict):
    """Chuẩn hoá lời gọi `sys.ask_missing_info`; trả Ask | None."""
    if not isinstance(args, dict):
        return None
    tool_name = args.get("tool_name")
    if not isinstance(tool_name, str) or not tool_name:
        return None
    resolved = resolve_tool_name(tool_name, tools)
    if resolved is None:
        return None
    tool = tools[resolved]
    allowed = set(tool.required or [])
    for group in tool.one_of or []:
        allowed.update(group)
    params = args.get("params")
    if isinstance(params, str):
        params = [params]
    if not isinstance(params, list):
        params = []
    kept = [p for p in params if isinstance(p, str) and p in allowed]
    if not kept:
        return None
    return Ask(tool_name=resolved, params=kept)


def coerce_args(tool, raw_args: dict) -> dict:
    """Ép kiểu theo schema; tham số sai không thể sửa ⇒ bỏ."""
    props = tool.props or {}
    out = {}
    for key, value in (raw_args or {}).items():
        if key not in props:
            continue
        spec = props[key] if isinstance(props[key], dict) else {}
        v = value
        if isinstance(v, str):
            v = v.strip()
        kind = spec.get("type")
        if kind == "integer":
            if isinstance(v, bool):
                v = None
            elif isinstance(v, str):
                v = _to_int(v)
            elif isinstance(v, float):
                v = int(v) if float(v).is_integer() else None
        elif kind == "number":
            if isinstance(v, bool):
                v = None
            elif isinstance(v, str):
                try:
                    v = float(v.replace(",", "."))
                except ValueError:
                    v = None
        elif kind == "boolean":
            if isinstance(v, str):
                low = v.lower()
                if low in ("true", "1", "yes", "có"):
                    v = True
                elif low in ("false", "0", "no", "không"):
                    v = False
                else:
                    v = None
        elif kind == "string":
            if not isinstance(v, str):
                v = str(v)
        elif kind == "array":
            if isinstance(v, str):
                v = [v]
            elif not isinstance(v, list):
                v = None
        if v is None:
            continue
        enum = spec.get("enum")
        if enum:
            if v not in enum:
                fixed = None
                if isinstance(v, str):
                    for option in enum:
                        if isinstance(option, str) and option.lower() == v.lower():
                            fixed = option
                            break
                    if fixed is None:
                        candidates = [o for o in enum if isinstance(o, str)]
                        close = difflib.get_close_matches(v, candidates, n=1, cutoff=0.8)
                        fixed = close[0] if close else None
                if fixed is None:
                    continue
                v = fixed
        out[key] = v
    return out


def _to_int(value: str):
    text = value.replace(" ", "")
    try:
        return int(text)
    except ValueError:
        pass
    try:
        f = float(text)
    except ValueError:
        return None
    return int(f) if f.is_integer() else None


def _ref_collection(prop_spec: dict) -> str:
    xref = prop_spec.get("x-ref")
    if not isinstance(xref, str) or not xref:
        return ""
    return xref.split(".")[-1]


def _ref_candidates(value, coll, store, hints):
    """Ứng viên ID cho một giá trị `x-ref` chưa xác minh."""
    candidates = {}
    entities = [e for e in store.entity_list() if e.collection == coll]
    if entities and isinstance(value, str):
        for hint in match_entities(tokenize_vi(value), entities, config.ENTITY_MATCH_THRESHOLD):
            candidates[hint.value] = max(candidates.get(hint.value, 0.0), hint.conf)
    for hint in hints or []:
        if hint.kind == "entity" and hint.extra.get("collection") == coll:
            candidates[hint.value] = max(candidates.get(hint.value, 0.0), hint.conf)
    return candidates


def fix_refs(tool, args: dict, store, hints, notes: list, ref_sources=None, tools=None, state=None) -> tuple:
    """Sửa/xác minh tham số `x-ref`. Trả (args, deferred_list)."""
    deferred = []
    tools = tools or {}
    for pname, pspec in (tool.props or {}).items():
        if not isinstance(pspec, dict):
            continue
        coll = _ref_collection(pspec)
        if not coll or pname not in args:
            continue
        value = args[pname]
        known = store.ids_for(coll)
        star = store.ids.get("*", set())
        if value in known or value in star:
            continue
        if coll in store.collections_read:
            candidates = _ref_candidates(value, coll, store, hints)
            ranked = sorted(candidates.items(), key=lambda kv: -kv[1])
            if config.XREF_MODE == "strict":
                top_id, top_conf = (ranked[0] if ranked else (None, 0.0))
                second_conf = ranked[1][1] if len(ranked) > 1 else 0.0
                unambiguous = bool(ranked) and (len(ranked) == 1
                                                or (top_conf - second_conf) >= config.ENTITY_AMBIGUITY_GAP)
                if unambiguous:
                    args[pname] = top_id
                    notes.append(f"fix_ref {tool.name}.{pname}: {value!r} → {top_id}")
                else:
                    notes.append(f"drop_ref {tool.name}.{pname}: không có ứng viên duy nhất cho {value!r}")
                    del args[pname]
            else:
                if len(ranked) == 1:
                    args[pname] = ranked[0][0]
                    notes.append(f"fix_ref {tool.name}.{pname}: {value!r} → {ranked[0][0]}")
                else:
                    notes.append(f"keep_ref {tool.name}.{pname}: giữ nguyên {value!r} (lenient)")
            continue
        # collection chưa từng được đọc ⇒ giá trị chưa xác minh
        nudges_used = getattr(state, "nudges_used", 0) if state is not None else 0
        if (tool.kind == "write" and config.DEFER_UNVERIFIED_REF_WRITES
                and nudges_used < config.MAX_NUDGES
                and readers_for(coll, tools=tools, ref_sources=ref_sources)):
            deferred.append((tool.name, pname, coll, value))
            notes.append(f"defer {tool.name}.{pname}: chưa đọc collection {coll}")
            continue
    return args, deferred


def autofill_refs(tool, args: dict, store, hints, notes: list) -> dict:
    """Điền tham số `x-ref` còn thiếu khi chỉ có đúng một ứng viên tự tin."""
    if not config.ENABLE_AUTOFILL_REF:
        return args
    for pname, pspec in (tool.props or {}).items():
        if not isinstance(pspec, dict):
            continue
        coll = _ref_collection(pspec)
        if not coll or pname in args:
            continue
        if pname not in (tool.required or []) and not any(pname in g for g in tool.one_of or []):
            continue
        if coll not in store.collections_read:
            continue
        candidates = [h for h in hints or []
                      if h.kind == "entity" and h.extra.get("collection") == coll
                      and h.conf >= config.ENTITY_UNIQUE_MIN_CONF]
        unique = {h.value for h in candidates}
        if len(unique) == 1:
            args[pname] = unique.pop()
            notes.append(f"autofill {tool.name}.{pname} = {args[pname]}")
    return args


def _choose_one_of_group(tool, args, raw_args, transcript, hints):
    """Chọn nhóm `x-one-of` để hỏi theo thứ tự ưu tiên §8.15."""
    groups = tool.one_of or []
    if not groups:
        return []
    raw_args = raw_args or {}
    for group in groups:
        if any(p in raw_args for p in group):
            return group
    for group in groups:
        for p in group:
            pspec = (tool.props or {}).get(p) or {}
            coll = _ref_collection(pspec) if isinstance(pspec, dict) else ""
            if coll and any(h.kind == "entity" and h.extra.get("collection") == coll for h in hints or []):
                return group
    transcript_tokens = set(strip_accents(transcript or "").split())
    if transcript_tokens:
        for group in groups:
            for p in group:
                pspec = (tool.props or {}).get(p) or {}
                names = {strip_accents(p).lower()}
                if isinstance(pspec, dict) and pspec.get("description"):
                    names.update(strip_accents(pspec["description"]).lower().split())
                if names & transcript_tokens:
                    return group
    return groups[0]


def missing_params(tool, args: dict, raw_args=None, transcript="", hints=None) -> list:
    """Danh sách tham số còn thiếu (đã gộp cả nhóm `x-one-of`)."""
    missing = []
    for pname in tool.required or []:
        if _is_empty(args.get(pname)):
            missing.append(pname)
    if tool.one_of:
        satisfied = any(
            all(not _is_empty(args.get(k)) for k in group)
            for group in tool.one_of
        )
        if not satisfied:
            group = _choose_one_of_group(tool, args, raw_args, transcript, hints)
            if group:
                missing.append(group[0])
    return missing


def _validate(env, name, args):
    try:
        res = env.validate(name, args)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    if isinstance(res, dict):
        return res
    return {"ok": bool(res), "error": None}


def _param_from_error(error: str, tool):
    """Tham số bị validate nhắc tới (nếu có)."""
    if not isinstance(error, str) or not error:
        return None
    for pname in (tool.props or {}):
        if pname and pname in error:
            return pname
    return None


def _is_time_param(pname, pspec) -> bool:
    text = f"{pname} {(pspec or {}).get('description') or ''}".lower()
    fmt = (pspec or {}).get("format") or ""
    if "date" in fmt:
        return True
    return any(hint in text for hint in _TIME_HINTS)


def _is_money_param(pname, pspec) -> bool:
    text = f"{pname} {(pspec or {}).get('description') or ''}".lower()
    return any(hint in text for hint in _MONEY_HINTS)


def gate(raw_calls, text, ctx, tools, store, hints, env, state, transcript="", ref_sources=None) -> GateResult:
    """Kiểm tra và chuẩn hoá danh sách call của LLM."""
    notes = []
    calls = []
    deferred = []
    needs_read = []
    gate_ask = None
    model_ask = None
    seen = set()
    tools = tools or {}

    for call in raw_calls or []:
        raw_name = getattr(call, "name", "") or ""
        if raw_name.replace("__", ".").replace("/", ".") == "sys.ask_missing_info":
            name = "sys.ask_missing_info"
        else:
            name = resolve_tool_name(raw_name, tools)
        if name is None:
            notes.append(f"drop_unknown_tool: {raw_name!r}")
            continue
        if name == "sys.ask_missing_info":
            ask = sanitize_ask(getattr(call, "args", {}) or {}, tools)
            if ask is not None and model_ask is None:
                model_ask = ask
            elif ask is not None:
                notes.append("drop_extra_ask")
            continue
        tool = tools[name]
        raw_args = dict(getattr(call, "args", {}) or {})
        args = coerce_args(tool, raw_args)

        if tool.kind == "read" and config.DROP_DUPLICATE_READS:
            key = (name, args_key(args))
            if store.has_called(name, args) or key in seen:
                notes.append(f"drop_duplicate_read: {name}")
                continue
            seen.add(key)

        args, deferred_calls = fix_refs(tool, args, store, hints, notes,
                                        ref_sources=ref_sources, tools=tools, state=state)
        if deferred_calls:
            for item in deferred_calls:
                deferred.append({"name": item[0], "args": dict(args),
                                 "param": item[1], "collection": item[2]})
                needs_read.append((item[0], item[1], item[2]))
                notes.append(f"deferred_call: {item[0]} thiếu ID {item[1]} của collection {item[2]}")
            continue

        args = autofill_refs(tool, args, store, hints, notes)

        missing = missing_params(tool, args, raw_args, transcript, hints)
        if missing:
            if gate_ask is None:
                gate_ask = Ask(tool_name=name, params=missing)
                notes.append(f"ask: {name} thiếu {missing}")
            continue

        res = _validate(env, name, args)
        if not res.get("ok"):
            bad = _param_from_error(res.get("error"), tool)
            if bad and bad not in (tool.required or []):
                args.pop(bad, None)
                res = _validate(env, name, args)
            if not res.get("ok"):
                notes.append(f"drop_invalid_call: {name} ({res.get('error')})")
                continue

        calls.append({"name": name, "arguments": args,
                      "call_id": getattr(call, "call_id", ""), "_tool": tool})

    # --- khử trùng hoàn toàn trong cùng danh sách ---
    unique_calls = []
    seen_full = set()
    for call in calls:
        key = (call["name"], args_key(call["arguments"] or {}))
        if key in seen_full:
            notes.append(f"drop_duplicate_call: {call['name']}")
            continue
        seen_full.add(key)
        unique_calls.append(call)
    calls = unique_calls

    # --- ghi đè số/giờ ---
    if config.ENABLE_OVERRIDE:
        calls = _apply_override(calls, hints, notes)

    # --- ghi đè ID thực thể: hint duy nhất tin cậy cao thắng ID chưa xác minh ---
    if config.ENABLE_ENTITY_OVERRIDE:
        calls = _apply_entity_override(calls, hints, store, notes)

    # --- hỏi khi mơ hồ ---
    ask = gate_ask if gate_ask is not None else model_ask
    if config.ENABLE_AMBIG_ASK and calls:
        ambiguous = _find_ambiguous(calls, hints)
        if ambiguous:
            call, pname = ambiguous
            calls = [c for c in calls if c is not call]
            ask = Ask(tool_name=call["name"], params=[pname])
            notes.append(f"ambiguous_ask: {call['name']}.{pname}")

    for call in calls:
        call.pop("_tool", None)

    refuse = False
    if not calls and not ask and not deferred:
        refuse = True
        notes.append("silent" if "KHONG_HO_TRO" not in (text or "") else "refuse")
    elif ask and calls and not config.ASK_AFTER_PARTIAL:
        calls = []
        notes.append("ask_only (ASK_AFTER_PARTIAL=False)")

    return GateResult(calls=calls, ask=ask, refuse=refuse, notes=notes,
                      needs_read=needs_read, deferred=deferred)


def _apply_override(calls, hints, notes):
    """Ghi đè tham số thời gian / tiền bằng hint tự tin cao (ENABLE_OVERRIDE)."""
    time_hints = [h for h in hints or [] if h.kind == "time" and h.conf >= 0.9]
    number_hints = [h for h in hints or [] if h.kind == "number" and h.conf >= 0.9]
    for call in calls:
        tool = call.get("_tool")
        props = (tool.props if tool is not None else {}) or {}
        for pname, value in list((call.get("arguments") or {}).items()):
            pspec = props.get(pname) or {}
            if _is_time_param(pname, pspec) and len(time_hints) == 1:
                new_value = time_hints[0].value
                if new_value != value:
                    call["arguments"][pname] = new_value
                    notes.append(f"override_time {call['name']}.{pname} = {new_value}")
            elif _is_money_param(pname, pspec) and len(number_hints) == 1:
                new_value = number_hints[0].value
                if new_value != value:
                    call["arguments"][pname] = new_value
                    notes.append(f"override_number {call['name']}.{pname} = {new_value}")
    return calls


def _apply_entity_override(calls, hints, store, notes):
    """Hint gần như chắc chắn (bậc 1/2, đúng một ứng viên) thắng ID model chọn.

    Bậc 1 (khớp tuyệt đối) / bậc 2 (lệch mỗi dấu thanh) là bằng chứng văn bản
    mạnh: model chọn ID khác — kể cả ID có thật — gần như chắc chắn sai.
    Mơ hồ (≥2 ứng viên) thì không chạm để tránh `gate_dropped_valid`.
    """
    for call in calls or []:
        tool = call.get("_tool")
        props = (tool.props if tool is not None else {}) or {}
        for pname, value in list((call.get("arguments") or {}).items()):
            if not isinstance(value, str) or not value:
                continue
            pspec = props.get(pname) or {}
            xref = pspec.get("x-ref") if isinstance(pspec, dict) else None
            if not xref or not isinstance(xref, str) or "." not in xref:
                continue
            coll = xref.split(".")[-1]
            cands = [h for h in hints or []
                     if h.kind == "entity" and h.extra.get("collection") == coll
                     and h.extra.get("tier") in (1, 2)]
            if len(cands) == 1 and cands[0].value != value:
                call["arguments"][pname] = cands[0].value
                notes.append(f"override_entity {call['name']}.{pname} = {cands[0].value}")
    return calls


def _find_ambiguous(calls, hints):
    """Call có tham số `x-ref` mơ hồ (≥2 ứng viên gần điểm nhau)."""
    for call in calls:
        args = call.get("arguments") or {}
        for pname, value in args.items():
            coll = ""
            for hint in hints or []:
                if (hint.kind == "entity" and hint.extra.get("collection")
                        and hint.value == value):
                    coll = hint.extra.get("collection")
            if not coll:
                continue
            cands = [h for h in hints or [] if h.kind == "entity" and h.extra.get("collection") == coll]
            if len(cands) < 2:
                continue
            scores = sorted([h.conf for h in cands], reverse=True)
            if scores[0] - scores[1] < config.ENTITY_AMBIGUITY_GAP:
                return call, pname
    return None
