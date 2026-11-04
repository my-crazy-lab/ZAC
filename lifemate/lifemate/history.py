"""Lịch sử hội thoại (EXECUTION-PLAN.md §8.7).

Định dạng thật của train: mỗi lượt là dict `{"role": "user"|"assistant", ...}`.
Lượt `user` có `audio` + `audio_text`; lượt `assistant` có `text`, `tool_calls`, `tool_results`.
"""
HIST_ROLE_KEYS = ("role", "speaker", "from")
HIST_TEXT_KEYS = ("text", "audio_text", "content")
HIST_AUDIO_KEYS = ("audio", "audio_path")
HIST_MAX_TURNS = 6


def _first_key(turn: dict, keys):
    for key in keys:
        if key in turn and turn[key] not in (None, ""):
            return turn[key]
    return None


def history_turns(item) -> list:
    """[{role, text, audio, raw}] — không đọc file audio (MVP không có STT)."""
    out = []
    history = (item or {}).get("history") or []
    if not isinstance(history, list):
        return out
    for turn in history:
        if not isinstance(turn, dict):
            continue
        role = _first_key(turn, HIST_ROLE_KEYS)
        role = str(role).lower() if role else "user"
        if role not in ("user", "assistant"):
            role = "assistant" if role in ("bot", "ai", "system") else "user"
        text = _first_key(turn, HIST_TEXT_KEYS)
        audio = _first_key(turn, HIST_AUDIO_KEYS)
        out.append({
            "role": role,
            "text": text if isinstance(text, str) else None,
            "audio": audio if isinstance(audio, str) else None,
            "raw": turn,
        })
    return out


def format_history(turns, user_texts=None) -> str:
    """Mỗi lượt một dòng; giữ tối đa `HIST_MAX_TURNS` lượt gần nhất."""
    lines = []
    for turn in turns or []:
        role = turn.get("role")
        raw = turn.get("raw") or {}
        if role == "user":
            text = turn.get("text")
            if not text:
                continue
            lines.append(f"Người dùng: {text}")
        else:
            calls = raw.get("tool_calls") or []
            ask = None
            for call in calls:
                if isinstance(call, dict) and call.get("name") == "sys.ask_missing_info":
                    args = call.get("arguments") or {}
                    ask = (args.get("tool_name"), args.get("params") or [])
            if ask:
                lines.append(f"Trợ lý hỏi: {ask[0]} thiếu {', '.join(ask[1])}")
            text = turn.get("text")
            if text:
                lines.append(f"Trợ lý: {text}")
    if not lines:
        return ""
    return "\n".join(lines[-HIST_MAX_TURNS:])
