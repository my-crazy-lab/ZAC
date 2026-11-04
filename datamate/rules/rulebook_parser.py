"""Parse rulebook → ``Knobs`` + ``RuleSpec`` (M3).

Thuật toán 8 bước (EXECUTION-MVP.md §M3):
1. Tách rulebook thành câu.
2. Câu đã có trong rulebook train ⇒ giữ knob mặc định.
3. Chọn knob liên quan theo từ khoá.
4. Suy giá trị: quy tắc từ định hình nội dung câu; nếu chưa chắc ⇒ hỏi LLM (MCQ).
5. Câu không khớp knob nào nhưng có từ khoá nghiệp vụ lạ ⇒ ``unmapped``.
6. Validate giá trị ∈ ``KNOB_DOMAINS``; sai ⇒ về mặc định + ``unmapped``.
7. Quét từ khoá để điền ``features`` / ``domains``.
8. Log ``RuleSpec``.
"""

from __future__ import annotations

import hashlib
import logging
import re
from typing import Any, Callable

from dtypes import Knobs, RuleSpec
from rules.knobs import KNOB_DOMAINS, is_valid
from text.normalize import nd

log = logging.getLogger(__name__)

# ------------------------------------------------------------------ câu

def split_sentences(text: str) -> list[str]:
    """Tách rulebook thành câu (theo dòng, dấu '.', bullet)."""
    out: list[str] = []
    for line in (text or "").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        s = re.sub(r"^\s*[-*•]\s*", "", s)
        s = re.sub(r"^\s*\d+[.)]\s*", "", s)
        if not s:
            continue
        for part in re.split(r"(?<=[.!?])\s+(?=[A-ZÀ-Ữ*•])", s):
            part = part.strip()
            if part:
                out.append(part)
    return out


def sentence_hash(sentence: str) -> str:
    return hashlib.sha1(nd(sentence).encode("utf-8")).hexdigest()


_MD_RE = re.compile(r"[*`|>]+")


def clean_md(s: str) -> str:
    """Bỏ ký hiệu markdown để so khớp nội dung luật."""
    return re.sub(r"\s+", " ", _MD_RE.sub(" ", s)).strip()


# Knob nào chỉ được suy trong mục nào của rulebook (tránh suy nhầm chéo mục)
SECTION_KNOBS: dict[str, set[str]] = {
    "don hang va doanh thu": {
        "revenue_after_line_discount", "revenue_deduct_order_voucher",
        "revenue_include_vat", "revenue_include_shipping",
        "exclude_cancelled", "returned_policy",
    },
    "thoi gian": {
        "week_start", "this_month", "this_week", "last_n_includes_today",
        "tet_start", "tet_end", "shift_morning", "shift_afternoon",
    },
    "xep hang": {"bestseller_metric"},
    "cong no": set(),
    "kho, nhap hang, gia von": {"cost_method"},
}

# Mục không chứa luật nghiệp vụ (chỉ chứa cách ghi/chấm điểm)
NON_RULE_SECTIONS = ("dap an va cham diem", "tu ngung", "khong tra loi duoc")


def sections(text: str) -> dict[str, str]:
    """Tên mục (heading) → nội dung."""
    out: dict[str, str] = {}
    cur = ""
    buf: list[str] = []
    for line in (text or "").splitlines():
        if line.startswith("#"):
            if cur:
                out[cur] = "\n".join(buf)
            cur = line.lstrip("#").strip()
            buf = []
        else:
            buf.append(line)
    if cur:
        out[cur] = "\n".join(buf)
    return out


# ------------------------------------------------------- từ khoá → knob

KNOB_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("revenue_include_vat", ("vat", "thue")),
    ("revenue_include_shipping", ("van chuyen", "phi ship", "phi giao", "ship")),
    ("revenue_deduct_order_voucher", ("voucher", "ma giam gia", "giam gia tren ca don",
                                      "khuyen mai theo tong tien")),
    ("revenue_after_line_discount", ("giam gia tren tung dong", "chiet khau dong",
                                     "da tru giam gia")),
    ("exclude_cancelled", ("huy", "cancel")),
    ("returned_policy", ("tra hang", "hoan hang", "return", "refund")),
    ("bestseller_metric", ("ban chay", "ban duoc nhieu nhat", "hot nhat")),
    ("this_week", ("tuan nay", "tuan truoc", "tuan roi")),
    ("week_start", ("tuan",)),
    ("this_month", ("thang nay", "thang truoc", "thang roi")),
    ("cost_method", ("gia von",)),
    ("tet_start", ("tet", "thang chap", "mung")),
    ("tet_end", ("tet", "mung 10")),
    ("shift_morning", ("ca sang",)),
    ("shift_afternoon", ("ca chieu",)),
    ("last_n_includes_today", ("ngay gan nhat", "ngay lien tiep")),
]

