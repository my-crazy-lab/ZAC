"""``validate_spec`` + ``compile_spec``: biên dịch Spec thành SQL (M5).

Nguyên tắc: **LLM không viết ngày, không viết logic nghiệp vụ** — chỉ điền vào
tập đóng; mọi phép tính nằm ở đây.
"""

from __future__ import annotations

import calendar as _calendar
import logging
import re as _re
from datetime import date
from dtypes import BizContext, CompiledPlan, EntityMatch, Knobs, Spec, TimeWindow
from engine import templates
from engine.registry import get
from text.normalize import nd

log = logging.getLogger(__name__)

INTENT_OUTPUTS: dict[str, set[str]] = {
    "aggregate_total": {"number", "percent"},
    "multi_value": {"list"},
    "compare_periods": {"percent", "number", "list", "string"},
    "compare_series": {"boolean", "list", "string", "date"},
    "rank_top": {"list", "string", "table", "date"},
    "lookup_single": {"string", "date", "number"},
    "filter_list": {"list", "table"},
    "boolean_check": {"boolean"},
    "point_in_time": {"number", "string", "list", "table"},
    "group_share": {"percent"},
    "cancel_rate": {"percent"},
    "other": set(),
}

PARAM_KEYS = {"compare_mode", "check", "threshold", "expiring_days", "unit_name",
              "debt_age_stat", "slow_and_high_stock", "extra_metrics",
              "multi_field", "multi_values"}

FILTER_FIELDS = {"product", "category", "customer", "channel", "pay_method",
                 "employee", "customer_group", "size", "unit_name"}
FILTER_OPS = {"=", "!=", "in"}
# Metric cộng dồn: không có dòng trong kỳ ⇒ 0, không phải NULL.
ZERO_WHEN_EMPTY = {"revenue", "qty", "profit", "import_amount", "cancelled_orders"}


def _window_map(windows: list[TimeWindow]) -> dict[str, TimeWindow]:
    out = {w.label: w for w in windows}
    if "main" not in out and windows:
        out["main"] = windows[0]
    return out


def _resolve_time_alias(label: str, windows: list[TimeWindow]) -> str | None:
    """Nhãn thô dạng YYYY-MM / YYYY-MM-DD → nhãn cửa sổ chứa kỳ đó.

    LLM hay viết nhãn tháng/ngày tự nhiên thay vì nhãn đã giải
    ("main"/"base"). Ánh xạ chứa (containment), ưu tiên khớp khít.
    """
    m = _re.fullmatch(r"(\d{4})-(\d{2})", (label or "").strip())
    if m:
        year, month = int(m.group(1)), int(m.group(2))
        if 1 <= month <= 12:
            start = date(year, month, 1)
            end = date(year, month, _calendar.monthrange(year, month)[1])
            exact = [w for w in windows if w.start == start and w.end == end]
            if exact:
                return exact[0].label
            for w in windows:
                if w.start <= start and w.end >= end:
                    return w.label
        return None
    m = _re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", (label or "").strip())
    if m:
        try:
            day = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
        for w in windows:
            if w.start <= day <= w.end:
                return w.label
    return None


_FILTER_SOURCE_COLUMNS: dict[str, tuple[str, ...]] = {
    "product": ("product_code", "product_name"),
    "category": ("category",),
    "customer": ("customer_key", "customer_name"),
    "channel": ("channel",),
    "pay_method": ("pay_method",),
    "employee": ("employee",),
    "customer_group": ("customer_group",),
    "size": ("size",),
    "unit_name": ("base_unit", "unit_name"),
}


def _source_columns(ctx: BizContext, source: str) -> set[str] | None:
    con = getattr(ctx, "con", None)
    if con is None or not source:
        return None
    try:
        return {str(r[0]) for r in con.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name=?",
            [source]).fetchall()}
    except Exception:  # noqa: BLE001
        return None


