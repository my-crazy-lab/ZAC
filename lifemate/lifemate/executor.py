"""Executor: validate → call, vòng lặp B2 (EXECUTION-PLAN.md §8.16)."""
import json

from lifemate import config
from lifemate.gate import gate
from lifemate.planner import plan
from lifemate.datatypes import Call

SILENT_NUDGE = ("Yêu cầu nằm trong phạm vi các công cụ. Hãy gọi công cụ phù hợp, "
                "hoặc gọi sys.ask_missing_info nếu thiếu thông tin.")


class ExecState:
    """Trạng thái của một mẫu trong vòng lặp B2."""

    def __init__(self):
        self.nudges_used = 0
        self.writes_done = 0
        self.executed = []      # [(name, args_key)]


def safe_call(env, name, args, log=None) -> dict:
    """Gọi tool; lỗi không ném ra ngoài."""
    try:
        result = env.call(name, args or {})
    except Exception as e:  # noqa: BLE001
        if log is not None:
            log.append({"call_error": f"{name}: {type(e).__name__}: {e}"})
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    if not isinstance(result, dict):
        result = {"ok": True, "result": result}
    return result


def _args_key(args) -> str:
    return json.dumps(args or {}, sort_keys=True, ensure_ascii=False)


def _has_repeat_marker(transcript: str) -> bool:
    if not transcript:
        return False
    low = transcript.lower()
    return any(marker in low for marker in config.REPEAT_MARKERS)


def _execute_calls(env, tools, calls, store, state, deadline, log, turn):
    """Thực thi một loạt call; trả (calls đã thực thi, [(call, result)])."""
    executed_calls = []
    results = []
    for call in calls or []:
        if deadline is not None and deadline.expired():
            break
        tool = tools.get(call["name"])
        kind = tool.kind if tool is not None else "write"
        if kind == "write":
            if state.writes_done >= config.MAX_WRITES:
                if log is not None:
                    log.append({"turn": turn, "stop": "max_writes"})
                break
            state.writes_done += 1
        result = safe_call(env, call["name"], call["arguments"], log)
        store.ingest(call["name"], call["arguments"], result)
        state.executed.append((call["name"], _args_key(call["arguments"])))
        executed_calls.append(call)
        results.append((call, result))
    return executed_calls, results


def run_plan(env, llm, tools, messages, store, ctx, transcript, hints_fn, deadline, log=None,
             state=None, ref_sources=None) -> ExecState:
    """Vòng lặp B2: PLAN → GATE → EXECUTE."""
    state = state or ExecState()
    silent_retries = 0
    for turn in range(1, config.MAX_TURNS + 1):
        if deadline is not None and deadline.expired():
            break
        calls, text, amsg = plan(llm, tools, messages, log)
        if log is not None:
            log.append({"turn": turn, "planner_text": text,
                        "planner_calls": [{"name": c.name, "args": c.args} for c in calls]})

        # 2) im lặng ở lượt 1 ⇒ nhắc một lần
        if (not calls and "KHONG_HO_TRO" not in (text or "") and "XONG" not in (text or "")
                and turn == 1 and silent_retries < config.SILENT_RETRY):
            silent_retries += 1
            messages = list(messages) + [{"role": "user", "content": SILENT_NUDGE}]
            continue

        hints = hints_fn() if hints_fn else []
        res = gate(calls, text, ctx, tools, store, hints, env, state, transcript,
                   ref_sources=ref_sources)
        if log is not None:
            log.append({"turn": turn, "gate_notes": res.notes,
                        "gate_calls": res.calls, "ask": res.ask.__dict__ if res.ask else None})

        # 4) gate từ chối ⇒ dừng
        if res.refuse:
            break

        # 5) lượt ≥ 2: bỏ lệnh ghi trùng y hệt đã thực thi
        if turn >= 2 and state.executed:
            keep = []
            for call in res.calls:
                tool = tools.get(call["name"])
                key = (call["name"], _args_key(call["arguments"]))
                if (tool is not None and tool.kind == "write" and key in state.executed
                        and not _has_repeat_marker(transcript)):
                    continue
                keep.append(call)
            res.calls = keep

        # 6) thực thi
        executed_calls, results = _execute_calls(env, tools, res.calls, store, state, deadline, log, turn)

        # 7) cập nhật messages
        if executed_calls:
            tool_calls = []
            tool_messages = []
            for call, result in results:
                tool_calls.append({
                    "id": call.get("call_id") or f"call_{len(tool_calls) + 1}",
                    "type": "function",
                    "function": {
                        "name": call["name"],
                        "arguments": json.dumps(call["arguments"], ensure_ascii=False),
                    },
                })
                tool_messages.append({
                    "role": "tool",
                    "tool_call_id": call.get("call_id") or f"call_{len(tool_messages) + 1}",
                    "content": json.dumps(result, ensure_ascii=False)[:3000],
                })
            messages = list(messages) + [
                {"role": "assistant", "content": text or "", "tool_calls": tool_calls},
            ] + tool_messages

        # 8) hoãn write chưa xác minh: thử lại sau khi đã đọc trong chính lượt này
        still_deferred = res.deferred
        if res.deferred:
            retry = [Call(name=d["name"], args=dict(d["args"]), call_id="") for d in res.deferred]
            res2 = gate(retry, text, ctx, tools, store, hints_fn() if hints_fn else [], env, state,
                        transcript, ref_sources=ref_sources)
            still_deferred = res2.deferred
            if res2.calls:
                more_calls, more_results = _execute_calls(env, tools, res2.calls, store, state,
                                                          deadline, log, turn)
                executed_calls.extend(more_calls)
                results.extend(more_results)
            if log is not None:
                log.append({"turn": turn, "deferred_retry_calls": res2.calls,
                            "deferred_still": still_deferred})
        if still_deferred:
            state.nudges_used += 1
            detail = ", ".join(f"{param} của {tool_name} ({coll})" for tool_name, param, coll in res.needs_read)
            messages = list(messages) + [{
                "role": "user",
                "content": ("Các giá trị ID sau chưa được xác minh vì chưa đọc dữ liệu: "
                            f"{detail}. Hãy gọi công cụ đọc phù hợp để lấy ID rồi mới gọi lại công cụ ghi."),
            }]
            continue

        # 9) ask ⇒ thực thi sau các call của lượt này rồi kết thúc
        if res.ask is not None:
            ask_args = {"tool_name": res.ask.tool_name, "params": list(res.ask.params)}
            result = safe_call(env, "sys.ask_missing_info", ask_args, log)
            store.ingest("sys.ask_missing_info", ask_args, result)
            state.executed.append(("sys.ask_missing_info", _args_key(ask_args)))
            break

        # 10) không thực thi gì ⇒ dừng
        if not executed_calls:
            break

        # 11) XONG ⇒ dừng
        if "XONG" in (text or ""):
            break

    return state
