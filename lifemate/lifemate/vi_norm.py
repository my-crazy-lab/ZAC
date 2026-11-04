"""Chuẩn hoá tiếng Việt: văn bản, số, giờ (EXECUTION-PLAN.md §8.5 và §8.11).

- Văn bản: `normalize` giữ dấu tiếng Việt, `strip_tone` bỏ dấu thanh,
  `strip_accents` bỏ toàn bộ dấu (dùng cho BM25), `token_sim` chấm theo bậc.
- Số/giờ: `parse_numbers`, `parse_times` — chạy trên **text gốc** (không dùng `normalize`).
"""
import re
import unicodedata
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher

from lifemate.datatypes import Hint

TONE_MARKS = ("\u0300", "\u0301", "\u0309", "\u0303", "\u0323")

STOPWORDS_VI = {
    "cho", "và", "là", "của", "tôi", "mình", "em", "anh", "chị", "bạn", "một", "các",
    "những", "trong", "ở", "đi", "về", "đến", "lúc", "giúp", "hộ", "nhé", "nha", "với", "thì",
    "mà",
}

# ---------------------------------------------------------------------------
# Văn bản
# ---------------------------------------------------------------------------


def normalize(text) -> str:
    """NFC, chữ thường, dấu câu → khoảng trắng (trừ . , : / giữa hai chữ số), gộp khoảng trắng.

    GIỮ dấu tiếng Việt.
    """
    if not isinstance(text, str):
        return ""
    text = unicodedata.normalize("NFC", text).lower()
    # giữ dấu phân cách số nằm giữa hai chữ số (vd "1.500.000")
    marks = {".": "\x02", ",": "\x03", ":": "\x04", "/": "\x05"}
    text = re.sub(r"(?<=\d)([.,:/])(?=\d)", lambda m: marks[m.group(0)], text)
    text = re.sub(r"[^\w\s\x02\x03\x04\x05]", " ", text, flags=re.UNICODE)
    for ch, mark in marks.items():
        text = text.replace(mark, ch)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def strip_tone(s) -> str:
    """Chỉ bỏ 5 dấu thanh; giữ ă â ê ô ơ ư đ."""
    if not isinstance(s, str):
        return ""
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if c not in TONE_MARKS)
    return unicodedata.normalize("NFC", s)


def strip_accents(s) -> str:
    """Bỏ toàn bộ dấu, đ→d, chữ thường (dùng cho BM25)."""
    if not isinstance(s, str):
        return ""
    s = unicodedata.normalize("NFD", s.lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.replace("đ", "d").replace("Đ", "d")
    return unicodedata.normalize("NFC", s)


def strip_tone_marks(s) -> str:
    """Bỏ dấu thanh nhưng giữ dấu khác (dùng cho so khớp âm)."""
    if not isinstance(s, str):
        return ""
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if c not in TONE_MARKS)
    return unicodedata.normalize("NFC", s)


def _tone_set(s: str) -> set:
    if not isinstance(s, str):
        return set()
    return {c for c in unicodedata.normalize("NFD", s) if c in TONE_MARKS}


def phonetic_key(token) -> str:
    """Khóa âm gần đúng (dùng cho bậc 4)."""
    t = strip_accents(token)
    t = re.sub(r"^(gi|d|r)", "d", t)
    t = re.sub(r"^(tr|ch)", "c", t)
    t = re.sub(r"^x", "s", t)
    t = re.sub(r"^l", "n", t)
    t = re.sub(r"(ng|nh)$", "n", t)
    t = re.sub(r"(ch|c)$", "t", t)
    return t