def validate_spec(spec: Spec, ctx: BizContext, windows: list[TimeWindow],
                  entities: list[EntityMatch] | None = None) -> list[str]:
    """Trả danh sách lỗi (rỗng ⇒ hợp lệ)."""
    errs: list[str] = []
    wmap = _window_map(windows)

    # 1. nhãn thời gian phải có trong danh sách (kèm ánh xạ nhãn thô)
    for i, label in enumerate(list(spec.time or [])):
        if label not in wmap:
            alias = _resolve_time_alias(label, windows)
            if alias is not None and alias in wmap:
                spec.time[i] = alias
            else:
                errs.append(f"time_label_unknown:{label}")
    # Nhiều nhãn thô cùng ánh xạ về một cửa sổ (vd 2025-01-01 và 2025-01-31
    # đều → main) sẽ tạo dòng trùng trong chuỗi.
    spec.time = list(dict.fromkeys(spec.time or []))

    # 2. filters: giá trị phải thuộc danh sách ứng viên
    allowed_values = _allowed_filter_values(ctx, entities)
    for f in spec.filters or []:
        field = str(f.get("field", ""))
        op = str(f.get("op", "="))
        if field not in FILTER_FIELDS:
            errs.append(f"filter_field_unknown:{field}")
        if op not in FILTER_OPS:
            errs.append(f"filter_op_unknown:{op}")
        for v in f.get("values", []) or []:
            if not _value_allowed(field, str(v), allowed_values):
                errs.append(f"filter_value_unknown:{field}={v}")

    # 3. metric & subject
    m = get(spec.metric)
    if spec.metric and m is None:
        errs.append(f"metric_unknown:{spec.metric}")
    if m is not None:
        views = getattr(ctx, "views", set())
        if views and m.source not in views:
            errs.append(f"metric_source_missing:{spec.metric}")
        caps = getattr(ctx, "data_caps", set())
        if caps and m.caps and not (m.caps & caps):
            errs.append(f"metric_caps_missing:{spec.metric}")
    if m is not None and spec.subject:
        if spec.subject not in m.subjects and spec.subject not in ("none", "null"):
            errs.append(f"subject_not_allowed:{spec.metric}/{spec.subject}")
    # Filter chỉ hợp lệ nếu cột filter có thật trong nguồn của metric.
    if m is not None and spec.filters:
        source = m.source
        if (m.name == "orders"
                and (spec.params or {}).get("threshold") not in (None, "")):
            source = "v_lines"
        cols = _source_columns(ctx, source)
        if cols:
            for f in spec.filters:
                field = str(f.get("field", ""))
                candidates = _FILTER_SOURCE_COLUMNS.get(field, (field,))
                if not any(c in cols for c in candidates):
                    errs.append(f"filter_not_in_source:{field}")

    # 4. intent ↔ output
    if spec.intent not in INTENT_OUTPUTS:
        errs.append(f"intent_unknown:{spec.intent}")
    else:
        allowed = INTENT_OUTPUTS[spec.intent]
        if allowed and spec.output not in allowed:
            errs.append(f"output_not_allowed:{spec.intent}/{spec.output}")

    # 5. chuỗi so sánh một cửa sổ là vô nghĩa (trả nhãn 'main' rác)
    if spec.intent == "compare_series" and len(spec.time or []) < 2:
        errs.append("compare_series_needs_two_windows")

    # 6. limit
    if spec.intent in ("rank_top", "lookup_single"):
        if spec.limit is None:
            errs.append("limit_required")
        elif spec.intent == "lookup_single" and spec.limit != 1:
            errs.append("lookup_single_limit_must_be_1")

    # 7. params
    for k in (spec.params or {}):
        if k not in PARAM_KEYS:
            errs.append(f"param_unknown:{k}")
    return errs


def _allowed_filter_values(ctx: BizContext, entities: list[EntityMatch] | None
                           ) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {f: set() for f in FILTER_FIELDS}
    for key, vals in (ctx.value_dict or {}).items():
        if key in out:
            out[key] = {nd(str(v)) for v in vals}
    for e in entities or []:
        if e.kind in ("product", "customer", "category"):
            out.setdefault(e.kind, set()).add(nd(e.canonical_name))
            if e.code:
                out[e.kind].add(nd(e.code))
    return out


