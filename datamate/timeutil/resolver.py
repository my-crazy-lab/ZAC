"""Time resolver: câu hỏi → ``TimeWindow`` (M2).

Nguyên tắc: **LLM không bao giờ tự tính ngày** — mọi cửa sổ thời gian do
``resolve_time`` cấp nhãn và ngày.

Xem bảng cụm trong EXECUTION-MVP.md §M2.
"""

from __future__ import annotations

import calendar as _cal
import logging
import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Callable, Iterable

from dtypes import Knobs, TimeWindow
from timeutil.calendar_vi import Calendar, recent_tet, tet_window

log = logging.getLogger(__name__)

FAR_PAST = date(1900, 1, 1)

COMPARE_RE = re.compile(r"so voi|tang |giam |bao nhieu ?%|hon bao nhieu|hay hon|ke hon|thay doi")
TIME_WORD_RE = re.compile(r"tuan|thang|quy|nam|ngay|hom|tet|ca sang|ca chieu")

YOY_RE = re.compile(r"cung ky\s+(nam ngoai|nam truoc)")
PREV_MONTH_RE = re.compile(r"cung ky\s+thang\s+(truoc|roi)")
PREV_WEEK_RE = re.compile(r"cung ky\s+tuan\s+(truoc|roi)")


# ------------------------------------------------------------------ helpers

def _month_start(d: date) -> date:
    return d.replace(day=1)


def _month_end(d: date) -> date:
    return d.replace(day=_cal.monthrange(d.year, d.month)[1])


def _add_months(d: date, n: int) -> date:
    m = d.month - 1 + n
    y = d.year + m // 12
    m = m % 12 + 1
    day = min(d.day, _cal.monthrange(y, m)[1])
    return date(y, m, day)


def _week_start(d: date, week_start: int = 0) -> date:
    return d - timedelta(days=(d.weekday() - week_start) % 7)


def _shift_year(d: date, n: int) -> date:
    try:
        return d.replace(year=d.year + n)
    except ValueError:  # 29/2 → 28/2
        return d.replace(year=d.year + n, day=28)