def token_sim(a, b) -> tuple:
    """(điểm, bậc) theo bậc 1..5 (xem EXECUTION-PLAN.md §8.5)."""
    if not isinstance(a, str) or not isinstance(b, str):
        return (0.0, 0)
    a = a.lower()
    b = b.lower()
    if a == b:
        return (1.0, 1)
    if strip_tone(a) == strip_tone(b):
        return (0.92, 2)
    # bậc 3: cùng gốc âm khi bỏ dấu, nhưng dấu thanh phải khớp nhau
    # (ví dụ "thư" vs "thu" là bậc 3; còn "hùng" vs "hưng" là khác thanh/horn ⇒ rơi xuống bậc 4)
    if strip_accents(a) == strip_accents(b) and _tone_set(a) == _tone_set(b):
        return (0.88, 3)
    if phonetic_key(a) == phonetic_key(b):
        return (0.85, 4)
    ra = strip_accents(a)
    rb = strip_accents(b)
    if len(ra) >= 4 and len(rb) >= 4:
        r = SequenceMatcher(None, ra, rb).ratio()
        if r >= 0.85:
            return (0.80 + 0.04 * (r - 0.85) / 0.15, 5)
    return (0.0, 0)


def tokenize(text) -> list:
    """Chữ thường, tách khoảng trắng."""
    if not isinstance(text, str):
        return []
    return [t for t in strip_accents(text).split() if t]


def tokenize_vi(text) -> list:
    """Chữ thường giữ dấu, tách khoảng trắng (dùng để so tên thực thể)."""
    if not isinstance(text, str):
        return []
    return [t for t in unicodedata.normalize("NFC", text).lower().split() if t]


# ---------------------------------------------------------------------------
# Số
# ---------------------------------------------------------------------------

DIGIT_WORDS = {
    "không": 0, "một": 1, "mốt": 1, "hai": 2, "ba": 3, "bốn": 4, "tư": 4, "năm": 5, "lăm": 5,
    "sáu": 6, "bảy": 7, "bẩy": 7, "tám": 8, "chín": 9,
}
MULT_10 = {"mươi", "chục"}
TEN = "mười"
HUNDRED = {"trăm"}
UNITS = {"nghìn": 1000, "ngàn": 1000, "triệu": 1000000, "tỷ": 1000000000, "tỉ": 1000000000}
IGNORED = {"lẻ", "linh"}
HALF = "rưỡi"

_UNIT_RE = re.compile(
    r"(?P<num>\d{1,3}(?:\.\d{3})+|\d+(?:[.,]\d+)?)\s*"
    r"(?P<unit>nghìn|ngàn|triệu|tỷ|tỉ|đồng|vnd|ka|tr|k|đ)\b",
    re.IGNORECASE,
)
_UNIT_FACTOR = {
    "nghìn": 1000, "ngàn": 1000, "triệu": 1000000, "tỷ": 1000000000, "tỉ": 1000000000,
    "đồng": 1, "vnd": 1, "ka": 1000, "tr": 1000000, "k": 1000, "đ": 1,
}

_TIME_AFTER = {"giờ", "phút", "tiếng", "ngày", "tháng", "tuần", "h"}
_TIME_BEFORE = {"ngày", "tháng", "lúc", "thứ"}

_WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)


def _words(text: str) -> list:
    """Danh sách (token, start, end) của các từ (chữ/số), giữ nguyên vị trí trong text."""
    out = []
    for m in _WORD_RE.finditer(text):
        out.append((m.group(0), m.start(), m.end()))
    return out


def _is_number_token(tok: str) -> bool:
    """Token có thể nằm trong một cụm số (chữ số hoặc chữ)."""
    return (
        tok == TEN
        or tok in DIGIT_WORDS
        or tok in MULT_10
        or tok in HUNDRED
        or _digit_token_value(tok) is not None
    )


def _scan_number_phrase(lows: list, k: int):
    """Cụm số bắt đầu tại vị trí k → (tokens, vị trí kế tiếp)."""
    start = k
    while k < len(lows) and _is_number_token(lows[k]):
        k += 1
    return lows[start:k], k


def _digit_token_value(tok: str):
    """Giá trị của token số: int thuần, hoặc int sau khi bỏ dấu chấm phân tách hàng nghìn.

    Trả None nếu token không phải số nguyên rõ ràng (vd "1,5")."""
    if tok.isdigit():
        return int(tok)
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", tok):
        return int(tok.replace(".", ""))
    return None