def _value_allowed(field: str, value: str, allowed: dict[str, set[str]]) -> bool:
    vals = allowed.get(field)
    if not vals:
        return True
    return nd(value) in vals


# ------------------------------------------------------------------ compile

def _time_predicate(spec: Spec, windows: list[TimeWindow], knobs: Knobs,
                    label: str = "main", date_col: str = "order_date") -> str:
    wmap = _window_map(windows)
    win = wmap.get(label)
    if win is None:
        return "TRUE"
    # Cửa sổ lũy kế vẫn có start thật (đầu năm, đầu kỳ). Bỏ start biến
    # "từ đầu năm đến nay" thành "toàn bộ dữ liệu đến nay".
    pred = (f"(s.{date_col} BETWEEN DATE '{win.start.isoformat()}' "
            f"AND DATE '{win.end.isoformat()}')")
    if win.kind == "shift":
        lo, hi = knobs.shift_morning if win.shift == "sang" else knobs.shift_afternoon
        pred += (f" AND EXTRACT(hour FROM s.order_ts) BETWEEN {int(lo)} AND {int(hi)}")
    return pred


def _filter_predicate(spec: Spec, ctx: BizContext) -> str:
    parts: list[str] = []
    for f in spec.filters or []:
        field = str(f.get("field", ""))
        op = str(f.get("op", "="))
        values = [str(v) for v in (f.get("values") or [])]
        if not values:
            continue
        vals_sql = ", ".join("'" + v.replace("'", "''") + "'" for v in values)
        vals_ci = ", ".join("'" + v.lower().replace("'", "''") + "'" for v in values)
        if field == "product":
            # Người dùng hỏi bằng tên hàng; filter có thể là tên hoặc mã.
            clause = (f"(s.product_code IN ({vals_sql}) OR "
                      f"lower(s.product_name) IN ({vals_ci}))")
        elif field == "category":
            clause = f"lower(s.category) IN ({vals_ci})"
        elif field == "customer":
            clause = (f"(s.customer_key IN ({vals_sql}) OR "
                      f"lower(s.customer_name) IN ({vals_ci}))")
        elif field == "unit_name":
            clause = f"lower(s.base_unit) IN ({vals_ci})"
        else:
            clause = f"lower(s.{field}) IN ({vals_ci})"
        if op == "!=":
            clause = f"NOT ({clause})"
        parts.append(clause)
    return " AND ".join(parts) if parts else "TRUE"


def _subject_exprs(subject: str | None) -> tuple[str, str, str]:
    """Trả (code, name, valid) theo luật xếp hạng (4.8)."""
    sub = subject or "none"
    if sub == "product":
        code = "COALESCE(s.product_code, '')"
        name = ("(SELECT p.product_name FROM v_products p "
                "WHERE p.product_code = s.product_code)")
        valid = "NOT s.is_service AND s.product_name IS NOT NULL"
    elif sub == "customer":
        code = "COALESCE(s.customer_key, lower(s.customer_name), '')"
        name = ("COALESCE((SELECT c.customer_name FROM v_customers c "
                "WHERE c.customer_key = s.customer_key), s.customer_name, '')")
        valid = "NOT s.is_walkin"
    elif sub == "category":
        code = "COALESCE(s.category, '')"
        name = "COALESCE(s.category, '')"
        valid = "TRUE"
    elif sub == "day":
        code = "CAST(s.order_date AS VARCHAR)"
        name = "CAST(s.order_date AS VARCHAR)"
        valid = "TRUE"
    elif sub == "week":
        code = "CAST(date_trunc('week', s.order_date) AS VARCHAR)"
        name = "CAST(date_trunc('week', s.order_date) AS VARCHAR)"
        valid = "TRUE"
    elif sub == "month":
        code = "CAST(date_trunc('month', s.order_date) AS VARCHAR)"
        name = "CAST(date_trunc('month', s.order_date) AS VARCHAR)"
        valid = "TRUE"
    elif sub in ("channel", "pay_method", "employee", "customer_group", "supplier"):
        code = f"COALESCE(s.{sub}, '')"
        name = f"COALESCE(s.{sub}, '')"
        valid = f"s.{sub} IS NOT NULL"
    elif sub == "window":
        code = "s.order_date::VARCHAR"
        name = "s.order_date::VARCHAR"
        valid = "TRUE"
    else:
        code = "''"
        name = "''"
        valid = "TRUE"
    return code, name, valid


