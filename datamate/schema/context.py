"""Compile README + mapping + snapshot thành Business Context cho planner.

BTC cung cấp trong mỗi folder:
- đoạn mở đầu mô tả tập dữ liệu (layout sheet, header, cách nối, dòng đặc biệt),
- ``## File`` (file/sheet có gì),
- ``## Cột trong ...`` (nghĩa từng cột),
- ``## Quy ước`` (luật nghiệp vụ của shop).

Module này đọc **tất cả** các khối đó và thêm snapshot dữ liệu thật, thay vì
chỉ lấy mục "Quy ước" như bản cũ. Không phụ thuộc business_id.
"""

from __future__ import annotations

import re
from typing import Any

from schema.mapper import parse_readme
from text.normalize import nd

# Nhóm luật nghiệp vụ mà planner/verifier cần phân biệt.
RULE_SIGNALS: dict[str, tuple[str, ...]] = {
    "revenue": ("doanh thu", "tien ban", "ban duoc bao nhieu tien", "gia tri don",
                "chiet khau", "giam gia", "vat"),
    "cancel": ("huy", "trang thai", "status", "da huy", "bi huy"),
    "return": ("tra hang", "hoan hang", "doi tra", "tra lai"),
    "unit": ("quy doi", "don vi", "thung", "hop", "lon", "kg", "base unit"),
    "discount": ("voucher", "dung diem", "diem", "chiet khau", "giam gia"),
    "shipping": ("phi ship", "phi van chuyen", "van chuyen", "giao hang", "phi phuc vu"),
    "debt": ("cong no", "con no", "thu no", "tra no", "thanh toan"),
    "stock": ("ton kho", "ton cuoi", "nhap kho", "lo hang", "han su dung", "hsd"),
    "cost": ("gia von", "gia nhap", "loi nhuan", "loi gop", "cost"),
    "delivery": ("giao hang", "van don", "doi giao", "lo giao"),
}

SPECIAL_ROW_NAMES = ("voucher", "dùng điểm", "dung diem", "phí ship", "phi ship",
                     "phí phục vụ", "phi phuc vu")

_RELATION_CUES = ("noi qua", "nối qua", "join", "cung so", "cùng số", "khop",
                  "khớp", "sheet", "header", "gop", "gộp", "ma hang", "mã hàng",
                  "ma khach", "mã khách", "khong co ma", "không có mã")


def classify_rule(text: str) -> list[str]:
    """Gán một dòng README vào các nhóm luật (có thể nhiều nhóm)."""
    q = nd(text)
    return [kind for kind, signals in RULE_SIGNALS.items()
            if any(sig in q for sig in signals)]


def parse_readme_sections(readme: str) -> tuple[list[str], dict[str, list[str]]]:
    """Trả (đoạn mở đầu, {heading: [dòng]}) của README."""
    intro: list[str] = []
    sections: dict[str, list[str]] = {}
    cur: str | None = None
    for raw in (readme or "").splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if stripped.startswith("# "):
            continue
        if stripped.startswith("## "):
            cur = stripped[3:].strip()
            sections.setdefault(cur, [])
            continue
        if stripped.startswith("#"):
            cur = None
            continue
        if cur is None:
            if stripped:
                intro.append(stripped)
        else:
            sections[cur].append(line)
    return intro, sections


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.;:])\s+|\n+", text)
    return [p.strip() for p in parts if p.strip()]


def _pick_sentences(text: str, cues: tuple[str, ...], limit: int = 6) -> list[str]:
    out: list[str] = []
    for sentence in _sentences(text):
        q = nd(sentence)
        if any(cue in q for cue in cues):
            out.append(sentence[:320])
        if len(out) >= limit:
            break
    return out


def _snippets(text: str, cues: tuple[str, ...], limit: int = 6,
              width: int = 200) -> list[str]:
    """Trích cửa sổ quanh từ khóa — tránh lặp cả đoạn văn dài."""
    q = nd(text)
    out: list[str] = []
    seen: set[int] = set()
    for cue in cues:
        start = 0
        while len(out) < limit:
            idx = q.find(cue, start)
            if idx < 0:
                break
            if all(abs(idx - s) > 60 for s in seen):
                seen.add(idx)
                out.append(text[max(0, idx - 80): idx + width].strip())
            start = idx + len(cue)
    return out


