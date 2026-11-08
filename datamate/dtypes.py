"""Dataclass dùng chung cho toàn hệ thống (EXECUTION-MVP.md §3.1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any, Hashable


class AnswerType(str, Enum):
    STRING = "string"
    NUMBER = "number"
    PERCENT = "percent"
    DATE = "date"
    BOOLEAN = "boolean"
    LIST = "list"
    TABLE = "table"
    UNANSWERABLE = "unanswerable"
    ABSTAIN = "abstain"


@dataclass
class Question:
    id: str
    business_id: str
    text: str
    as_of: date

    @staticmethod
    def from_jsonl(obj: dict[str, Any]) -> "Question":
        raw = obj.get("as_of_date") or obj.get("as_of") or ""
        return Question(
            id=str(obj["id"]),
            business_id=str(obj["business_id"]),
            text=str(obj.get("question") or obj.get("text") or ""),
            as_of=date.fromisoformat(str(raw)[:10]),
        )


@dataclass
class Answer:
    type: str
    value: Any = None
    reason: str | None = None

    @staticmethod
    def from_jsonl(obj: dict[str, Any]) -> "Answer":
        t = str(obj.get("type", AnswerType.ABSTAIN.value))
        return Answer(type=t, value=obj.get("answer"), reason=obj.get("reason"))

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"type": self.type}
        if self.type == AnswerType.UNANSWERABLE.value:
            out["reason"] = self.reason or ""
            return out
        if self.type == AnswerType.ABSTAIN.value:
            return out
        out["answer"] = self.value
        return out


@dataclass
class Knobs:
    """Mặc định = rulebook train (EXECUTION-MVP.md §3.1)."""

    revenue_after_line_discount: bool = True
    revenue_deduct_order_voucher: bool = False
    revenue_include_vat: bool = False
    revenue_include_shipping: bool = False
    exclude_cancelled: bool = True
    returned_policy: str = "exclude_order"  # exclude_order | exclude_line | ignore
    bestseller_metric: str = "qty"  # qty | revenue | orders
    week_start: int = 0  # 0 = Thứ Hai
    this_month: str = "month_to_date"
    this_week: str = "week_to_date"
    last_n_includes_today: bool = True
    cost_method: str = "line_cost"  # line_cost | wavg_by_lot | wavg_up_to_sale_date
    tet_start: tuple = ("lunar", 12, 23, -1)
    tet_end: tuple = ("lunar", 1, 10, 0)
    shift_morning: tuple = (6, 13)
    shift_afternoon: tuple = (14, 21)
    rounding_money: str = "half_up"

    def diff_from_default(self) -> dict[str, Any]:
        """Các knob khác mặc định (dùng cho schema card + prompt)."""
        base = Knobs()
        out: dict[str, Any] = {}
        for f in ("revenue_after_line_discount", "revenue_deduct_order_voucher",
                  "revenue_include_vat", "revenue_include_shipping",
                  "exclude_cancelled", "returned_policy", "bestseller_metric",
                  "week_start", "this_month", "this_week", "last_n_includes_today",
                  "cost_method", "tet_start", "tet_end", "shift_morning",
                  "shift_afternoon", "rounding_money"):
            v = getattr(self, f)
            b = getattr(base, f)
            if v != b:
                out[f] = v
        return out


@dataclass
class RuleSpec:
    knobs: Knobs
    domains: set[str] = field(default_factory=set)
    features: set[str] = field(default_factory=set)
    unmapped: list[str] = field(default_factory=list)


@dataclass
class TimeWindow:
    label: str
    start: date
    end: date
    kind: str = "period"  # period | cumulative | shift
    shift: str | None = None  # "sang" | "chieu"
    trunc_same_days: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "kind": self.kind,
            "shift": self.shift,
            "trunc_same_days": self.trunc_same_days,
        }


@dataclass
class BizContext:
    con: Any
    archetype: str
    data_caps: set[str]
    views: set[str]
    date_min: date
    date_max: date
    schema_conf: float
    flags: dict
    status_invalid: dict
    value_dict: dict
    card: str
    entity_index: Any
    rules: RuleSpec
    invariants: dict
    verified: bool = True
    business_id: str = ""
    biz_dir: str = ""
    graph: dict | None = None
    context: dict | None = None
    catalog: list | None = None


@dataclass
class Spec:
    intent: str
    metric: str | None = None
    subject: str | None = None
    filters: list[dict] = field(default_factory=list)
    time: list[str] = field(default_factory=list)
    having: dict | None = None
    order: str = "desc"
    limit: int | None = None
    output: str = "number"
    params: dict = field(default_factory=dict)

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "Spec":
        return Spec(
            intent=str(d.get("intent", "other")),
            metric=d.get("metric"),
            subject=d.get("subject"),
            filters=list(d.get("filters") or []),
            time=list(d.get("time") or []),
            having=d.get("having"),
            order=str(d.get("order", "desc")),
            limit=d.get("limit"),
            output=str(d.get("output", "number")),
            params=dict(d.get("params") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent": self.intent,
            "metric": self.metric,
            "subject": self.subject,
            "filters": self.filters,
            "time": self.time,
            "having": self.having,
            "order": self.order,
            "limit": self.limit,
            "output": self.output,
            "params": self.params,
        }


@dataclass
class CompiledPlan:
    sql: str
    post: str | None = None
    out_type: str = "number"
    meta: dict = field(default_factory=dict)


@dataclass
class ExecResult:
    columns: list[str]
    rows: list[tuple]
    error: str | None = None
    elapsed_s: float = 0.0

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass
class Candidate:
    answer: Answer
    source: str
    spec_or_sql: str
    votes: int = 1
    k: int = 1
    extra: dict = field(default_factory=dict)


@dataclass
class EntityMatch:
    span: tuple[int, int]
    kind: str
    canonical_name: str
    code: str | None
    score: float


@dataclass
class AnswerCheck:
    answerable: bool
    p_unanswerable: float
    reason: str
    entity_missing: bool = False


@dataclass
class MappingCandidate:
    mapping: dict
    penalties: dict
    score: float
    schema_conf: float


def canon_hashable(value: Any) -> Hashable:
    """Chuyển giá trị bất biến về dạng hashable (dùng cho canon_key)."""
    if isinstance(value, dict):
        return tuple(sorted((str(k), canon_hashable(v)) for k, v in value.items()))
    if isinstance(value, (list, tuple)):
        return tuple(canon_hashable(v) for v in value)
    if isinstance(value, (set, frozenset)):
        return tuple(sorted(canon_hashable(v) for v in value))
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)
