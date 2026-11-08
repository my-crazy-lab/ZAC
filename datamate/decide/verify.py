"""Kiểm chứng kết quả sau khi chạy template (không phải LLM viết SQL).

Verifier chỉ chặn các dạng chắc chắn sai/không dùng được: lỗi SQL, rỗng với
câu xếp hạng, NULL ở câu số, phần trăm ngoài miền, sai shape của template.
"""

from __future__ import annotations

import math
from typing import Any

from dtypes import ExecResult, Spec


def _num(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def verify_result(res: ExecResult | None, spec: Spec) -> list[str]:
    if res is None:
        return ["no_result"]
    if res.error:
        return [f"sql_error:{res.error[:200]}"]
    if not res.rows:
        # Tổng của kỳ không có dòng vẫn có nghĩa là 0; các intent khác cần dữ liệu.
        return [] if spec.intent == "aggregate_total" else ["empty_result"]
    first = res.rows[0]
    if not first:
        return ["empty_row"]

    if spec.output in ("number", "percent"):
        val = _num(first[0])
        if val is None:
            return ["null_value"]
        if spec.output == "percent" and spec.intent in ("group_share", "cancel_rate"):
            if val < -0.01 or val > 100.01:
                return [f"percent_out_of_range:{val}"]

    if spec.intent in ("rank_top", "lookup_single", "filter_list", "group_share"):
        if len(first) < 2:
            return ["shape_missing_label"]
        if spec.limit and len(res.rows) > int(spec.limit) + 1:
            return ["too_many_rows"]

    return []


__all__ = ["verify_result"]
