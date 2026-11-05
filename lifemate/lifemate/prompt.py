"""Dựng prompt cho LLM (EXECUTION-PLAN.md §8.9).

System prompt dùng **nguyên văn** 9 quy tắc trong đặc tả.
"""
import json

from lifemate import config
from lifemate.lexicon import trim_snapshot

SYSTEM_PROMPT = """Bạn là trợ lý điều khiển ứng dụng trên thiết bị bằng giọng nói. Người dùng nói tiếng Việt.
Nhiệm vụ: biến yêu cầu thành các lời gọi công cụ đúng.
Quy tắc:
1. Chỉ dùng các công cụ được cung cấp. Không bịa tên công cụ hay tham số.
2. Mọi ID (thiết bị, liên hệ, tài khoản...) phải lấy đúng từ "Dữ liệu ứng dụng" hoặc từ kết quả công cụ đọc. Không tự đặt ID. Nếu chưa có dữ liệu để lấy ID, hãy gọi công cụ đọc phù hợp trước.
3. Số tiền, giờ, ngày: ưu tiên dùng đúng giá trị trong mục "Gợi ý". Giờ dùng định dạng ISO có múi giờ.
4. Khi người dùng nói "nhà tôi", "chỗ tôi", "văn phòng" hãy dùng hồ sơ và vị trí hiện tại.
5. Nếu thiếu thông tin bắt buộc mà không thể suy ra từ yêu cầu, hồ sơ, vị trí hay dữ liệu ứng dụng: gọi sys.ask_missing_info với tool_name là công cụ định gọi và params là danh sách tên tham số còn thiếu. Không đoán.
6. Nếu không công cụ nào xử lý được yêu cầu: không gọi công cụ nào, chỉ trả lời KHONG_HO_TRO.
7. Chỉ gọi công cụ đọc khi cần dữ liệu để thực hiện yêu cầu hoặc khi yêu cầu chính là hỏi thông tin. Không gọi lại công cụ đã gọi. Chỉ gọi công cụ ghi khi chắc chắn.
8. Với tham số văn bản tự do (nội dung, tiêu đề, ghi chú, truy vấn): dùng đúng từ khóa người dùng nói, ngắn gọn, không thêm từ.
9. Khi đã hoàn tất mọi việc người dùng yêu cầu, trả lời XONG và không gọi thêm công cụ."""

WEEKDAY_VI = ["hai", "ba", "tư", "năm", "sáu", "bảy", "chủ nhật"]


def _json(value) -> str:
    try:
        return json.dumps(value, ensure_ascii=False)
    except Exception:  # noqa: BLE001
        return str(value)


def build_messages(item, hyps, hist_texts, hints, store, fewshot_text=None, policy_text=None,
                   tools=None, transcript=None) -> list:
    """User message + system message, đúng thứ tự mục trong đặc tả."""
    ctx = (item or {}).get("context") or {}
    current_time = ctx.get("current_time", "")
    timezone = ctx.get("timezone", "")
    now = None
    try:
        from datetime import datetime
        now = datetime.fromisoformat(str(current_time))
    except Exception:  # noqa: BLE001
        now = None
    weekday_vi = WEEKDAY_VI[now.weekday()] if now is not None else ""

    parts = []
    parts.append(f"Thời gian hiện tại: {current_time} ({timezone}); thứ {weekday_vi}")
    location = ctx.get("location")
    if location:
        parts.append(f"Vị trí hiện tại: {_json(location)}")
    profile = ctx.get("user_profile")
    if profile:
        parts.append(f"Hồ sơ: {_json(profile)}")
    from lifemate.history import format_history, history_turns
    turns = history_turns(item)
    history_text = format_history(turns, hist_texts)
    if history_text:
        parts.append(f"Lịch sử:\n{history_text}")
    if policy_text:
        parts.append(f"Quy tắc bổ sung:\n{policy_text}")
    if fewshot_text:
        parts.append(f"Ví dụ tương tự:\n{fewshot_text}")
    top_text = ""
    if hyps:
        top_text = getattr(hyps[0], "text", "") or ""
    if transcript:
        top_text = transcript
    parts.append(f"Yêu cầu: {top_text}")
    alts = []
    for hyp in (hyps or [])[1:3]:
        text = getattr(hyp, "text", "") or ""
        if text and text != top_text:
            alts.append(text)
    if alts:
        parts.append("Cách nghe khác: " + " | ".join(alts))
    from lifemate.resolver import format_hints
    hint_text = format_hints(hints)
    if hint_text:
        parts.append("Dùng đúng id trong mục Gợi ý cho tên đã khớp, không tự đặt ID.\n"
                     f"Gợi ý:\n{hint_text}")
    snapshot = trim_snapshot(store, top_text, config.SNAPSHOT_MAX_CHARS)
    if snapshot and snapshot != "{}":
        parts.append(f"Dữ liệu ứng dụng:\n{snapshot}")

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "\n\n".join(parts)},
    ]
