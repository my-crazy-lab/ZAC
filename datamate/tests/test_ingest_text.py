"""Test cho M1/M6: parse số, ngày, chuẩn hoá văn bản, entity linking."""

from __future__ import annotations

import pandas as pd

from ingest.clean import find_header_row, parse_date_series, parse_number_series
from text.entity_linker import EntityIndex, link_entities
from text.normalize import expand_abbrev, nd


def test_parse_number_thousands_and_decimal():
    s = pd.Series(["1.200.000", "26,000", "4000", "1.500,5", "2,5"])
    out = list(parse_number_series(s))
    assert out[0] == 1200000
    assert out[1] == 26000
    assert out[2] == 4000
    assert out[3] == 1500.5
    assert out[4] == 2.5


def test_parse_number_suffix():
    s = pd.Series(["500k", "1,2tr"])
    out = list(parse_number_series(s))
    assert out[0] == 500000
    assert out[1] == 1200000


def test_parse_date_dd_mm_yyyy():
    s = pd.Series(["25/09/2025", "01/04/2026"])
    out = list(parse_date_series(s))
    assert out[0].isoformat() == "2025-09-25"
    assert out[1].isoformat() == "2026-04-01"


def test_parse_date_vietnamese_month_name():
    s = pd.Series(["1 thg 6 2025"])
    out = list(parse_date_series(s))
    assert out[0].isoformat() == "2025-06-01"


def test_find_header_row_prefers_full_row():
    raw = pd.DataFrame([
        ["Hàng", None, "Tiền"],
        ["Hàng", "so_luong", "Tri gia"],
        ["A", 1, 2],
    ])
    assert find_header_row(raw) == 1


def test_nd_strips_diacritics():
    assert nd("Cà phê Sữa") == "ca phe sua"


def test_expand_abbrev():
    assert "doanh thu" in expand_abbrev("dthu")
    assert "hom qua" in expand_abbrev("hqua")


def test_entity_linking_prefers_full_name():
    idx = EntityIndex()
    idx.add("product", "Chà cá chiên", "cha ca chien")
    idx.add("product", "Bàn chải Colgate", "ban chai colgate")
    matches = link_entities("thang 8/2025 ban cha ca chien duoc bao nhieu tien", idx)
    assert matches and matches[0].canonical_name == "Chà cá chiên"


def test_entity_linking_ignores_business_phrases():
    idx = EntityIndex()
    idx.add("product", "Bàn chải Colgate", "ban chai colgate")
    matches = link_entities("mat hang ban chay nhat thang 6 nam 2026", idx)
    assert not matches