FEATURE_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("repair_ticket", ("sua xe", "so sua xe", "tho sua")),
    ("warranty_service", ("bao hanh",)),
    ("installment", ("tra gop", "ky gop", "tra cham")),
    ("trade_in", ("thu may cu", "thu cu")),
    ("member_since", ("ngay dang ky", "khach thanh vien", "thanh vien")),
    ("size_breakdown", ("size m, size l", "size", "kich co")),
    ("product_group_share", ("ty trong", "nhom hang")),
    ("peak_hour", ("khung gio", "cao diem")),
    ("loyal_customer", ("nhieu ngay co mua", "khach than thiet", "khach trung thanh nhat",
                        "khach so p nhat")),
    ("topping_split", ("topping",)),
    ("cash_shift_report", ("tien mat theo ca", "thu ngan", "bao cao tien mat theo ca")),
    ("debt_rules", ("cong no",)),
    ("cost_rules", ("gia von",)),
    ("shift_report", ("ca sang", "ca chieu")),
    ("average_by_weekday", ("trung binh moi ngay thu",)),
    ("supplier_rank", ("nha cung cap chinh",)),
    ("fastest_churn", ("khach hay doi y nhat",)),
    ("stockout", ("het hang cuoi ngay",)),
    ("delivery_rounds", ("so dot giao", "giao nhieu dot")),
]

DOMAIN_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("cafe", ("ca phe",)),
    ("pharmacy", ("nha thuoc",)),
    ("construction", ("vat lieu xay dung",)),
    ("baby", ("me va be",)),
    ("repair", ("sua xe",)),
    ("phone", ("dien thoai", "cua hang dien thoai")),
]

# Những từ khoá nghiệp vụ lạ ⇒ câu không map được (unmapped)
UNKNOWN_BUSINESS_RE = re.compile(
    r"\b(tinh|bao gom|khong tinh|loai tru|bo qua)\b"
)


def _infer_value(knob: str, sentence_nd: str) -> Any | None:
    """Suy giá trị knob từ nội dung câu (không dùng LLM)."""
    s = sentence_nd
    if knob == "week_start":
        if "bat dau **chu nhat**" in s or "bat dau chu nhat" in s:
            return 6
        if "bat dau **thu hai**" in s or "bat dau thu hai" in s:
            return 0
        return None
    if knob == "revenue_include_vat":
        if "khong cong thue vat" in s or "khong cong vat" in s:
            return False
        if "cong thue vat" in s or "tinh ca vat" in s:
            return True
        return None
    if knob == "revenue_include_shipping":
        if "khong gom phi giao" in s or "khong gom phi ship" in s:
            return False
        if "gom phi giao" in s or "tinh ca phi giao" in s or "cong phi ship" in s:
            return True
        return None
    if knob == "revenue_deduct_order_voucher":
        if "khong tru giam gia tren ca don" in s:
            return False
        if "tru giam gia tren ca don" in s:
            return True
        return None
    if knob == "revenue_after_line_discount":
        if "da tru giam gia tren tung dong" in s or "tru giam gia tren tung dong" in s:
            return True
        return None
    if knob == "exclude_cancelled":
        if "don bi huy" in s or "trang thai huy" in s:
            return True
        return None
    if knob == "returned_policy":
        if "bo **ca don**" in s or "bo ca don" in s or "loai **ca don**" in s:
            return "exclude_order"
        if "tru dong" in s or "chi tru dong" in s:
            return "exclude_line"
        return None
    if knob == "bestseller_metric":
        if "so luong quy ve don vi co ban" in s:
            return "qty"
        if "theo so tien" in s:
            return "revenue"
        if "theo so don" in s:
            return "orders"
        return None
    if knob == "this_month":
        if "thang nay" in s and "het hom nay" in s:
            return "month_to_date"
        return None
    if knob == "this_week":
        if "tuan nay" in s and "het hom nay" in s:
            return "week_to_date"
        return None
    if knob == "last_n_includes_today":
        if "ke ca hom nay" in s:
            return True
        return None
    if knob == "cost_method":
        if "gia von ghi tren dong ban" in s:
            return "line_cost"
        if "binh quan gia quyen theo lo" in s:
            return "wavg_by_lot"
        return None
    if knob == "tet_start":
        if "23 thang chap" in s:
            return ("lunar", 12, 23, -1)
        return None
    if knob == "tet_end":
        if "mung 10 thang gieng" in s:
            return ("lunar", 1, 10, 0)
        return None
    if knob == "shift_morning":
        m = re.search(r"ca sang\s+(\d{1,2}):(\d{2})\s*[-–]\s*(\d{1,2}):(\d{2})", s)
        if m:
            return (int(m.group(1)), int(m.group(3)))
        return None
    if knob == "shift_afternoon":
        m = re.search(r"ca chieu\s+(\d{1,2}):(\d{2})\s*[-–]\s*(\d{1,2}):(\d{2})", s)
        if m:
            return (int(m.group(1)), int(m.group(3)))
        return None
    return None


def _knob_options(knob: str) -> list[Any]:
    return list(KNOB_DOMAINS.get(knob, []))