def _files(sections: dict[str, list[str]]) -> list[str]:
    out: list[str] = []
    for heading, lines in sections.items():
        if heading.lower() != "file":
            continue
        for line in lines:
            text = line.strip().lstrip("-* ").strip()
            if text:
                out.append(text)
    return out


def _file_columns(readme: str) -> dict[str, dict[str, str]]:
    """Mô tả cột theo file/sheet, giữ nguyên tên gốc của cột."""
    raw = parse_readme(readme)
    out: dict[str, dict[str, str]] = {}
    for heading, lines in parse_readme_sections(readme)[1].items():
        m = re.match(r"Cột trong\s+`?([^`]+)`?", heading, re.IGNORECASE)
        if not m:
            continue
        key = m.group(1).strip()
        cols = raw.get(nd(key), {})
        out[key] = {k: v for k, v in cols.items()}
    return out


def _special_rows(text: str) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for name in SPECIAL_ROW_NAMES:
        if name in seen:
            continue
        snippet = next(iter(_snippets(text, (name,), limit=1, width=180)), "")
        if snippet:
            seen.add(name)
            out.append({"row": name, "note": snippet[:220]})
    return out


def build_snapshot(con: Any, views: set[str]) -> dict[str, Any]:
    """Mô tả dữ liệu thật của shop từ các view canonical."""
    out: dict[str, Any] = {}

    def rows(sql: str) -> list[tuple]:
        try:
            return con.execute(sql).fetchall()
        except Exception:  # noqa: BLE001
            return []

    def one(sql: str) -> Any:
        got = rows(sql)
        return got[0][0] if got and got[0] else None

    if "v_lines" in views:
        out["n_lines"] = one("SELECT COUNT(*) FROM v_lines")
        out["n_orders"] = one("SELECT COUNT(DISTINCT order_id) FROM v_lines")
        out["n_products"] = one("SELECT COUNT(DISTINCT product_code) FROM v_lines")
        date_range = rows("SELECT MIN(order_date), MAX(order_date) FROM v_lines")
        if date_range and date_range[0]:
            out["date_min"], out["date_max"] = date_range[0][0], date_range[0][1]
        sample = rows("SELECT DISTINCT product_name FROM v_lines "
                      "WHERE product_name IS NOT NULL ORDER BY 1 LIMIT 5")
        out["sample_products"] = [str(r[0]) for r in sample if r and r[0]]
        amt = rows("SELECT MIN(line_amount_net), MAX(line_amount_net) FROM v_lines")
        if amt and amt[0]:
            out["amount_min"], out["amount_max"] = amt[0][0], amt[0][1]
    if "v_orders" in views:
        out["n_customers"] = one(
            "SELECT COUNT(DISTINCT customer_key) FROM v_orders "
            "WHERE customer_key IS NOT NULL AND NOT is_walkin")
        ch = rows("SELECT channel, COUNT(*) FROM v_orders WHERE channel IS NOT NULL "
                  "GROUP BY 1 ORDER BY 2 DESC LIMIT 8")
        out["channels"] = [str(r[0]) for r in ch if r and r[0]]
        st = rows("SELECT status_raw, COUNT(*) FROM v_orders_all "
                  "WHERE status_raw IS NOT NULL GROUP BY 1 ORDER BY 2 DESC LIMIT 8") \
            if "v_orders_all" in views else []
        out["statuses"] = [str(r[0]) for r in st if r and r[0]]
    if "v_lines" in views:
        cat = rows("SELECT category, COUNT(*) FROM v_lines WHERE category IS NOT NULL "
                   "GROUP BY 1 ORDER BY 2 DESC LIMIT 8")
        out["categories"] = [str(r[0]) for r in cat if r and r[0]]
    if "v_imports" in views:
        out["n_imports"] = one("SELECT COUNT(*) FROM v_imports")
        rng = rows("SELECT MIN(import_date), MAX(import_date) FROM v_imports")
        if rng and rng[0] and rng[0][0] is not None:
            out["import_date_min"], out["import_date_max"] = rng[0][0], rng[0][1]
        sup = rows("SELECT supplier, COUNT(*) FROM v_imports WHERE supplier IS NOT NULL "
                   "GROUP BY 1 ORDER BY 2 DESC LIMIT 5")
        out["suppliers"] = [str(r[0]) for r in sup if r and r[0]]
    if "v_inventory" in views:
        out["n_stock_products"] = one(
            "SELECT COUNT(DISTINCT product_code) FROM v_inventory")
        last = one("SELECT MAX(inv_date) FROM v_inventory")
        if last is not None:
            out["inventory_last_date"] = last
    if "v_payments" in views:
        out["n_payments"] = one("SELECT COUNT(*) FROM v_payments")
    return out