def _accumulate(tokens: list) -> float:
    """Cộng dồn một cụm số (chữ hoặc số)."""
    total = 0.0
    cur = 0.0
    pending = None
    last_unit = None
    for tok in tokens:
        if tok == TEN:
            cur += 10
            pending = None
        elif tok in MULT_10:
            cur += (pending if pending is not None else 1) * 10
            pending = None
        elif tok in DIGIT_WORDS:
            pending = DIGIT_WORDS[tok]
        elif tok in HUNDRED:
            cur += (pending if pending is not None else 1) * 100
            pending = None
        elif tok in UNITS:
            cur += pending or 0
            if cur == 0:
                cur = 1
            total += cur * UNITS[tok]
            last_unit = UNITS[tok]
            cur = 0.0
            pending = None
        elif tok in IGNORED:
            pending = None
        elif tok == HALF:
            if last_unit:
                total += last_unit / 2
        else:
            value = _digit_token_value(tok)
            if value is None:
                continue
            pending = value
    cur += pending or 0
    if last_unit:
        if cur < 10:
            total += cur * last_unit / 10
        elif cur < 1000 and cur % 100 == 0:
            total += cur * last_unit / 1000
        else:
            total += cur
    else:
        total += cur
    return total


def _number_phrase_value(tokens: list):
    """Giá trị số của cụm chỉ gồm chữ số/từ số (không đơn vị) — dùng cho giờ/phút."""
    if not tokens:
        return None
    val = 0
    cur = 0
    pending = None
    for tok in tokens:
        if tok == TEN:
            cur += 10
            pending = None
        elif tok in MULT_10:
            cur += (pending if pending is not None else 1) * 10
            pending = None
        elif tok in DIGIT_WORDS:
            pending = DIGIT_WORDS[tok]
        elif tok in HUNDRED:
            cur += (pending if pending is not None else 1) * 100
            pending = None
        else:
            value = _digit_token_value(tok)
            if value is None:
                return None
            pending = value
    cur += pending or 0
    val = cur
    return val


def parse_numbers(text: str) -> list:
    """Trích số từ text (chạy trên text gốc, KHÔNG dùng normalize)."""
    if not isinstance(text, str) or not text.strip():
        return []
    hints = []
    seen = set()

    # --- 1. regex số + đơn vị (vd "500 nghìn", "1,5 triệu", "500k") ---
    regex_spans = []
    for m in _UNIT_RE.finditer(text):
        num_raw = m.group("num")
        unit = m.group("unit").lower()
        if "." in num_raw:
            value = float(num_raw.replace(".", ""))
        elif "," in num_raw:
            value = float(num_raw.replace(",", "."))
        else:
            value = float(num_raw)
        factor = _UNIT_FACTOR.get(unit, 1)
        total = value * factor
        if abs(total - round(total)) < 1e-9:
            total = int(round(total))
        span = m.group(0).strip()
        key = (span, total)
        if key not in seen:
            seen.add(key)
            hints.append(Hint(kind="number", span=span, value=total, conf=0.95))
        regex_spans.append((m.start(), m.end()))

    # --- 2. đường chữ số ---
    words = _words(text)
    numberish = []
    for idx, (tok, s, e) in enumerate(words):
        low = tok.lower()
        if (low in DIGIT_WORDS or low in MULT_10 or low in HUNDRED or low in UNITS
                or low in IGNORED or low == HALF or low == TEN):
            numberish.append(idx)
        elif _digit_token_value(low) is not None:
            numberish.append(idx)

    spans = []
    run = []
    prev = None
    for idx in numberish:
        if prev is not None and idx == prev + 1:
            run.append(idx)
        else:
            if run:
                spans.append(run)
            run = [idx]
        prev = idx
    if run:
        spans.append(run)

    for run in spans:
        toks = [words[i][0].lower() for i in run]
        start = words[run[0]][1]
        end = words[run[-1]][2]
        # bỏ span trùng với regex số+đơn vị
        if any(not (end <= rs or start >= re_) for rs, re_ in regex_spans):
            continue
        # token trước / sau span
        before = words[run[0] - 1][0].lower() if run[0] > 0 else ""
        after = words[run[-1] + 1][0].lower() if run[-1] + 1 < len(words) else ""
        if after in _TIME_AFTER or before in _TIME_BEFORE:
            continue
        # span chỉ gồm chữ số đơn (0..9) và ≥ 6 token ⇒ chuỗi chữ số rời
        single = [t for t in toks if t in DIGIT_WORDS and DIGIT_WORDS[t] < 10]
        if len(single) == len(toks) and len(toks) >= 6:
            digits = "".join(str(DIGIT_WORDS[t]) for t in toks)
            key = (digits, digits)
            if key not in seen:
                seen.add(key)
                hints.append(Hint(kind="digits", span=" ".join(toks), value=digits, conf=0.9))
            continue
        if any(_digit_token_value(t) is None and t not in DIGIT_WORDS for t in toks):
            # token không hiểu được (vd "1,5") ⇒ đã loại bởi regex hoặc không phải số
            if any("," in t or "." in t for t in toks):
                continue
        total = _accumulate(toks)
        if total <= 0:
            continue
        if abs(total - round(total)) < 1e-9:
            total = int(round(total))
        has_unit = any(t in UNITS for t in toks) or any(t in ("k", "ka", "tr", "đ", "đồng", "vnd") for t in toks)
        conf = 0.95 if has_unit else 0.8
        span_text = text[start:end].strip()
        key = (span_text, total)
        if key not in seen:
            seen.add(key)
            hints.append(Hint(kind="number", span=span_text, value=total, conf=conf))

    hints.sort(key=lambda h: text.find(h.span) if h.span in text else 0)
    return hints


