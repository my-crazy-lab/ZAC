"""Agent: vòng lặp đầy đủ cho một mẫu (EXECUTION-PLAN.md §8.16).

MVP: **không có STT** — transcript lấy thẳng từ `label.audio_text` (chỉ train).
"""
import json
from datetime import datetime

from lifemate import config
from lifemate.executor import ExecState, run_plan
from lifemate.history import history_turns
from lifemate.prefetch import run_prefetch, select_prefetch_tools
from lifemate.prompt import build_messages
from lifemate.resolver import build_hints
from lifemate.scope import in_scope
from lifemate.state_store import StateStore
from lifemate.datatypes import Deadline, Hyp


def transcript_of(item) -> str:
    """Transcript của lượt hiện tại (MVP: lấy thẳng từ nhãn train)."""
    label = (item or {}).get("label") or {}
    text = label.get("audio_text")
    if not text:
        text = (item or {}).get("audio_text")
    if not text:
        raise ValueError(f"mẫu {item.get('id')!r} không có audio_text (MVP chỉ chạy được trên train)")
    return text


def history_user_texts(item) -> list:
    out = []
    for turn in history_turns(item):
        if turn.get("role") == "user" and turn.get("text"):
            out.append(turn["text"])
    return out


def _now_of(item) -> datetime:
    ctx = (item or {}).get("context") or {}
    try:
        return datetime.fromisoformat(str(ctx.get("current_time")))
    except Exception:  # noqa: BLE001
        return datetime.now()


class Agent:
    """Chạy pipeline cho một mẫu; dùng chung cho eval và infer."""

    def __init__(self, catalog, llm, ref_sources=None, fewshot_index=None, policy_rules=None):
        self.catalog = catalog
        self.llm = llm
        self.ref_sources = ref_sources or {}
        self.fewshot_index = fewshot_index
        self.policy_rules = policy_rules or {}

    def run(self, item, env, split_dir=None, deadline=None, log=None):
        """Trả dict debug; mọi lời gọi env.call nằm trong `env`."""
        log = log if log is not None else []
        ctx = (item or {}).get("context") or {}
        installed = ctx.get("installed_apps") or {}
        tools = self.catalog.tools_for(installed)
        transcript = transcript_of(item)
        hyps = [Hyp(text=transcript, score=1.0)]
        debug = {
            "id": item.get("id"),
            "hyps": [{"text": h.text, "score": h.score} for h in hyps],
            "asr_nbest": "gold",
        }

        # --- SCOPE (trước mọi env.call) ---
        ok, scope_dbg = in_scope(self.llm, hyps, tools, self.catalog.all_tools(), ctx, log)
        debug["scope"] = scope_dbg
        if not ok:
            debug["gate_notes"] = ["out_of_scope"]
            debug["executed"] = []
            debug["hints"] = []
            debug["snapshot_keys"] = []
            return debug

        store = StateStore()

        # --- PREFETCH (luôn sau scope) ---
        prefetch_tools = select_prefetch_tools(
            tools, transcript, self.ref_sources, config.PREFETCH_MODE, config.PREFETCH_MAX_READS)
        if prefetch_tools:
            run_prefetch(env, store, prefetch_tools, log)

        now = _now_of(item)
        hints_fn = lambda: build_hints(hyps, store, now)

        # --- few-shot + quy tắc chính sách ---
        fewshot_text = None
        if config.ENABLE_FEWSHOT and self.fewshot_index is not None:
            from lifemate.retrieval import format_fewshot, select_examples
            examples = select_examples(self.fewshot_index, transcript, set(tools.keys()), config.FEWSHOT_K)
            fewshot_text = format_fewshot(examples, self.catalog)
        policy_text = None
        if config.ENABLE_POLICY_RULES:
            from lifemate.policy_text import build_policy_text
            policy_text = build_policy_text(self.policy_rules, set(tools.keys()))

        messages = build_messages(
            item, hyps, history_user_texts(item), hints_fn(), store,
            fewshot_text=fewshot_text, policy_text=policy_text, tools=tools, transcript=transcript,
        )

        # --- vòng B2 ---
        state = ExecState()
        run_plan(env, self.llm, tools, messages, store, ctx, transcript, hints_fn, deadline, log,
                 state=state, ref_sources=self.ref_sources)

        debug["hints"] = [
            {"kind": h.kind, "span": h.span, "value": h.value, "conf": h.conf}
            for h in hints_fn()
        ]
        debug["snapshot_keys"] = sorted(store.snapshot.keys())
        debug["gate_notes"] = [entry.get("gate_notes") for entry in log
                               if isinstance(entry, dict) and entry.get("gate_notes")]
        debug["executed"] = [list(x) for x in state.executed]
        debug["nudges_used"] = state.nudges_used
        debug["planner_raw"] = [entry for entry in log
                                if isinstance(entry, dict) and entry.get("planner_calls") is not None]
        return debug


def write_debug(debug: dict, debug_dir=None) -> None:
    """Ghi `debug/<id>.json` (tối đa `DEBUG_MAX_BYTES`)."""
    from pathlib import Path
    directory = Path(debug_dir) if debug_dir else config.debug_dir()
    directory.mkdir(parents=True, exist_ok=True)
    sample_id = debug.get("id") or "unknown"
    path = directory / f"{sample_id}.json"
    try:
        text = json.dumps(debug, ensure_ascii=False, indent=1)
    except Exception:  # noqa: BLE001
        text = json.dumps({"id": sample_id, "error": "debug không serialize được"})
    if len(text.encode("utf-8")) > config.DEBUG_MAX_BYTES:
        text = json.dumps({"id": sample_id, "truncated": True}, ensure_ascii=False)
    path.write_text(text, encoding="utf-8")