def compile_context(readme: str, mapping: dict[str, Any], graph: dict[str, Any],
                    knobs: Any, views: set[str], data_caps: set[str],
                    archetype: str = "UNKNOWN", schema_conf: float = 0.0,
                    graph_issues: list[str] | None = None,
                    snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
    """Trả Business Context (dict thuần, JSON hoá được)."""
    intro, sections = parse_readme_sections(readme)
    intro_text = " ".join(intro).strip()
    conventions = [line.strip().lstrip("-* ").strip()
                   for heading, lines in sections.items()
                   if heading.lower().startswith("quy ước") or heading.lower().startswith("quy uoc")
                   for line in lines if line.strip()]

    rules: list[dict[str, Any]] = []
    unit_rules: list[str] = []
    for text in conventions:
        kinds = classify_rule(text)
        is_conversion = bool(re.search(r"=\s*\d", text)) or "quy doi" in nd(text)
        if "unit" in kinds and is_conversion:
            unit_rules.append(text)
            continue
        rules.append({"kinds": kinds or ["other"], "text": text})

    columns = _file_columns(readme)
    mapped_columns: list[dict[str, str]] = []
    for entity, info in sorted((mapping or {}).get("entities", {}).items()):
        table = info.get("table", "")
        desc_map: dict[str, str] = {}
        for key, cols in columns.items():
            if nd(key) in nd(table) or nd(table) in nd(key):
                desc_map = cols
                break
        for role, column in sorted((info.get("cols") or {}).items()):
            mapped_columns.append({
                "entity": entity,
                "role": role,
                "column": str(column),
                "desc": desc_map.get(nd(str(column)), ""),
            })

    entities: dict[str, Any] = {}
    for name, info in sorted((mapping or {}).get("entities", {}).items()):
        entities[name] = {
            "tables": list(info.get("tables") or [info.get("table", "")]),
            "roles": sorted((info.get("cols") or {}).keys()),
            "fit": info.get("fit"),
        }

    full_text = intro_text + "\n" + "\n".join(conventions)
    relations = _snippets(full_text, _RELATION_CUES, limit=6, width=240)
    special_rows = _special_rows(full_text)
    status_notes = _snippets(full_text,
                             ("trang thai", "trạng thái", "ghi chu cua don",
                              "đơn huỷ", "don huy", "đang giao", "dang giao"),
                             limit=4, width=220)
    return {
        "archetype": archetype,
        "schema_conf": round(float(schema_conf), 4),
        "shape": intro_text[:1200],
        "files": _files(sections),
        "knobs": knobs.diff_from_default() if hasattr(knobs, "diff_from_default") else {},
        "rules": rules,
        "unit_rules": unit_rules,
        "relations": relations,
        "special_rows": special_rows,
        "status_notes": status_notes,
        "columns": columns,
        "mapped_columns": mapped_columns,
        "entities": entities,
        "roles": sorted({r for e in entities.values() for r in e["roles"]}),
        "views": sorted(v for v in views if str(v).startswith("v_")),
        "data_caps": sorted(data_caps),
        "snapshot": dict(snapshot or {}),
        "graph_issues": list(graph_issues or []),
    }


def _fmt_num(value: Any) -> str:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return str(value)
    return f"{int(f):,}" if f.is_integer() else f"{f:,.2f}"


def render_context(context: dict[str, Any] | None, max_rules: int = 12,
                   max_chars: int = 3200) -> str:
    """Bản text ngắn gọn của context để đưa vào prompt planner."""
    if not context:
        return ""
    lines = ["[SHOP CONTEXT]",
             f"archetype={context.get('archetype')} "
             f"schema_conf={context.get('schema_conf')}"]
    if context.get("shape"):
        lines.append("- mô tả: " + str(context["shape"])[:900])
    if context.get("files"):
        lines.append("- file: " + "; ".join(context["files"])[:500])

    snap = context.get("snapshot") or {}
    if snap:
        parts = []
        for key, label in (("n_lines", "dòng"), ("n_orders", "đơn"),
                           ("n_products", "sản phẩm"), ("n_customers", "khách")):
            if snap.get(key) is not None:
                parts.append(f"{label}={_fmt_num(snap[key])}")
        if snap.get("date_min") is not None:
            parts.append(f"ngày={snap['date_min']}..{snap['date_max']}")
        if snap.get("amount_min") is not None:
            parts.append(f"tiền dòng={_fmt_num(snap['amount_min'])}.."
                         f"{_fmt_num(snap['amount_max'])}")
        if snap.get("n_imports") is not None:
            parts.append(f"phiếu nhập={_fmt_num(snap['n_imports'])}")
        if snap.get("n_stock_products") is not None:
            parts.append(f"mã tồn kho={_fmt_num(snap['n_stock_products'])}")
        if snap.get("n_payments") is not None:
            parts.append(f"thanh toán={_fmt_num(snap['n_payments'])}")
        if parts:
            lines.append("- snapshot: " + ", ".join(parts))
        for key, label in (("statuses", "trạng thái"), ("channels", "kênh"),
                           ("categories", "nhóm hàng"),
                           ("sample_products", "hàng mẫu")):
            if snap.get(key):
                lines.append(f"- {label}: " + ", ".join(map(str, snap[key])))
    if context.get("relations"):
        lines.append("- quan hệ/khóa: " + " | ".join(context["relations"])[:700])
    if context.get("special_rows"):
        lines.append("- dòng đặc biệt: " + "; ".join(
            f"{r['row']}: {r['note']}" for r in context["special_rows"])[:700])
    if context.get("status_notes"):
        lines.append("- trạng thái/ghi chú: " + " | ".join(context["status_notes"])[:600])

    unit_rules = context.get("unit_rules") or []
    if unit_rules:
        lines.append(f"- quy đổi: {len(unit_rules)} dòng; ví dụ: "
                     + " | ".join(unit_rules[:5])[:600])
    rules = context.get("rules") or []
    if rules:
        rendered = []
        for rule in rules:
            if rule.get("kinds") == ["other"]:
                continue
            kinds = ",".join(rule.get("kinds") or [])
            rendered.append(f"[{kinds}] {rule.get('text')}")
        if rendered:
            lines.append("- quy ước:")
            lines.extend(f"  - {r}" for r in rendered[:max_rules])

    mapped = context.get("mapped_columns") or []
    if mapped:
        shown = []
        for item in mapped[:36]:
            desc = f" = {item['desc']}" if item.get("desc") else ""
            shown.append(f"{item['entity']}.{item['role']}: {item['column']}{desc}")
        lines.append("- cột đã map: " + " | ".join(shown))

    text = "\n".join(lines)
    return text[:max_chars]


def rule_kinds(context: dict[str, Any] | None) -> set[str]:
    out: set[str] = set()
    for rule in (context or {}).get("rules", []):
        out.update(rule.get("kinds") or [])
    return out


__all__ = ["RULE_SIGNALS", "classify_rule", "parse_readme_sections",
           "build_snapshot", "compile_context", "render_context", "rule_kinds"]