# ---------------------------------------------------------------------------
# Giờ / ngày
# ---------------------------------------------------------------------------

WEEKDAY_WORDS = {
    "hai": 0, "ba": 1, "tư": 2, "năm": 3, "sáu": 4, "bảy": 5, "chủ nhật": 6,
}
PART_OF_DAY = ("sáng", "trưa", "chiều", "tối", "đêm")
_DURATION_UNITS = {"phút": 1, "tiếng": 60, "giờ": 60, "ngày": 24 * 60}


def _fmt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S%z")[:-2] + ":" + dt.strftime("%z")[-2:]


def _fmt_offset(dt: datetime) -> str:
    off = dt.strftime("%z") or "+0000"
    return dt.strftime("%Y-%m-%dT%H:%M:%S") + off[:3] + ":" + off[3:]


def _apply_part_of_day(hour: int, word: str) -> int:
    if word == "sáng":
        return hour
    if word == "trưa":
        return hour if hour >= 10 else hour + 12
    if word in ("chiều", "tối"):
        return hour + 12 if hour < 12 else hour
    if word == "đêm":
        if 6 <= hour < 12:
            return hour + 12
        if hour == 12:
            return 0
        return hour
    return hour


def _parse_date_expr(text: str, now: datetime):
    """Tìm biểu thức ngày trong text. Trả (date, span, kind) hoặc None."""
    low = text.lower()
    patterns = [
        (r"ngày\s+mốt|ngày\s+kia|\bmốt\b", "dayafter"),
        (r"hôm\s+qua", "yesterday"),
        (r"ngày\s+mai|\bmai\b", "tomorrow"),
        (r"hôm\s+nay|\bnay\b", "today"),
    ]
    for pat, kind in patterns:
        m = re.search(pat, low)
        if m:
            base = now.date()
            if kind == "today":
                d = base
            elif kind == "tomorrow":
                d = base + timedelta(days=1)
            elif kind == "dayafter":
                d = base + timedelta(days=2)
            else:
                d = base - timedelta(days=1)
            return d, m.group(0), kind

    # thứ <hai|ba|tư|năm|sáu|bảy|chủ nhật> [tuần sau|tới|này]
    m = re.search(r"thứ\s+(hai|ba|tư|năm|sáu|bảy|chủ nhật)(\s+tuần\s+(sau|tới|này))?", low)
    if m:
        wd = WEEKDAY_WORDS[m.group(1)]
        span = m.group(0)
        week = m.group(3)
        today = now.date()
        if week == "này":
            monday = today - timedelta(days=today.weekday())
            d = monday + timedelta(days=wd)
        elif week in ("sau", "tới"):
            monday = today + timedelta(days=7 - today.weekday())
            d = monday + timedelta(days=wd)
        else:
            delta = (wd - today.weekday()) % 7
            if delta == 0:
                delta = 7
            d = today + timedelta(days=delta)
        return d, span, "weekday"

    # ngày D tháng M
    m = re.search(r"ngày\s+(\d{1,2})\s*tháng\s*(\d{1,2})", low)
    if m:
        d = _safe_date(int(m.group(2)), int(m.group(1)), now.date().year)
        if d:
            return d, m.group(0), "explicit"
    # D tháng M
    m = re.search(r"(\d{1,2})\s*tháng\s*(\d{1,2})", low)
    if m:
        d = _safe_date(int(m.group(2)), int(m.group(1)), now.date().year)
        if d:
            return d, m.group(0), "explicit"
    # D/M
    m = re.search(r"\b(\d{1,2})/(\d{1,2})\b", low)
    if m:
        d = _safe_date(int(m.group(2)), int(m.group(1)), now.date().year)
        if d:
            return d, m.group(0), "explicit"
    # ngày D
    m = re.search(r"ngày\s+(\d{1,2})\b(?!\s*tháng)", low)
    if m:
        day = int(m.group(1))
        today = now.date()
        try:
            d = date(today.year, today.month, day)
        except ValueError:
            d = None
        if d is None:
            year, month = today.year, today.month + 1
            if month > 12:
                month, year = 1, year + 1
            try:
                d = date(year, month, day)
            except ValueError:
                d = None
        if d:
            return d, m.group(0), "explicit"
    return None


