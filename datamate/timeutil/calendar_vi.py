"""Đọc lịch âm – dương (M2).

Lịch được **tra cứu**, không tự tính thiên văn. File ``calendar.csv`` có cột:
``date, weekday, lunar_day, lunar_month, lunar_year, lunar_leap, holiday``.
"""

from __future__ import annotations

import csv
import logging
import os
from dataclasses import dataclass, field
from datetime import date
from typing import Any

log = logging.getLogger(__name__)


@dataclass
class Calendar:
    rows: list[dict[str, Any]] = field(default_factory=list)
    by_date: dict[str, dict[str, Any]] = field(default_factory=dict)
    lunar_index: dict[tuple[int, int, int], date] = field(default_factory=dict)

    def date_of(self, d: date) -> dict[str, Any] | None:
        return self.by_date.get(d.isoformat())

    def lunar_of(self, d: date) -> tuple[int, int, int] | None:
        row = self.by_date.get(d.isoformat())
        if not row:
            return None
        return (int(row["lunar_year"]), int(row["lunar_month"]), int(row["lunar_day"]))


def _as_bool(v: str) -> bool:
    return str(v).strip().lower() in ("true", "1", "yes", "co")


def load_calendar(path: str) -> Calendar:
    """Đọc calendar.csv (adapter theo cột thật)."""
    cal = Calendar()
    if not os.path.exists(path):
        log.warning("không thấy calendar: %s", path)
        return cal
    with open(path, encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for raw in reader:
            try:
                d = date.fromisoformat(str(raw["date"])[:10])
            except (KeyError, ValueError):
                continue
            row = {
                "date": d,
                "weekday": raw.get("weekday", ""),
                "lunar_day": int(float(raw.get("lunar_day") or 0)),
                "lunar_month": int(float(raw.get("lunar_month") or 0)),
                "lunar_year": int(float(raw.get("lunar_year") or 0)),
                "lunar_leap": _as_bool(raw.get("lunar_leap", "false")),
                "holiday": raw.get("holiday", ""),
            }
            cal.rows.append(row)
            cal.by_date[d.isoformat()] = row
            key = (row["lunar_year"], row["lunar_month"], row["lunar_day"])
            # ưu tiên ngày không nhuận
            if not row["lunar_leap"] or key not in cal.lunar_index:
                cal.lunar_index[key] = d
    return cal


def lunar_to_solar(cal: Calendar, year: int, month: int, day: int,
                   leap: bool = False) -> date | None:
    """Tra bảng âm → dương; thiếu ngày ⇒ ``None``."""
    if cal is None:
        return None
    d = cal.lunar_index.get((int(year), int(month), int(day)))
    if d is None and leap:
        # thử ngày nhuận (tháng âm nhuận có cùng số tháng)
        for (ly, lm, ld), sd in cal.lunar_index.items():
            if ly == int(year) and lm == int(month) and ld == int(day):
                d = sd
                break
    return d


def _last_day_of_lunar_month(cal: Calendar, year: int, month: int) -> date | None:
    best: date | None = None
    for (ly, lm, ld), sd in cal.lunar_index.items():
        if ly == int(year) and lm == int(month):
            if best is None or sd > best:
                best = sd
    return best


def tet_window(cal: Calendar, tet_year: int, knobs: Any) -> tuple[date, date] | None:
    """Cửa sổ Tết của năm âm lịch ``tet_year`` (theo knob)."""
    if cal is None:
        return None
    start_cfg = getattr(knobs, "tet_start", ("lunar", 12, 23, -1))
    end_cfg = getattr(knobs, "tet_end", ("lunar", 1, 10, 0))

    def _resolve(cfg: tuple, year: int) -> date | None:
        kind = cfg[0]
        month = int(cfg[1])
        day = int(cfg[2])
        offset = int(cfg[3]) if len(cfg) > 3 else 0
        if kind == "lunar":
            lyear = year + offset
            d = lunar_to_solar(cal, lyear, month, day)
            if d is None:
                d = _last_day_of_lunar_month(cal, lyear, month)
            return d
        return None

    start = _resolve(start_cfg, tet_year)
    end = _resolve(end_cfg, tet_year)
    if start is None or end is None:
        return None
    if end < start:
        return None
    return start, end


def recent_tet(cal: Calendar, as_of: date, knobs: Any) -> tuple[date, date] | None:
    """Cửa sổ Tết gần nhất có ``start <= as_of``."""
    if cal is None:
        return None
    years = sorted({ly for (ly, _lm, _ld) in cal.lunar_index}, reverse=True)
    for ly in years[:40]:
        w = tet_window(cal, ly, knobs)
        if w and w[0] <= as_of:
            return w
    return None
