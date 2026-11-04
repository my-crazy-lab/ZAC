"""Entity linking: khớp tên trong câu hỏi với mã/tên trong dữ liệu (M6).

Nguyên tắc:
- **Tên giữ dấu** trong index (để trả đúng tên); **so khớp** trên dạng bỏ dấu.
- Khớp theo n-gram 1..5 token, bỏ n-gram toàn stopword.
- Điểm = ``max(token_set_ratio, partial_ratio)/100`` (+ thưởng nếu khớp token đầu).
- Giữ điểm ≥ 0.8; ưu tiên span dài, rồi điểm cao; mỗi span tối đa 3 kết quả.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from rapidfuzz import fuzz

from dtypes import EntityMatch
from text.normalize import nd

log = logging.getLogger(__name__)

STOPWORDS = {
    "la", "cua", "bao", "nhieu", "nhat", "thang", "tuan", "nam", "ngay", "hom",
    "nay", "roi", "truoc", "co", "khong", "mot", "nhung", "voi", "va", "hay",
    "cho", "tu", "den", "trong", "ngoai", "gia", "tong", "so", "danh", "sach",
    "liet", "ke", "theo", "tai", "thieu", "nhieu", "it", "nhat", "top", "sp",
    "mat", "hang", "san", "pham", "don", "doanh", "thu", "khach", "cua",
    "trong", "khoang", "thoi", "gian", "gia", "tri", "nhom", "loai", "bi",
}

MAX_NGRAM = 5
MIN_SCORE = 0.8
# Cụm nghiệp vụ không phải tên hàng — không được dùng để khớp thực thể
PHRASE_STOP = {
    "mat hang", "ban chay", "ban chay nhat", "doanh thu", "so luong", "gia tri",
    "nhom hang", "khach hang", "don hang", "hang hoa", "san pham", "nha cung cap",
    "don vi", "ca sang", "ca chieu", "so don", "ti le", "ty le", "hieu chinh",
    "so sanh", "ban duoc", "bao nhieu tien", "gia ban", "gia von", "cong no",
    "ton kho", "het han", "mua bao nhieu", "ban bao nhieu", "gia tri don",
    "trung binh", "khach mua", "nhan vien", "mua hang", "nhap hang", "tra hang",
}


def _align_score(query: str, target: str) -> float:
    """Khớp theo **cặp từ** (mỗi từ của span khớp ≤ 1 từ của tên).

    Tránh việc span ngắn khớp nhầm tên dài ("ban chay" ↛ "ban chai colgate").
    """
    q_toks = query.split()
    t_toks = target.split()
    if not q_toks or not t_toks:
        return 0.0
    if q_toks == t_toks:
        return 1.0
    used: set[int] = set()
    matches = 0
    for qt in q_toks:
        best = None
        best_i = None
        for i, tt in enumerate(t_toks):
            if i in used:
                continue
            r = fuzz.ratio(qt, tt)
            if r >= 80 and (best is None or r > best):
                best, best_i = r, i
        if best is not None and best_i is not None:
            used.add(best_i)
            matches += 1
    return 2.0 * matches / (len(q_toks) + len(t_toks))


@dataclass
class EntityIndex:
    """Chỉ mục thực thể của một business."""

    entries: list[tuple[str, str, str | None]] = field(default_factory=list)
    by_kind: dict[str, list[tuple[str, str, str | None]]] = field(default_factory=dict)

    def add(self, kind: str, name: Any, code: Any = None) -> None:
        if name is None:
            return
        nm = str(name).strip()
        if not nm or nm.lower() in ("nan", "none"):
            return
        cd = str(code).strip() if code is not None and str(code).strip() else None
        item = (kind, nm, cd)
        if item in self.entries:
            return
        self.entries.append(item)
        self.by_kind.setdefault(kind, []).append(item)

    def kinds(self) -> list[str]:
        return sorted(self.by_kind)

    def size(self) -> int:
        return len(self.entries)


def build_entity_index(con: Any, value_dict: dict[str, list[str]] | None = None) -> EntityIndex:
    """Dựng chỉ mục từ ``v_products``, ``v_customers`` và từ điển giá trị."""
    idx = EntityIndex()
    _fill_from_table(con, idx, "v_products", "product_name", "product_code")
    _fill_from_table(con, idx, "v_customers", "customer_name", "customer_key")
    if value_dict:
        for field_name, values in sorted(value_dict.items()):
            kind = field_name if field_name in ("channel", "pay_method", "customer_group",
                                               "employee", "size", "category") else "value"
            for v in values or []:
                idx.add(kind, v, None)
    return idx


def _fill_from_table(con: Any, idx: EntityIndex, table: str, name_col: str,
                     code_col: str | None) -> None:
    try:
        rows = con.execute(f'SELECT "{name_col}", "{code_col}" FROM "{table}"').fetchall()
    except Exception:  # noqa: BLE001 — bảng không tồn tại là chuyện bình thường
        return
    for name, code in rows:
        idx.add("product" if table == "v_products" else "customer", name, code)


def _score(query: str, target_nd: str, target_raw: str) -> float:
    """Điểm khớp tên (0..1) theo cặp từ + trùng token đầu."""
    if not query or not target_nd:
        return 0.0
    if query == target_nd:
        return 1.0
    score = _align_score(query, target_nd)
    q0 = query.split()[0]
    t0 = target_nd.split()[0]
    if q0 and q0 == t0:
        score = min(1.0, score + 0.05)
    if target_raw and query == nd(target_raw):
        score = 1.0
    return score


def link_entities(q_nd: str, index: EntityIndex, min_score: float = MIN_SCORE,
                  max_per_span: int = 3) -> list[EntityMatch]:
    """Trả về các thực thể khớp trong câu hỏi (đã bỏ dấu)."""
    if not q_nd or index is None or not index.entries:
        return []
    tokens = q_nd.split()
    if not tokens:
        return []
    # chuẩn bị dạng bỏ dấu của index
    prepared: list[tuple[str, str, str | None, str, str]] = []
    for kind, name, code in index.entries:
        nname = nd(name)
        ncode = nd(code) if code else ""
        prepared.append((kind, name, code, nname, ncode))

    cands: list[tuple[int, int, float, str, str, str | None]] = []
    n_tokens = len(tokens)
    for size in range(min(MAX_NGRAM, n_tokens), 0, -1):
        for start in range(0, n_tokens - size + 1):
            span_tokens = tokens[start:start + size]
            if all(t in STOPWORDS for t in span_tokens):
                continue
            span_nd = " ".join(span_tokens)
            if span_nd in PHRASE_STOP:
                continue
            best_per_kind: dict[str, tuple[float, str, str | None, str]] = {}
            for kind, name, code, nname, ncode in prepared:
                sc = _score(span_nd, nname, name)
                if code:
                    sc = max(sc, _score(span_nd, ncode, code))
                if sc < min_score:
                    continue
                cur = best_per_kind.get(kind)
                if cur is None or sc > cur[0]:
                    best_per_kind[kind] = (sc, name, code, kind)
            if not best_per_kind:
                continue
            ranked = sorted(best_per_kind.values(), key=lambda x: (-x[0], x[1]))
            for sc, name, code, kind in ranked[:max_per_span]:
                cands.append((start, start + size, sc, name, code, kind))

    # loại span chồng nhau: giữ span có điểm cao nhất, rồi span dài hơn
    cands.sort(key=lambda c: (-c[2], -(c[1] - c[0]), c[0]))
    used: list[tuple[int, int]] = []
    out: list[EntityMatch] = []
    for start, end, sc, name, code, kind in cands:
        if any(not (end <= s or start >= e) for s, e in used):
            continue
        used.append((start, end))
        out.append(EntityMatch(span=(start, end), kind=kind, canonical_name=name,
                               code=code, score=round(float(sc), 4)))
    out.sort(key=lambda m: (m.span[0], -m.span[1]))
    return out