def _safe_date(month: int, day: int, year: int):
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _find_time_of_day(text: str, words: list):
    """Tìm biểu thức giờ trong ngày. Trả dict hoặc None."""
    lows = [w[0].lower() for w in words]
    for i, low in enumerate(lows):
        if low != "giờ":
            continue
        # cụm số ngay trước "giờ"
        j = i - 1
        while j >= 0 and _is_number_token(lows[j]):
            j -= 1
        start = j + 1
        if start == i:
            continue
        phrase = lows[start:i]
        hour = _number_phrase_value(phrase)
        if hour is None or not (0 <= hour <= 24):
            continue
        # phần phút phía sau
        minute = 0
        end = i
        if i + 1 < len(lows) and lows[i + 1] == HALF:
            minute = 30
            end = i + 1
        elif i + 1 < len(lows) and lows[i + 1] == "kém":
            ph, nk = _scan_number_phrase(lows, i + 2)
            y = _number_phrase_value(ph)
            if y is not None:
                hour = hour - 1
                minute = 60 - y
                end = nk - 1
        else:
            ph, nk = _scan_number_phrase(lows, i + 1)
            if ph and nk < len(lows) and lows[nk] == "phút":
                minute = _number_phrase_value(ph)
                end = nk
        # từ chỉ buổi trong cửa sổ 3 token quanh biểu thức
        pod = None
        for idx in range(max(0, start - 3), min(len(lows), end + 4)):
            if lows[idx] in PART_OF_DAY:
                pod = lows[idx]
                break
        span = text[words[start][1]:words[end][2]]
        return {"hour": hour, "minute": minute, "pod": pod, "span": span}
    # dạng 15h, 15h30, 15:30
    for m in re.finditer(r"\b(\d{1,2})\s*h\s*(\d{2})?\b|\b(\d{1,2}):(\d{2})\b", text.lower()):
        if m.group(1) is not None:
            hour = int(m.group(1))
            minute = int(m.group(2)) if m.group(2) else 0
        else:
            hour = int(m.group(3))
            minute = int(m.group(4))
        if hour > 24 or minute > 59:
            continue
        return {"hour": hour, "minute": minute, "pod": None, "span": m.group(0)}
    return None