def _parse_day(text: str) -> date | None:
    """Parse ngày trong câu hỏi: dd/mm/yyyy, dd-mm-yyyy, yyyy-mm-dd."""
    t = text.strip()
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", t)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    m = re.search(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})", t)
    if m:
        y = int(m.group(3))
        if y < 100:
            y += 2000
        try:
            return date(y, int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
    return None


@dataclass
class Cue:
    pos: int
    end: int
    kind: str
    build: Callable[[date, Knobs, Calendar], TimeWindow | None]
    raw: str


def _overlaps(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return not (a[1] <= b[0] or a[0] >= b[1])


# ------------------------------------------------------------------- cues

def _months_from_list(text: str) -> list[tuple[int, int]]:
    months: list[tuple[int, int]] = []
    m = re.search(r"(\d{1,2})\s*thang\s+(\d{1,2}(?:\s*,\s*\d{1,2})*)\s*/\s*(\d{4})", text)
    if m:
        year = int(m.group(3))
        for part in re.split(r"\s*,\s*", m.group(2)):
            months.append((year, int(part)))
        return months
    m = re.search(r"thang\s+(\d{1,2})\s*/\s*(\d{4})((?:\s*(?:,|va|,va)\s*\d{1,2}\s*/\s*\d{4})*)", text)
    if m:
        year = int(m.group(2))
        months.append((year, int(m.group(1))))
        for mm in re.finditer(r"(\d{1,2})\s*/\s*(\d{4})", m.group(3) or ""):
            months.append((int(mm.group(2)), int(mm.group(1))))
    return months


def _c_thang_list(text: str) -> list[Cue]:
    months = _months_from_list(text)
    if len(months) < 2:
        return []
    m = re.search(r"(\d{1,2})\s*thang[^0-9]{0,4}\d{1,2}(?:\s*,\s*\d{1,2})*\s*/\s*\d{4}"
                  r"(?:\s*(?:,|va|,va)\s*\d{1,2}\s*/\s*\d{4})*", text)
    if m is None:
        m = re.search(r"thang[^0-9]{0,4}\d{1,2}\s*/\s*\d{4}"
                      r"(?:\s*(?:,|va|,va)\s*\d{1,2}\s*/\s*\d{4})*", text)
    pos, end = (m.start(), m.end()) if m else (0, 1)

    def build(_as_of: date, _knobs: Knobs, _cal: Calendar) -> TimeWindow:
        y, mo = months[0]
        return TimeWindow(label="main", start=date(y, mo, 1), end=_month_end(date(y, mo, 1)))

    return [Cue(pos=pos, end=end, kind="months", build=build, raw=text[pos:end])]


def _c_cumulative(text: str) -> list[Cue]:
    out: list[Cue] = []
    for m in re.finditer(
        r"(?:tinh )?den het ngay\s+([0-9]{1,2}[/\-.][0-9]{1,2}[/\-.][0-9]{2,4}|[0-9]{4}-[0-9]{1,2}-[0-9]{1,2})",
        text,
    ):
        day = _parse_day(m.group(1))
        if day is None:
            continue

        def build(_as_of: date, _knobs: Knobs, _cal: Calendar, _d: date = day) -> TimeWindow:
            return TimeWindow(label="main", start=FAR_PAST, end=_d, kind="cumulative")

        out.append(Cue(pos=m.start(), end=m.end(), kind="cumulative", build=build, raw=m.group(0)))
    return out


def _c_n_days(text: str) -> list[Cue]:
    out: list[Cue] = []
    for m in re.finditer(r"(\d+)\s*ngay\s*(?:qua|gan day|vua roi|truoc day)", text):
        n = int(m.group(1))

        def build(as_of: date, knobs: Knobs, _cal: Calendar, _n: int = n) -> TimeWindow:
            if getattr(knobs, "last_n_includes_today", True):
                start = as_of - timedelta(days=_n - 1)
            else:
                start = as_of - timedelta(days=_n)
            return TimeWindow(label="main", start=start, end=as_of)

        out.append(Cue(pos=m.start(), end=m.end(), kind="n_days", build=build, raw=m.group(0)))
    return out


def _c_n_weeks(text: str) -> list[Cue]:
    out: list[Cue] = []
    for m in re.finditer(r"(\d+)\s*tuan\s*(?:qua|truoc)", text):
        n = int(m.group(1))

        def build(as_of: date, knobs: Knobs, _cal: Calendar, _n: int = n) -> TimeWindow:
            ws = _week_start(as_of, knobs.week_start)
            return TimeWindow(label="main", start=ws - timedelta(weeks=_n),
                              end=ws - timedelta(days=1))

        out.append(Cue(pos=m.start(), end=m.end(), kind="n_weeks", build=build, raw=m.group(0)))
    return out


def _c_n_months(text: str) -> list[Cue]:
    out: list[Cue] = []
    for m in re.finditer(r"(\d+)\s*thang\s*(?:qua|truoc)", text):
        n = int(m.group(1))

        def build(as_of: date, _knobs: Knobs, _cal: Calendar, _n: int = n) -> TimeWindow:
            end = _month_end(_add_months(_month_start(as_of), -1))
            start = _month_start(_add_months(as_of, -_n))
            return TimeWindow(label="main", start=start, end=end)

        out.append(Cue(pos=m.start(), end=m.end(), kind="n_months", build=build, raw=m.group(0)))
    return out


def _c_tuan(text: str) -> list[Cue]:
    out: list[Cue] = []
    for m in re.finditer(r"\btuan\s+(nay|roi|truoc|vua roi)\b", text):
        kind = m.group(1)

        def build(as_of: date, knobs: Knobs, _cal: Calendar, _k: str = kind) -> TimeWindow:
            ws = _week_start(as_of, knobs.week_start)
            if _k == "nay":
                return TimeWindow(label="main", start=ws, end=as_of)
            return TimeWindow(label="main", start=ws - timedelta(days=7), end=ws - timedelta(days=1))

        out.append(Cue(pos=m.start(), end=m.end(), kind="week", build=build, raw=m.group(0)))
    return out


def _c_thang(text: str) -> list[Cue]:
    out: list[Cue] = []
    for m in re.finditer(r"\bthang\s+(nay|roi|truoc|vua roi)\b", text):
        kind = m.group(1)

        def build(as_of: date, _knobs: Knobs, _cal: Calendar, _k: str = kind) -> TimeWindow:
            if _k == "nay":
                return TimeWindow(label="main", start=_month_start(as_of), end=as_of)
            prev = _add_months(as_of, -1)
            return TimeWindow(label="main", start=_month_start(prev), end=_month_end(prev))

        out.append(Cue(pos=m.start(), end=m.end(), kind="month", build=build, raw=m.group(0)))
    return out


def _c_thang_named(text: str) -> list[Cue]:
    out: list[Cue] = []
    # "T2/2026" (viết tắt tháng) — cùng kiểu với "thang 2/2026"
    for m in re.finditer(r"\bt\s?(\d{1,2})\s*/\s*(\d{4})\b", text):
        month = int(m.group(1))
        if month < 1 or month > 12:
            continue

        def build(_as_of: date, _knobs: Knobs, _cal: Calendar,
                  _mo: int = month, _y: str = m.group(2)) -> TimeWindow:
            start = date(int(_y), _mo, 1)
            return TimeWindow(label="main", start=start, end=_month_end(start))

        out.append(Cue(pos=m.start(), end=m.end(), kind="month_named", build=build,
                       raw=m.group(0)))
    for m in re.finditer(r"\bthang\s+(\d{1,2})(?:\s*/\s*(\d{4}))?", text):
        month = int(m.group(1))
        if month < 1 or month > 12:
            continue
        year_txt = m.group(2)
        if year_txt is None:
            # "tháng 6 năm 2025" ⇒ lấy năm trong cụm ngay sau
            tail = text[m.end(): m.end() + 30]
            my = re.search(r"\bnam\s+(\d{4})", tail)
            if my:
                year_txt = my.group(1)

        def build(as_of: date, _knobs: Knobs, _cal: Calendar,
                  _mo: int = month, _y: str | None = year_txt) -> TimeWindow:
            if _y:
                year = int(_y)
            else:
                year = as_of.year if _mo <= as_of.month else as_of.year - 1
            start = date(year, _mo, 1)
            return TimeWindow(label="main", start=start, end=_month_end(start))

        out.append(Cue(pos=m.start(), end=m.end(), kind="month_named", build=build, raw=m.group(0)))
    return out


def _c_day_explicit(text: str) -> list[Cue]:
    """``ngày 25/09/2025`` ⇒ đúng một ngày."""
    out: list[Cue] = []
    for m in re.finditer(r"\bngay\s+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{1,2}-\d{1,2})", text):
        day = _parse_day(m.group(1))
        if day is None:
            continue

        def build(_as_of: date, _knobs: Knobs, _cal: Calendar, _d: date = day) -> TimeWindow:
            return TimeWindow(label="main", start=_d, end=_d)

        out.append(Cue(pos=m.start(), end=m.end(), kind="day_explicit", build=build, raw=m.group(0)))
    return out


def _c_quy_named(text: str) -> list[Cue]:
    """``quý 4/2025`` hoặc ``quý 4 năm 2025``."""
    out: list[Cue] = []
    for m in re.finditer(r"\bquy\s+(\d)(?:\s*/\s*(\d{4}))?", text):
        q = int(m.group(1))
        if q < 1 or q > 4:
            continue
        year_txt = m.group(2)
        if year_txt is None:
            tail = text[m.end(): m.end() + 30]
            my = re.search(r"\bnam\s+(\d{4})", tail)
            if my:
                year_txt = my.group(1)

        def build(as_of: date, _knobs: Knobs, _cal: Calendar,
                  _q: int = q, _y: str | None = year_txt) -> TimeWindow:
            year = int(_y) if _y else as_of.year
            start = date(year, 3 * (_q - 1) + 1, 1)
            return TimeWindow(label="main", start=start, end=_month_end(_add_months(start, 2)))

        out.append(Cue(pos=m.start(), end=m.end(), kind="quarter_named", build=build, raw=m.group(0)))
    return out


def _c_quy(text: str) -> list[Cue]:
    out: list[Cue] = []
    for m in re.finditer(r"\bquy\s+(nay|roi|truoc)\b", text):
        kind = m.group(1)

        def build(as_of: date, _knobs: Knobs, _cal: Calendar, _k: str = kind) -> TimeWindow:
            q = (as_of.month - 1) // 3 + 1
            if _k == "nay":
                start = date(as_of.year, 3 * (q - 1) + 1, 1)
                return TimeWindow(label="main", start=start, end=as_of)
            prev_q = q - 1
            year = as_of.year
            if prev_q == 0:
                prev_q = 4
                year -= 1
            start = date(year, 3 * (prev_q - 1) + 1, 1)
            end = _month_end(_add_months(start, 2))
            return TimeWindow(label="main", start=start, end=end)

        out.append(Cue(pos=m.start(), end=m.end(), kind="quarter", build=build, raw=m.group(0)))
    return out


def _c_nam(text: str) -> list[Cue]:
    out: list[Cue] = []
    for m in re.finditer(r"\bnam\s+(nay|ngoai|roi|truoc)\b", text):
        kind = m.group(1)

        def build(as_of: date, _knobs: Knobs, _cal: Calendar, _k: str = kind) -> TimeWindow:
            if _k == "nay":
                return TimeWindow(label="main", start=date(as_of.year, 1, 1), end=as_of)
            year = as_of.year - 1
            return TimeWindow(label="main", start=date(year, 1, 1), end=date(year, 12, 31))

        out.append(Cue(pos=m.start(), end=m.end(), kind="year", build=build, raw=m.group(0)))
    return out


def _c_tet(text: str) -> list[Cue]:
    out: list[Cue] = []
    for m in re.finditer(r"\btet(?:\s+(nam ngoai|nam truoc|nay|vua roi|gan nhat))?\b", text):
        mode = (m.group(1) or "").strip()

        def build(as_of: date, knobs: Knobs, cal: Calendar, _m: str = mode) -> TimeWindow | None:
            if _m in ("nam ngoai", "nam truoc"):
                w = tet_window(cal, as_of.year - 1, knobs)
            else:
                w = recent_tet(cal, as_of, knobs)
            if not w:
                return None
            return TimeWindow(label="main", start=w[0], end=w[1])

        out.append(Cue(pos=m.start(), end=m.end(), kind="tet", build=build, raw=m.group(0)))
    return out


def _c_ca(text: str) -> list[Cue]:
    out: list[Cue] = []
    for m in re.finditer(r"\bca\s+(sang|chieu)\b", text):
        shift = m.group(1)

        def build(as_of: date, _knobs: Knobs, _cal: Calendar, _s: str = shift) -> TimeWindow:
            return TimeWindow(label="main", start=_month_start(as_of), end=as_of,
                              kind="shift", shift=_s)

        out.append(Cue(pos=m.start(), end=m.end(), kind="shift", build=build, raw=m.group(0)))
    return out


def _c_thu(text: str) -> list[Cue]:
    out: list[Cue] = []
    for m in re.finditer(r"\bthu\s+(2|3|4|5|6|7|cn)\s+(tuan roi|tuan nay)\b", text):
        wd = {"2": 0, "3": 1, "4": 2, "5": 3, "6": 4, "7": 5, "cn": 6}[m.group(1)]
        week_kind = m.group(2)

        def build(as_of: date, knobs: Knobs, _cal: Calendar,
                  _wd: int = wd, _wk: str = week_kind) -> TimeWindow:
            ws = _week_start(as_of, knobs.week_start)
            if _wk == "tuan roi":
                ws = ws - timedelta(days=7)
            delta = (_wd - ws.weekday()) % 7
            day = ws + timedelta(days=delta)
            return TimeWindow(label="main", start=day, end=day)

        out.append(Cue(pos=m.start(), end=m.end(), kind="weekday", build=build, raw=m.group(0)))
    return out


def _c_hom(text: str) -> list[Cue]:
    out: list[Cue] = []
    for m in re.finditer(r"\bhom\s+(nay|qua)\b", text):
        kind = m.group(1)

        def build(as_of: date, _knobs: Knobs, _cal: Calendar, _k: str = kind) -> TimeWindow:
            if _k == "nay":
                return TimeWindow(label="main", start=as_of, end=as_of)
            d = as_of - timedelta(days=1)
            return TimeWindow(label="main", start=d, end=d)

        out.append(Cue(pos=m.start(), end=m.end(), kind="day", build=build, raw=m.group(0)))
    return out


# Thứ tự quét: cụm dài/đặc thù trước
_CUE_BUILDERS: list[Callable[[str], list[Cue]]] = [
    _c_thang_list,
    _c_day_explicit,
    _c_quy_named,
    _c_cumulative,
    _c_n_days,
    _c_n_weeks,
    _c_n_months,
    _c_tuan,
    _c_thu,
    _c_thang,
    _c_thang_named,
    _c_quy,
    _c_nam,
    _c_tet,
    _c_ca,
    _c_hom,
]


def _scan(text: str) -> list[Cue]:
    """Quét các cụm thời gian; loại cue chồng nhau (giữ span dài nhất)."""
    modifier_spans = [m.span() for m in YOY_RE.finditer(text)]
    modifier_spans += [m.span() for m in PREV_MONTH_RE.finditer(text)]
    modifier_spans += [m.span() for m in PREV_WEEK_RE.finditer(text)]

    cues: list[Cue] = []
    for fn in _CUE_BUILDERS:
        for c in fn(text):
            if any(_overlaps((c.pos, c.end), sp) for sp in modifier_spans):
                continue
            cues.append(c)
    kept: list[Cue] = []
    for c in sorted(cues, key=lambda c: (-(c.end - c.pos), c.pos)):
        if any(_overlaps((c.pos, c.end), (k.pos, k.end)) for k in kept):
            continue
        kept.append(c)
    kept.sort(key=lambda c: c.pos)
    return kept


def _truncate_base(main_w: TimeWindow, base_w: TimeWindow, as_of: date) -> TimeWindow:
    """'Tháng trước' cắt cùng số ngày khi kỳ chính kết thúc ở hôm nay."""
    if not (main_w.start == _month_start(as_of) and main_w.end == as_of):
        return base_w
    prev = _add_months(as_of, -1)
    last = _cal.monthrange(prev.year, prev.month)[1]
    end = date(prev.year, prev.month, min(as_of.day, last))
    return TimeWindow(label=base_w.label, start=_month_start(prev), end=end,
                      kind=base_w.kind, shift=base_w.shift, trunc_same_days=True)


ABS_CUE_KINDS = {"month_named", "quarter_named", "day_explicit", "months"}
REL_CUE_KINDS = {"month", "week", "year", "n_days", "n_weeks", "n_months"}


def _shift_back(win: TimeWindow, kind: str) -> TimeWindow:
    """Dịch cửa sổ lùi 1 kỳ (dùng cho "so với tháng trước")."""
    if kind == "month":
        start = _add_months(win.start, -1)
        return TimeWindow(label="base", start=start, end=_month_end(start))
    if kind == "week":
        return TimeWindow(label="base", start=win.start - timedelta(days=7),
                          end=win.end - timedelta(days=7))
    if kind == "year":
        return TimeWindow(label="base", start=_shift_year(win.start, -1),
                          end=_shift_year(win.end, -1))
    return TimeWindow(label="base", start=win.start, end=win.end)


def resolve_time(text_nd: str, as_of: date, knobs: Knobs,
                 cal: Calendar) -> tuple[list[TimeWindow], list[str]]:
    """Trả (danh sách cửa sổ có nhãn, danh sách cụm chưa giải được)."""
    text = (text_nd or "").strip()
    if not text:
        return [], []
    cues = _scan(text)
    unresolved: list[str] = []

    yoy = bool(YOY_RE.search(text))
    prev_month = bool(PREV_MONTH_RE.search(text))
    prev_week = bool(PREV_WEEK_RE.search(text))
    has_compare = bool(COMPARE_RE.search(text))

    # --- chọn main/base
    main_cue = cues[0] if cues else None
    base_cue = cues[1] if len(cues) > 1 else None
    rel_base_kind: str | None = None
    if has_compare and len(cues) >= 2:
        abs_cues = [c for c in cues if c.kind in ABS_CUE_KINDS]
        rel_cues = [c for c in cues if c.kind in REL_CUE_KINDS]
        if abs_cues and rel_cues:
            main_cue = abs_cues[0]
            base_cue = rel_cues[0]
            rel_base_kind = rel_cues[0].kind
        elif len(abs_cues) >= 2:
            main_cue, base_cue = abs_cues[0], abs_cues[1]

    main_w = main_cue.build(as_of, knobs, cal) if main_cue else None
    base_w = base_cue.build(as_of, knobs, cal) if base_cue else None

    if main_w is None and base_w is None:
        if TIME_WORD_RE.search(text):
            unresolved.append(text)
        return [], unresolved

    # --- nhiều tháng: p1..pn
    if main_cue is not None and main_cue.kind == "months":
        months = _months_from_list(text)
        if months:
            out: list[TimeWindow] = []
            for i, (y, mo) in enumerate(months):
                label = "main" if i == 0 else f"p{i+1}"
                out.append(TimeWindow(label=label, start=date(y, mo, 1),
                                      end=_month_end(date(y, mo, 1))))
            y0, m0 = months[0]
            out.append(TimeWindow(label="p1", start=date(y0, m0, 1),
                                  end=_month_end(date(y0, m0, 1))))
            return out, unresolved

    windows: list[TimeWindow] = []
    if main_w is not None:
        windows.append(main_w)

    # --- cùng kỳ năm ngoái / kỳ trước
    if main_w is not None and (yoy or prev_month or prev_week) and rel_base_kind is None:
        if yoy:
            k_w = TimeWindow(label="yoy", start=_shift_year(main_w.start, -1),
                             end=_shift_year(main_w.end, -1), kind=main_w.kind,
                             shift=main_w.shift)
        elif prev_month:
            k_w = TimeWindow(label="prev", start=_add_months(main_w.start, -1),
                             end=_add_months(main_w.end, -1), kind=main_w.kind,
                             shift=main_w.shift)
        else:
            k_w = TimeWindow(label="prev", start=main_w.start - timedelta(weeks=1),
                             end=main_w.end - timedelta(weeks=1), kind=main_w.kind,
                             shift=main_w.shift)
        windows.append(k_w)
        if base_w is None:
            base_w = k_w

    if base_w is not None:
        if rel_base_kind is not None and main_w is not None:
            base_w = _shift_back(main_w, rel_base_kind)
        base_w = TimeWindow(label="base", start=base_w.start, end=base_w.end,
                            kind=base_w.kind, shift=base_w.shift,
                            trunc_same_days=base_w.trunc_same_days)
        if (main_w is not None and base_w.kind == "period"
                and base_w.start == _month_start(_add_months(as_of, -1))
                and base_w.end == _month_end(_add_months(as_of, -1))):
            base_w = _truncate_base(main_w, base_w, as_of)
        windows.append(base_w)

    return windows, unresolved


def window_by_label(windows: Iterable[TimeWindow]) -> dict[str, TimeWindow]:
    """Tra cửa sổ theo nhãn (có fallback "main" → cửa sổ đầu)."""
    out: dict[str, TimeWindow] = {w.label: w for w in windows}
    if "main" not in out:
        wl = list(windows)
        if wl:
            out["main"] = wl[0]
    return out
