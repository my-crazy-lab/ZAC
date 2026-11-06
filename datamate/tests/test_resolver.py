"""Test cho M2: time resolver (bảng cụm trong EXECUTION-MVP.md §M2)."""

from __future__ import annotations

from datetime import date

from dtypes import Knobs
from timeutil.calendar_vi import load_calendar
from timeutil.resolver import resolve_time

AS_OF = date(2026, 3, 4)
KNOBS = Knobs()
CAL = load_calendar("train/calendar.csv")


def _resolve(text: str):
    windows, unresolved = resolve_time(text, AS_OF, KNOBS, CAL)
    return windows


def test_tuan_roi_full_week():
    w = _resolve("tuan roi")
    assert (w[0].start, w[0].end) == (date(2026, 2, 23), date(2026, 3, 1))


def test_thang_nay_month_to_date():
    w = _resolve("thang nay")
    assert (w[0].start, w[0].end) == (date(2026, 3, 1), date(2026, 3, 4))


def test_thang_truoc_full_month():
    w = _resolve("thang truoc")
    assert (w[0].start, w[0].end) == (date(2026, 2, 1), date(2026, 2, 28))


def test_multi_month_list_keeps_every_month():
    w = _resolve("doanh thu 3 thang 4/2026, 5/2026, 6/2026 co tang lien tuc khong")
    months = {(x.start.year, x.start.month) for x in w}
    assert {(2026, 4), (2026, 5), (2026, 6)} <= months


def test_multi_month_list_with_repeated_year():
    w = _resolve("thang 1/2026, thang 2/2026 va thang 3/2026 ghi lan luot")
    months = {(x.start.year, x.start.month) for x in w}
    assert {(2026, 1), (2026, 2), (2026, 3)} <= months


def test_three_month_count_is_not_single_month():
    # "3 thang 4/2026" (ba tháng, bắt đầu tháng 4) không được hiểu là chỉ tháng 4
    w = _resolve("3 thang 4/2026")
    assert len(w) == 1 and w[0].start.month == 4


def test_shift_uses_period_not_month_to_date():
    w = _resolve("ca chieu tuan truoc")
    assert len(w) == 1 and w[0].kind == "shift" and w[0].shift == "chieu"
    assert (w[0].start, w[0].end) == (date(2026, 2, 23), date(2026, 3, 1))


def test_two_shifts_share_same_period():
    w = _resolve("tuan truoc ca chieu so voi ca sang")
    assert len(w) == 2
    assert {(x.start, x.end) for x in w} == {(date(2026, 2, 23), date(2026, 3, 1))}
    assert {x.shift for x in w} == {"chieu", "sang"}


def test_thang_nay_vs_thang_truoc_truncates():
    w = _resolve("thang nay so voi thang truoc")
    base = [x for x in w if x.label == "base"][0]
    assert (base.start, base.end) == (date(2026, 2, 1), date(2026, 2, 4))
    assert base.trunc_same_days is True


def test_7_days_includes_today():
    w = _resolve("7 ngay qua")
    assert (w[0].start, w[0].end) == (date(2026, 2, 26), date(2026, 3, 4))


def test_yoy_shifts_one_year():
    w = _resolve("thang nay so voi cung ky nam ngoai")
    yoy = [x for x in w if x.label == "yoy"][0]
    assert (yoy.start, yoy.end) == (date(2025, 3, 1), date(2025, 3, 4))


def test_shift_ca_chieu():
    w = _resolve("ca chieu")
    assert w[0].kind == "shift" and w[0].shift == "chieu"


def test_cumulative():
    w = _resolve("tinh den het ngay 2026-03-01")
    assert w[0].kind == "cumulative" and w[0].end == date(2026, 3, 1)


def test_multiple_months():
    w = _resolve("thang 1/2026, 2/2026 va 3/2026")
    labels = [x.label for x in w]
    assert "main" in labels and "p2" in labels and "p3" in labels
    p2 = [x for x in w if x.label == "p2"][0]
    assert (p2.start, p2.end) == (date(2026, 2, 1), date(2026, 2, 28))


def test_explicit_month_year():
    w = _resolve("thang 6 nam 2025")
    assert (w[0].start, w[0].end) == (date(2025, 6, 1), date(2025, 6, 30))


def test_explicit_day():
    w = _resolve("ngay 25/09/2025")
    assert (w[0].start, w[0].end) == (date(2025, 9, 25), date(2025, 9, 25))


def test_quarter():
    w = _resolve("quy 4/2025")
    assert (w[0].start, w[0].end) == (date(2025, 10, 1), date(2025, 12, 31))