def _find_duration(text: str, words: list):
    """Tìm khoảng thời gian tương đối. Trả (minutes, span) hoặc None."""
    lows = [w[0].lower() for w in words]
    for i, low in enumerate(lows):
        if low == "sau" and i + 1 < len(lows):
            ph, nk = _scan_number_phrase(lows, i + 1)
            if ph and nk < len(lows) and lows[nk] in _DURATION_UNITS:
                value = _number_phrase_value(ph)
                if value is not None:
                    span = text[words[i][1]:words[nk][2]]
                    return value * _DURATION_UNITS[lows[nk]], span
        if low in _DURATION_UNITS and i + 1 < len(lows) and lows[i + 1] == "nữa":
            # "<số> <đơn vị> nữa"
            j = i - 1
            while j >= 0 and _is_number_token(lows[j]):
                j -= 1
            ph = lows[j + 1:i]
            if ph:
                value = _number_phrase_value(ph)
                if value is not None:
                    span = text[words[j + 1][1]:words[i + 1][2]]
                    return value * _DURATION_UNITS[low], span
    m = re.search(r"\bnửa\s+tiếng\b", text.lower())
    if m:
        return 30, m.group(0)
    # "X tiếng rưỡi"
    for i, low in enumerate(lows):
        if low == "tiếng" and i + 1 < len(lows) and lows[i + 1] == HALF and i > 0:
            j = i - 1
            while j >= 0 and _is_number_token(lows[j]):
                j -= 1
            ph = lows[j + 1:i]
            if ph:
                value = _number_phrase_value(ph)
                if value is not None:
                    span = text[words[j + 1][1]:words[i + 2][2]]
                    return value * 60 + 30, span
    return None


def parse_times(text: str, now: datetime) -> list:
    """Trích giờ/ngày. Định dạng ISO có múi giờ (luôn có giây :00)."""
    if not isinstance(text, str) or not text.strip():
        return []
    if not isinstance(now, datetime):
        now = datetime.now()
    words = _words(text)
    if not words:
        return []
    tz = now.tzinfo
    hints = []

    # 1) khoảng thời gian tương đối
    duration = _find_duration(text, words)
    if duration is not None:
        minutes, span = duration
        target = (now + timedelta(minutes=minutes)).replace(second=0, microsecond=0)
        hints.append(Hint(kind="time", span=span, value=_fmt_offset(target), conf=0.9,
                          extra={"kind": "relative", "alternatives": []}))
        return hints

    date_expr = _parse_date_expr(text, now)
    tod = _find_time_of_day(text, words)

    if tod is None:
        if date_expr is not None:
            d, span, kind = date_expr
            hints.append(Hint(kind="time", span=span, value=d.isoformat(), conf=0.9,
                              extra={"kind": "date", "alternatives": []}))
        return hints

    hour = tod["hour"]
    minute = tod["minute"]
    pod = tod["pod"]
    day = date_expr[0] if date_expr else now.date()
    span = tod["span"]

    if pod is not None:
        hour = _apply_part_of_day(hour, pod)
        candidates = [hour]
        conf = 0.9
    elif hour >= 13 or hour == 0:
        candidates = [hour]
        conf = 0.9
    else:
        candidates = [hour, hour + 12]
        conf = 0.6

    base = datetime(day.year, day.month, day.day, 0, 0, 0, tzinfo=tz)
    built = []
    for h in candidates:
        h = h % 24 if h != 24 else 0
        built.append(base.replace(hour=h, minute=minute))

    if len(built) == 1:
        chosen = built[0]
        alternatives = []
        conf_out = conf
    else:
        today = now.date()
        if day != today:
            if 1 <= candidates[0] <= 6:
                chosen = built[1]
            elif 7 <= candidates[0] <= 11:
                chosen = built[0]
            else:
                chosen = built[0] if candidates[0] == 12 else built[0]
            alternatives = [b for b in built if b != chosen]
        else:
            later = [b for b in built if b > now]
            if later:
                chosen = min(later)
            else:
                chosen = min(built) + timedelta(days=1)
            alternatives = [b for b in built if b != chosen]
        conf_out = conf

    if date_expr is None and chosen <= now:
        chosen = chosen + timedelta(days=1)
        alternatives = []

    hints.append(Hint(kind="time", span=span, value=_fmt_offset(chosen), conf=conf_out,
                      extra={"kind": "absolute",
                             "alternatives": [_fmt_offset(a) for a in alternatives]}))
    return hints
