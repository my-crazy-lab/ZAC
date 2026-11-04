"""LifeMate — harness thực thi (text → tool calls → state → metrics).

Bản MVP: dùng MiniMax qua API OpenAI-compatible, **không có STT**
(transcript lấy thẳng từ `label.audio_text` của split train).

Lưu ý đặt tên: dataclass dùng chung nằm ở `datatypes.py` (không phải `types.py`)
vì `types.py` sẽ che mất module `types` của thư viện chuẩn khi thư mục package
nằm trong `sys.path` (hỏng `python -m pytest` khi chạy từ thư mục này).
"""
