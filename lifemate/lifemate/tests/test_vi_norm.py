"""Test `vi_norm.py` — phần văn bản (M1) và số/giờ (M2).

Bảng test 8.11 phải pass 100%.
"""
from datetime import datetime, timedelta, timezone

import pytest

from lifemate.vi_norm import (
    normalize,
    parse_numbers,
    parse_times,
    strip_accents,
    strip_tone,
    token_sim,
)

NOW = datetime(2026, 11, 16, 17, 0, 0, tzinfo=timezone(timedelta(hours=7)))


# ---------------------------------------------------------------- văn bản


def test_normalize_keeps_tones_and_numbers():
    out = normalize("Chuyển 1.500.000 cho Thư!")
    assert "1.500.000" in out
    assert "chuyển" in out and "thư" in out
    assert "!" not in out


def test_strip_tone():
    assert strip_tone("Hương") == "Hương"
    assert strip_tone("hướng") == "hương"


def test_strip_accents():
    assert strip_accents("Hương") == "huong"
    assert strip_accents("Đà Nẵng") == "da nang"


def test_token_sim_tiers():
    assert token_sim("hướng", "hương") == (0.92, 2)
    assert token_sim("thư", "thu") == (0.88, 3)
    score, tier = token_sim("hùng", "hưng")
    assert tier <= 5 and score < 0.88
    assert token_sim("lan", "nan") == (0.85, 4)
    assert token_sim("thư", "thư") == (1.0, 1)


# ---------------------------------------------------------------- số


NUMBER_CASES = [
    ("năm trăm nghìn", 500000),
    ("500 nghìn", 500000),
    ("500k", 500000),
    ("hai triệu rưỡi", 2500000),
    ("một triệu rưỡi", 1500000),
    ("hai nghìn rưỡi", 2500),
    ("ba mươi lăm nghìn", 35000),
    ("một tỷ hai", 1200000000),
    ("một triệu hai trăm", 1200000),
    ("một trăm lẻ năm", 105),
    ("hai mươi mốt", 21),
    ("mười lăm", 15),
    ("năm chục nghìn", 50000),
    ("1,5 triệu", 1500000),
]


@pytest.mark.parametrize("text,expected", NUMBER_CASES)
def test_parse_numbers_table(text, expected):
    hints = parse_numbers(text)
    assert hints, f"không ra số cho {text!r}"
    assert hints[0].kind == "number"
    assert hints[0].value == expected, f"{text!r} -> {hints[0].value}"


def test_parse_numbers_digits_sequence():
    hints = parse_numbers("không chín bảy không một chín năm bảy tám ba chín")
    assert len(hints) == 1
    assert hints[0].kind == "digits"
    assert hints[0].value == "09701957839"


def test_parse_numbers_excludes_time_context():
    assert parse_numbers("nhắc tôi họp lúc ba giờ chiều mai") == []
    assert parse_numbers("hai tiếng nữa") == []


# ---------------------------------------------------------------- giờ


TIME_CASES = [
    ("nhắc tôi họp lúc ba giờ chiều mai", "2026-11-17T15:00:00+07:00"),
    ("năm giờ rưỡi sáng mai", "2026-11-17T05:30:00+07:00"),
    ("họp thứ sáu tuần sau lúc 9 giờ sáng", "2026-11-27T09:00:00+07:00"),
    ("thứ sáu lúc 8 giờ tối", "2026-11-20T20:00:00+07:00"),
    ("hai tiếng nữa", "2026-11-16T19:00:00+07:00"),
    ("ba mươi phút nữa", "2026-11-16T17:30:00+07:00"),
    ("tám giờ tối nay", "2026-11-16T20:00:00+07:00"),
    ("bảy giờ kém mười lăm sáng mai", "2026-11-17T06:45:00+07:00"),
    ("bảy giờ kém mười lăm chiều mai", "2026-11-17T18:45:00+07:00"),
    ("mười lăm giờ", "2026-11-17T15:00:00+07:00"),
    ("ngày 20 tháng 12 lúc 10 giờ", "2026-12-20T10:00:00+07:00"),
]


@pytest.mark.parametrize("text,expected", TIME_CASES)
def test_parse_times_table(text, expected):
    hints = parse_times(text, NOW)
    assert hints, f"không ra giờ cho {text!r}"
    assert hints[0].kind == "time"
    assert hints[0].value == expected, f"{text!r} -> {hints[0].value}"


def test_parse_times_ambiguous_hour():
    hints = parse_times("ngày 20 tháng 12 lúc 10 giờ", NOW)
    assert hints[0].conf == pytest.approx(0.6)
    assert "2026-12-20T22:00:00+07:00" in hints[0].extra["alternatives"]


def test_parse_times_date_only():
    hints = parse_times("ngày mốt", NOW)
    assert hints[0].value == "2026-11-18"
