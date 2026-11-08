"""Map bảng thô → vai trò cột canonical (M4.C).

Nguyên tắc:
- Gán vai trò **theo thực thể** (mỗi thực thể có tập vai trò riêng) để tránh
  nhiễu chéo (ví dụ "Tổng tiền phiếu nhập" không bị hiểu là "Tổng tiền đơn").
- Một bảng có thể phục vụ **nhiều thực thể** (bảng phẳng: vừa là dòng bán vừa
  là đơn hàng).
- Không có ``if business_id == ...``: mọi khác biệt đến từ cấu trúc dữ liệu,
  tên cột, README, rulebook.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

from dtypes import MappingCandidate
from schema.roles import ENTITY_REQUIRED, ENTITY_ROLES, ROLE_DEFS, score_column
from text.normalize import column_key, nd, split_camel

log = logging.getLogger(__name__)

# Ngưỡng để một bảng phục vụ một thực thể
ENTITY_THRESHOLD = 0.55
# Ngưỡng điểm của một cột được chấp nhận làm vai trò
COLUMN_MIN_SCORE = 0.5
# Ngưỡng khớp **tên** (tên cột + mô tả README) — vai trò phải khớp tên
NAME_MIN_SCORE = 0.78

# Ưu tiên bảng theo tên (để phá vỡ hòa) — theo *tên*, không theo business_id
TABLE_PREFERENCE: dict[str, tuple[str, ...]] = {
    "lines": ("ban hang", "chi tiet don", "chitiet", "don hang", "hoa don chi tiet",
              "so ban hang", "phieu ban"),
    "orders": ("don hang", "hoa don", "hoadon", "danhsachhoadon", "so ban hang", "bao cao ban hang"),
    "products": ("san pham", "danh muc", "hang hoa", "bang gia", "don vi"),
    "customers": ("khach", "khach hang"),
    "payments": ("thanh toan", "quy", "cong no", "thu tien"),
    "units": ("quy doi", "danh muc", "don vi"),
    "imports": ("nhap hang", "phieu nhap", "nhap"),
    "inventory": ("ton kho", "ton cuoi", "bao cao ton"),
    "lots": ("lo", "lot"),
    "price_history": ("bang gia", "lich su gia", "gia"),
    "deliveries": ("giao hang", "giao"),
}

_README_SECTION_RE = re.compile(r"^##\s+Cột trong\s+`?([^`]+)`?", re.IGNORECASE)
_README_ITEM_RE = re.compile(r"^-\s+\*\*(.+?)\*\*\s*:\s*(.+)$")
_README_MENTION_RE = re.compile(r"`?([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)`?")
_README_CONVENTIONS_RE = re.compile(r"^##\s+Quy ước\s*$", re.IGNORECASE)


def parse_readme(readme: str) -> dict[str, dict[str, str]]:
    """README → {tên file hoặc tên bảng (bỏ dấu): {tên cột (bỏ dấu): mô tả}}.

    Ngoài mục ``## Cột trong `<file>``, còn đọc các câu nhắc ``bảng.cột``
    (kiểu README của shop SQLite).
    """
    out: dict[str, dict[str, str]] = {}
    cur: str | None = None
    for line in (readme or "").splitlines():
        m = _README_SECTION_RE.match(line.strip())
        if m:
            cur = nd(m.group(1))
            out.setdefault(cur, {})
            continue
        m = _README_ITEM_RE.match(line.strip())
        if m and cur is not None:
            out[cur][nd(m.group(1))] = m.group(2).strip()
    # --- câu nhắc dạng ``bang.cot``
    for line in (readme or "").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        for m in _README_MENTION_RE.finditer(s):
            tbl, col = nd(m.group(1)), nd(m.group(2))
            if not tbl or not col or len(tbl) < 3:
                continue
            desc = s.strip()
            out.setdefault(tbl, {}).setdefault(col, desc)
    return out


def parse_readme_facts(readme: str) -> dict[str, Any]:
    """Tách phần README mà canonicalizer/prompt cần biết ngoài mô tả cột."""
    lines = (readme or "").splitlines()
    conventions: list[str] = []
    in_conventions = False
    for raw in lines:
        line = raw.strip()
        if line.startswith("## "):
            in_conventions = bool(_README_CONVENTIONS_RE.match(line))
            continue
        if in_conventions and line:
            conventions.append(line.lstrip("-* ").strip())
    text = " ".join(conventions)
    return {
        "columns": parse_readme(readme),
        "conventions": conventions,
        "unit_rules": [x for x in conventions if "quy đổi" in x.lower() or "quy doi" in x.lower()],
        "special_rows": [x for x in ("voucher", "dùng điểm", "dung diem", "phí ship", "phi ship", "phí phục vụ", "phi phuc vu")
                         if x in text.lower()],
    }


def _profile(df: Any, col: str, sample: int = 2000) -> dict[str, Any]:
    """Thống kê cột để VALUE_TESTS (lấy mẫu để chạy nhanh trên bảng lớn)."""
    from ingest.clean import detect_date_column, parse_number_series

    s = df[col]
    n_rows = int(len(s))
    nonnull = s.dropna()
    n_nonnull = int(len(nonnull))
    prof: dict[str, Any] = {
        "n_rows": n_rows,
        "n_nonnull": n_nonnull,
        "n_distinct": int(nonnull.nunique()) if n_nonnull else 0,
    }
    if n_nonnull == 0:
        prof.update({"num_ratio": 0.0, "date_ratio": 0.0, "ts_ratio": 0.0,
                     "str_ratio": 0.0, "int_ratio": 0.0, "median": 0.0})
        return prof
    samp = nonnull.head(sample)
    num = parse_number_series(samp)
    prof["num_ratio"] = float(num.notna().sum()) / max(1, len(samp))
    vals = num.dropna()
    prof["int_ratio"] = float((vals.abs() - vals.round()).abs().lt(1e-9).sum()) / max(1, len(vals))
    prof["median"] = float(vals.abs().median()) if len(vals) else 0.0
    is_date, has_time = detect_date_column(samp)
    prof["date_ratio"] = 1.0 if is_date else 0.0
    prof["ts_ratio"] = 1.0 if (is_date and has_time) else 0.0
    obj = samp.map(lambda v: isinstance(v, str))
    prof["str_ratio"] = float(obj.sum()) / max(1, len(samp))
    return prof


def _column_query(col: str, desc: str | None) -> str:
    q = nd(col)
    if desc:
        q = f"{q} {nd(desc)}"
    return q


def _readme_for_table(table: Any, readme_map: dict[str, dict[str, str]]) -> dict[str, str]:
    """Mô tả cột theo tên file (khớp theo tên file, không theo thứ tự bảng).

    Với SQLite, tên bảng có tiền tố theo file (vd ``pos_chi_tiet_don``) ⇒ thử
    bỏ tiền tố để khớp với README.
    """
    file_key = nd(str(table.source))
    if file_key in readme_map:
        return readme_map[file_key]
    table_key = nd(str(table.name))
    if table_key in readme_map:
        return readme_map[table_key]
    if "_" in table_key:
        stripped = table_key.split("_", 1)[1]
        if stripped in readme_map:
            return readme_map[stripped]
    for k, v in readme_map.items():
        if k and (k in file_key or file_key in k):
            return v
    return {}


def _role_scores(table: Any, readme_cols: dict[str, str]) -> dict[str, dict[str, Any]]:
    """Điểm (role, cột) cho mọi vai trò: (score, độ dài token, name_score)."""
    profiles: dict[str, dict[str, Any]] = {}
    queries: dict[str, tuple[str, str]] = {}
    for col in table.df.columns:
        if str(col).endswith("__nd"):
            continue
        profiles[str(col)] = _profile(table.df, str(col))
        desc = column_key(readme_cols.get(nd(str(col)), "") or "")
        queries[str(col)] = (column_key(str(col)), desc)

    scores: dict[str, dict[str, Any]] = {}
    for role in ROLE_DEFS:
        for col in profiles:
            name_nd, desc_nd = queries[col]
            sc, nlen, ns = score_column(role, name_nd, profiles[col], desc_nd=desc_nd)
            if sc > 0:
                scores.setdefault(role.name, {})[col] = (round(float(sc), 4), nlen, round(float(ns), 4))
    return scores


def _assign(scores: dict[str, dict[str, Any]], role_names: tuple[str, ...],
            min_score: float = COLUMN_MIN_SCORE,
            min_name: float = NAME_MIN_SCORE) -> dict[str, tuple[str, float]]:
    """Gán vai trò cho cột (greedy theo điểm, ưu tiên token dài).

    Chỉ cột có **tên khớp mạnh** (``name_score >= min_name``) mới được gán —
    nếu không, mọi cột ngày sẽ khớp mọi vai trò ngày.
    """
    pairs: list[tuple[float, int, str, str]] = []
    for role in role_names:
        for col, (sc, nlen, ns) in scores.get(role, {}).items():
            if sc >= min_score and ns >= min_name:
                pairs.append((sc, nlen, role, col))
    pairs.sort(key=lambda x: (-x[0], -x[1], x[2], x[3]))
    assigned: dict[str, tuple[str, float]] = {}
    used: set[str] = set()
    for sc, _nlen, role, col in pairs:
        if role in assigned or col in used:
            continue
        assigned[role] = (col, round(float(sc), 4))
        used.add(col)
    return assigned


def _entity_fit(scores: dict[str, dict[str, Any]], entity: str,
                global_assigned: dict[str, tuple[str, float]]
                ) -> tuple[float, dict[str, tuple[str, float]]]:
    """Mức độ bảng khớp một thực thể + phép gán vai trò tương ứng.

    Vai trò lấy từ **phép gán toàn cục** (đã giải quyết xung đột cột–vai trò),
    nên "Mã nhập hàng" không bị gán cho ``product_code`` khi đã là ``import_id``.
    """
    role_names = set(ENTITY_ROLES.get(entity, ()))
    assigned = {r: v for r, v in global_assigned.items() if r in role_names}
    groups = ENTITY_REQUIRED.get(entity, ())
    if not groups:
        return 0.0, assigned
    vals: list[float] = []
    for group in groups:
        best = 0.0
        for role in group:
            if role in assigned:
                best = max(best, assigned[role][1])
        vals.append(best)
    return sum(vals) / len(vals), assigned


def _split_camel(name: str) -> str:
    """Tách CamelCase để so khớp tên file: ``DanhSachDonViTinh`` → ``danh sach don vi tinh``."""
    return nd(split_camel(name).replace("_", " "))


def _same_logical_table(name_a: str, name_b: str) -> bool:
    """Cùng một sổ nhưng khác sheet/file: so phần tên trước ``__`` sau khi bỏ số cuối."""
    def key(name: str) -> str:
        base = str(name).split("__")[0]
        return re.sub(r"[_\-]?\d+$", "", base)

    return bool(key(name_a)) and key(name_a) == key(name_b)


def _file_stem(source: str) -> str:
    """Gốc tên file bỏ đuôi và hậu tố số: ``DanhSachHoaDonChiTiet_1.xlsx`` → ``danhsachhoadonchitiet``."""
    base = os.path.splitext(str(source))[0]
    base = re.sub(r"[\s_-]*\d+$", "", base)
    return nd(base)


def _pref_score(entity: str, *names: str) -> int:
    """Điểm ưu tiên theo tên bảng (để phá vỡ hòa giữa các bảng cùng thực thể)."""
    keys = [_split_camel(n) for n in names if n]
    for kw in TABLE_PREFERENCE.get(entity, ()):
        for k in keys:
            if kw in k:
                return 1
    return 0


def map_business(tables: list[Any], readme: str, llm: Any = None) -> list[MappingCandidate]:
    """Sinh mapping ứng viên (điểm giảm dần)."""
    readme_map = parse_readme(readme)
    per_table: list[dict[str, Any]] = []

    for t in tables:
        readme_cols = _readme_for_table(t, readme_map)
        scores = _role_scores(t, readme_cols)
        global_assigned = _assign(scores, tuple(r.name for r in ROLE_DEFS))
        fits: dict[str, tuple[float, dict[str, tuple[str, float]]]] = {}
        for entity in ENTITY_REQUIRED:
            fit, assigned = _entity_fit(scores, entity, global_assigned)
            if fit >= ENTITY_THRESHOLD:
                fits[entity] = (fit, assigned)
        if fits:
            per_table.append({"table": t, "scores": scores, "fits": fits,
                              "global": global_assigned})

    # --- chọn bảng cho từng thực thể (điểm cao nhất; phá vỡ hòa theo tên + số dòng)
    best_for_entity: dict[str, tuple[tuple[float, float, int], dict[str, Any]]] = {}
    for info in per_table:
        for ent, (fit, _assigned) in info["fits"].items():
            pref = _pref_score(ent, str(info["table"].source), str(info["table"].name))
            n_rows = int(len(info["table"].df))
            bonus = 0.0
            if ent == "lines":
                # Ưu tiên bảng dòng bán **có tiền** hơn bảng giao hàng/nhật ký
                # (cùng có số lượng + tên hàng) mà không loại bỏ shop chỉ có
                # một bảng dòng thiếu cột tiền.
                bonus = 0.35 if any(r in _assigned for r in
                                    ("line_amount", "unit_price")) else 0.0
            key = (round(fit, 4) + 0.15 * pref + bonus, pref, n_rows)
            cur = best_for_entity.get(ent)
            if cur is None or key > cur[0]:
                best_for_entity[ent] = (key, info)

    # Bảng phẳng: nếu bảng dòng bán **tự có** cột đơn (mã đơn + ngày/giờ) thì
    # dùng nó làm bảng đơn luôn. Nếu không, mapper có thể chọn bảng dòng ở
    # file tháng này và bảng đơn ở file tháng khác ⇒ join rỗng.
    if "lines" in best_for_entity and "orders" in best_for_entity:
        lines_info = best_for_entity["lines"][1]
        if lines_info["table"].name != best_for_entity["orders"][1]["table"].name:
            glob = lines_info["global"]
            if "order_id" in glob and ("order_date" in glob or "order_ts" in glob):
                if "orders" not in lines_info["fits"]:
                    assigned = {r: v for r, v in glob.items()
                                if r in ENTITY_ROLES["orders"]}
                    lines_info["fits"]["orders"] = (1.0, assigned)
                best_for_entity["orders"] = best_for_entity["lines"]

    entities: dict[str, dict[str, Any]] = {}
    for ent, (key, info) in sorted(best_for_entity.items()):
        _f, assigned = info["fits"][ent]
        cols = {r: c for r, (c, _s) in assigned.items()}
        if not cols:
            continue
        # hợp nhất các bảng cùng thực thể có **cùng tập cột** (vd chi tiết _1/_2)
        sig = set(cols.values())
        tables_same = [info["table"].name]
        for other in per_table:
            if other["table"].name == info["table"].name:
                continue
            _f2, a2 = other["fits"].get(ent, (0.0, {}))
            if _f2 < ENTITY_THRESHOLD:
                continue
            # a2.values() là (cột, điểm) — phải lấy tên cột, không lấy tuple,
            # nếu không overlap luôn 0 và các sheet tháng không bao giờ gộp.
            other_cols = {c for c, _s in a2.values()}
            overlap = 0.0
            if other_cols:
                overlap = len(sig & other_cols) / max(1, len(sig | other_cols))
            # Cùng file chưa đủ để coi là cùng bảng: một file báo cáo có thể
            # chứa sổ bán hàng, bảng giao hàng, danh mục… với cột khác nhau.
            # Chỉ gộp khi tập cột gần như trùng **và** cùng tên logic (các
            # sheet tháng / file _1, _2 của cùng một sổ).
            same_source = str(info["table"].source) == str(other["table"].source)
            if overlap >= 0.8 and (same_source or _same_logical_table(
                    info["table"].name, other["table"].name)):
                tables_same.append(other["table"].name)
        entities[ent] = {
            "table": info["table"].name,
            "tables": sorted(tables_same),
            "cols": cols,
            "scores": {r: s for r, (_c, s) in assigned.items()},
            "fit": round(float(_f), 4),
        }

    # bảng phẳng: bảng "lines" cũng chứa thuộc tính đơn → ghi nhận
    if "lines" in entities and "order_id" not in entities["lines"]["cols"]:
        # Cột mã phiếu trên sổ bán hàng đôi khi bị global greedy gán nhầm
        # sang import_id. Khôi phục vai trò bắt buộc của dòng bán nếu tên cột
        # khớp mạnh; đây là sửa xung đột vai trò, không phụ thuộc business.
        info = next((i for i in per_table
                     if i["table"].name == entities["lines"]["table"]), None)
        if info is not None:
            best = max(info["scores"].get("order_id", {}).items(),
                       key=lambda item: item[1][0], default=None)
            if best is not None and best[1][0] >= 0.85 and best[1][2] >= NAME_MIN_SCORE:
                col, (score, _nlen, _ns) = best
                entities["lines"]["cols"]["order_id"] = col
                entities["lines"]["scores"]["order_id"] = round(float(score), 4)
    if "lines" in entities and "orders" in entities:
        if entities["lines"]["table"] == entities["orders"]["table"]:
            entities["lines"]["order_cols"] = dict(entities["orders"]["cols"])
        else:
            entities["lines"]["order_table"] = entities["orders"]["table"]
            entities["lines"]["order_cols"] = dict(entities["orders"]["cols"])
    elif "lines" in entities:
        # thuộc tính đơn nằm ngay trong bảng dòng bán (bảng phẳng không có bảng đơn)
        info = next(i for i in per_table if i["table"].name == entities["lines"]["table"])
        order_cols = {r: c for r, (c, _s) in info["global"].items()
                      if r in ENTITY_ROLES["orders"]}
        if order_cols:
            entities["lines"]["order_cols"] = order_cols

    penalties: dict[str, float] = {}
    for entity, required in ENTITY_REQUIRED.items():
        if entity not in entities:
            if entity in ("units", "imports", "inventory", "lots", "price_history",
                          "deliveries", "products", "customers", "payments"):
                continue
            penalties[f"missing_{entity}"] = 0.15
            continue
        cols = entities[entity]["cols"]
        for group in required:
            if not any(r in cols for r in group):
                penalties[f"{entity}.{'|'.join(group)}"] = 0.2
        for role, sc in entities[entity]["scores"].items():
            if sc < 0.65:
                penalties[f"{entity}.{role}_low"] = 0.05

    mapping = {"entities": entities}
    total_pen = sum(penalties.values())
    score = 1.0 - min(1.0, total_pen)
    schema_conf = max(0.0, min(1.0, score))
    return [MappingCandidate(mapping=mapping, penalties=penalties,
                              score=round(score, 4), schema_conf=round(schema_conf, 4))]