def _mcq_prompt(sentence: str, knob: str, options: list[Any]) -> str:
    lines = [f"{i}. {opt}" for i, opt in enumerate(options)]
    return (
        f'Câu quy tắc: "{sentence}"\n'
        f"Tham số cần xác định: {knob}\n"
        "Chọn đúng MỘT lựa chọn. Chỉ trả JSON {\"choice\": <số>}.\n"
        + "\n".join(lines)
    )


def _llm_choice(llm: Any, sentence: str, knob: str, options: list[Any]) -> Any | None:
    """Hỏi LLM MCQ (schema ``{"choice": int}``); hỏi lại tối đa 1 lần."""
    if llm is None:
        return None
    available = getattr(llm, "available", True)
    if not available:
        return None
    import json

    prompt = _mcq_prompt(sentence, knob, options)
    schema = {"type": "object", "properties": {"choice": {"type": "integer"}},
              "required": ["choice"], "additionalProperties": False}
    try:
        outs = llm.generate([prompt], json_schema=schema)
    except Exception as exc:  # noqa: BLE001
        log.warning("LLM MCQ lỗi: %s", exc)
        return None
    for attempt in range(2):
        out = (outs or [""])[0] if outs else ""
        if not out:
            return None
        try:
            obj = json.loads(out)
            choice = int(obj["choice"])
        except (ValueError, KeyError, TypeError):
            if attempt == 0:
                try:
                    outs = llm.generate([prompt + "\nChỉ trả JSON {\"choice\": <số>}."],
                                        json_schema=schema)
                except Exception:  # noqa: BLE001
                    return None
                continue
            return None
        if 0 <= choice < len(options):
            return options[choice]
        return None
    return None


def parse_rulebook(text: str, train_text: str | None = None,
                   llm: Any = None) -> RuleSpec:
    """Parse rulebook thành ``RuleSpec`` (knobs + features + domains)."""
    knobs = Knobs()
    unmapped: list[str] = []
    features: set[str] = set()
    domains: set[str] = set()

    # --- 2. tập câu đã biết (train) ⇒ giữ mặc định
    train_hashes: set[str] = set()
    if train_text:
        train_hashes = {sentence_hash(s) for s in split_sentences(train_text)}

    sec = sections(text)
    for head, body in sec.items():
        head_nd = nd(head)
        allowed = None
        for key, val in SECTION_KNOBS.items():
            if key in head_nd:
                allowed = val
                break
        is_rule_section = not any(x in head_nd for x in NON_RULE_SECTIONS)
        for sent in split_sentences(body):
            s_nd = nd(clean_md(sent))
            if not s_nd:
                continue
            # --- 3. knob liên quan (giới hạn theo mục)
            candidates: list[str] = []
            for knob, kws in KNOB_KEYWORDS:
                if allowed is not None and knob not in allowed:
                    continue
                if any(kw in s_nd for kw in kws):
                    candidates.append(knob)
            matched = False
            for knob in candidates:
                value = _infer_value(knob, s_nd)
                if value is None and sentence_hash(sent) not in train_hashes:
                    value = _llm_choice(llm, clean_md(sent), knob, _knob_options(knob))
                if value is None:
                    continue
                if not is_valid(knob, value):
                    unmapped.append(f"[{knob}] {clean_md(sent)}")
                    continue
                setattr(knobs, knob, value)
                matched = True
            # --- 5. câu lạ
            if (not matched and not candidates and is_rule_section
                    and UNKNOWN_BUSINESS_RE.search(s_nd)):
                unmapped.append(clean_md(sent))

    # --- 7. features + domains
    full_nd = nd(clean_md(text))
    for feat, kws in FEATURE_KEYWORDS:
        if any(kw in full_nd for kw in kws):
            features.add(feat)
    for head, body in sec.items():
        head_nd = nd(head)
        for dom, kws in DOMAIN_KEYWORDS:
            if any(kw in head_nd for kw in kws):
                domains.add(dom)
        body_nd = nd(clean_md(body))
        for feat, kws in FEATURE_KEYWORDS:
            if any(kw in body_nd for kw in kws):
                features.add(feat)

    spec = RuleSpec(knobs=knobs, domains=domains, features=features,
                     unmapped=sorted(set(unmapped)))
    log.info("RuleSpec: domains=%s features=%s unmapped=%d",
             sorted(domains), sorted(features), len(spec.unmapped))
    return spec


def features_for_text(text: str, spec: RuleSpec) -> set[str]:
    """Nhóm nghiệp vụ của một câu hỏi (dùng cho feature ``rule_missing``)."""
    s = nd(text)
    out: set[str] = set()
    for feat, kws in FEATURE_KEYWORDS:
        if any(kw in s for kw in kws):
            out.add(feat)
    return out


def build_parser(llm: Any = None, train_rulebook_path: str | None = None
                 ) -> Callable[[str], RuleSpec]:
    """Trả về hàm parse dùng cho một split (có sẵn rulebook train để đối chiếu)."""
    train_text = None
    if train_rulebook_path:
        try:
            train_text = open(train_rulebook_path, encoding="utf-8").read()
        except OSError:
            train_text = None

    def _parse(text: str) -> RuleSpec:
        return parse_rulebook(text, train_text, llm)

    return _parse