def _post_for(spec: Spec) -> str | None:
    if spec.intent == "compare_series":
        if spec.output in ("string", "date"):
            return "argmax_label" if "nhat" in nd(str(spec.params.get("check", ""))) \
                or True else "argmin_label"
        return "series_increasing" if spec.params.get("check") != "series_decreasing" \
            else "series_decreasing"
    if spec.intent == "boolean_check":
        if spec.params.get("check") == "series_decreasing":
            return "series_decreasing"
        if spec.params.get("check") == "series_increasing":
            return "series_increasing"
        return "exists"
    return None


def compile_spec(spec: Spec, ctx: BizContext, knobs: Knobs, windows: list[TimeWindow],
                 as_of: date) -> CompiledPlan:
    """Biên dịch Spec → ``CompiledPlan`` (SQL + hậu xử lý)."""
    m = get(spec.metric) or get("revenue")
    source = m.source
    date_col = m.date_col
    value_expr = m.value_expr
    as_of_sql = f"DATE '{as_of.isoformat()}'"
    time_pred = _time_predicate(spec, windows, knobs, "main", date_col)
    filter_pred = _filter_predicate(spec, ctx)
    subj_code, subj_name, subj_valid = _subject_exprs(spec.subject)
    if m.name == "qty":
        subj_valid = f"({subj_valid}) AND NOT s.is_service" if subj_valid != "TRUE" \
            else "NOT s.is_service"

    multi_field = (spec.params or {}).get("multi_field")
    multi_values = (spec.params or {}).get("multi_values") or []

    threshold_value = None
    if m.name in ("orders", "customers") and spec.intent == "aggregate_total":
        raw_thr = (spec.params or {}).get("threshold")
        if raw_thr not in (None, ""):
            if isinstance(raw_thr, (int, float)):
                threshold_value = float(raw_thr)
            else:
                digits = _re.sub(r"[^\d.\-]", "", str(raw_thr)).replace(".", "")
                try:
                    threshold_value = float(digits)
                except ValueError:
                    threshold_value = None

    if (threshold_value is not None and m.name == "orders"
            and "v_lines" in getattr(ctx, "views", set())):
        # Đếm đơn theo ngưỡng doanh thu/tiền hàng của cả đơn.
        sql = f"""
            SELECT COUNT(*) AS value FROM (
                SELECT s.order_id, SUM(COALESCE(s.line_amount_net, 0)) AS v
                FROM v_lines s
                WHERE {time_pred} AND {filter_pred} AND s.order_date <= {as_of_sql}
                GROUP BY s.order_id
                HAVING v >= {threshold_value}
            ) t"""
        post = None
    elif (threshold_value is not None and m.name == "customers"
          and "v_orders" in getattr(ctx, "views", set())):
        # Đếm khách có ít nhất N đơn trong kỳ.
        sql = f"""
            SELECT COUNT(*) AS value FROM (
                SELECT COALESCE(NULLIF(s.customer_key, ''), lower(s.customer_name))
                       AS customer_key
                FROM v_orders s
                WHERE {time_pred} AND {filter_pred} AND s.order_date <= {as_of_sql}
                  AND NOT s.is_walkin
                GROUP BY 1
                HAVING COUNT(DISTINCT s.order_id) >= {threshold_value}
            ) t"""
        post = None
    elif multi_field and multi_values and spec.intent in ("aggregate_total", "multi_value"):
        # Mỗi giá trị một nhánh; list giữ đúng thứ tự câu hỏi nêu.
        parts = []
        for v in multi_values:
            esc = str(v).replace("'", "''")
            pred = f"s.{multi_field} IN ('{esc}')"
            parts.append(
                f"SELECT '{esc}' AS label, {value_expr} AS value FROM {source} s "
                f"WHERE {time_pred} AND ({pred}) AND {filter_pred} "
                f"AND s.{date_col} <= {as_of_sql}"
            )
        sql = " UNION ALL ".join(parts)
        post = "series_values"
    elif spec.intent == "aggregate_total" or spec.intent == "cancel_rate":
        # Tỉ lệ huỷ = 100 * đơn huỷ / mọi đơn trong kỳ (rulebook dòng 18).
        if spec.output == "percent" and (spec.intent == "cancel_rate"
                                         or m.name == "cancelled_orders"):
            value_expr = ("100.0 * COUNT(*) FILTER (WHERE s.is_cancelled)"
                          " / NULLIF(COUNT(*), 0)")
        # Tổng của tập rỗng là 0 (không bán được gì), không phải NULL → retry.
        if m.name in ZERO_WHEN_EMPTY and spec.output != "percent":
            value_expr = f"COALESCE({value_expr}, 0)"
        sql = templates.T1.format(VALUE_EXPR=value_expr, SOURCE=source, TIME=time_pred,
                                   FILTER=filter_pred, DATE_COL=date_col, AS_OF=as_of_sql)
        post = None
    elif spec.intent in ("rank_top", "lookup_single", "filter_list"):
        limit = spec.limit
        having = ""
        if spec.having:
            op = str(spec.having.get("op", ">"))
            val = spec.having.get("value", 0)
            having = f"HAVING {value_expr} {op} {val}"
        limit_sql = f"LIMIT {int(limit) + 1}" if limit else ""
        sql = templates.T2.format(SUBJ_CODE=subj_code, SUBJ_NAME=subj_name,
                                  VALUE_EXPR=value_expr, SOURCE=source, TIME=time_pred,
                                  FILTER=filter_pred, SUBJ_VALID=subj_valid,
                                  DATE_COL=date_col, AS_OF=as_of_sql, HAVING=having,
                                  DIR="ASC" if spec.order == "asc" else "DESC",
                                  LIMIT_PLUS_1=limit_sql)
        post = None
    elif spec.intent == "compare_periods":
        mode = str(spec.params.get("compare_mode", "pct"))
        time_main = _time_predicate(spec, windows, knobs, "main", date_col)
        time_base = _time_predicate(spec, windows, knobs, "base", date_col)
        if spec.subject and spec.subject not in ("none", "null"):
            limit = spec.limit
            limit_sql = f"LIMIT {int(limit) + 1}" if limit else ""
            sql = templates.T3_SUBJECT.format(
                SUBJ_CODE=subj_code, SUBJ_NAME=subj_name, VALUE_EXPR=value_expr,
                SOURCE=source, TIME_MAIN=time_main, TIME_BASE=time_base, FILTER=filter_pred,
                SUBJ_VALID=subj_valid, DATE_COL=date_col, AS_OF=as_of_sql, MODE=mode,
                DIR="ASC" if spec.order == "asc" else "DESC", LIMIT_PLUS_1=limit_sql)
        else:
            sql = templates.T3.format(VALUE_EXPR=value_expr, SOURCE=source,
                                      TIME_MAIN=time_main, TIME_BASE=time_base,
                                      FILTER=filter_pred, DATE_COL=date_col,
                                      AS_OF=as_of_sql, MODE=mode)
        post = None
    elif spec.intent == "compare_series":
        parts = []
        wmap = _window_map(windows)
        for label in spec.time:
            w = wmap.get(label)
            if w is None:
                continue
            pred = _time_predicate(spec, windows, knobs, label, date_col)
            parts.append(
                f"SELECT '{label}' AS label, {value_expr} AS value FROM {source} s "
                f"WHERE {pred} AND {filter_pred} AND s.{date_col} <= {as_of_sql}"
            )
        sql = " UNION ALL ".join(parts) if parts else templates.T1.format(
            VALUE_EXPR=value_expr, SOURCE=source, TIME=time_pred, FILTER=filter_pred,
            DATE_COL=date_col, AS_OF=as_of_sql)
        if spec.output == "list":
            post = "series_values"
        elif spec.output in ("string", "date"):
            post = "argmax_label"
        else:
            post = "series_increasing"
    elif spec.intent == "boolean_check":
        parts = []
        wmap = _window_map(windows)
        for label in (spec.time or ["main"]):
            w = wmap.get(label)
            if w is None:
                continue
            pred = _time_predicate(spec, windows, knobs, label, date_col)
            parts.append(
                f"SELECT '{label}' AS label, {value_expr} AS value FROM {source} s "
                f"WHERE {pred} AND {filter_pred} AND s.{date_col} <= {as_of_sql}"
            )
        sql = " UNION ALL ".join(parts) if parts else templates.T1.format(
            VALUE_EXPR=value_expr, SOURCE=source, TIME=time_pred, FILTER=filter_pred,
            DATE_COL=date_col, AS_OF=as_of_sql)
        post = _post_for(spec)
    elif spec.intent == "point_in_time":
        wmap = _window_map(windows)
        win = wmap.get("main")
        cutoff = (win.end if (win and win.kind == "cumulative") else as_of)
        cutoff_sql = f"DATE '{cutoff.isoformat()}'"
        limit = spec.limit
        limit_sql = f"LIMIT {int(limit) + 1}" if limit else ""
        dir_sql = "ASC" if spec.order == "asc" else "DESC"
        if m.template == "point_stock":
            sql = templates.POINT_STOCK.format(CUTOFF=cutoff_sql, DIR=dir_sql,
                                               LIMIT_PLUS_1=limit_sql)
        elif m.template == "point_debt":
            if m.name == "debt_age":
                sql = templates.POINT_DEBT_AGE.format(CUTOFF=cutoff_sql, DIR=dir_sql,
                                                       LIMIT_PLUS_1=limit_sql)
            else:
                sql = templates.POINT_DEBT.format(CUTOFF=cutoff_sql, DIR=dir_sql,
                                                  LIMIT_PLUS_1=limit_sql)
        elif m.template == "expiring":
            days = int(spec.params.get("expiring_days", 30) or 30)
            sql = templates.POINT_EXPIRING.format(CUTOFF=cutoff_sql, DAYS=days,
                                                  DIR=dir_sql, LIMIT_PLUS_1=limit_sql)
        else:
            sql = templates.T1.format(VALUE_EXPR=value_expr, SOURCE=source, TIME=time_pred,
                                      FILTER=filter_pred, DATE_COL=date_col, AS_OF=as_of_sql)
        post = None
    elif spec.intent == "group_share":
        limit = spec.limit
        limit_sql = f"LIMIT {int(limit) + 1}" if limit else ""
        sql = templates.T7.format(SUBJ_CODE=subj_code, SUBJ_NAME=subj_name,
                                  VALUE_EXPR=value_expr, SOURCE=source, TIME=time_pred,
                                  FILTER=filter_pred, SUBJ_VALID=subj_valid,
                                  DATE_COL=date_col, AS_OF=as_of_sql,
                                  DIR="ASC" if spec.order == "asc" else "DESC",
                                  LIMIT_PLUS_1=limit_sql)
        post = None
    else:
        sql = templates.T1.format(VALUE_EXPR=value_expr, SOURCE=source, TIME=time_pred,
                                  FILTER=filter_pred, DATE_COL=date_col, AS_OF=as_of_sql)
        post = None

    return CompiledPlan(
        sql=sql, post=post, out_type=spec.output,
        meta={"is_money": bool(m.is_money), "value_col": "value",
              "subject": spec.subject, "metric": m.name, "intent": spec.intent},
    )
