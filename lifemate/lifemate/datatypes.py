"""Hợp đồng dữ liệu dùng chung (EXECUTION-PLAN.md §7)."""
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Tool:
    name: str
    app: str
    kind: str
    description: str
    app_name_vi: str
    app_description: str
    returns: str
    parameters: dict
    required: list
    props: dict
    one_of: list          # list nhóm, mỗi nhóm là list tên tham số


@dataclass
class Hyp:
    text: str
    score: float


@dataclass
class Hint:
    kind: str             # "entity" | "number" | "time" | "digits"
    span: str
    value: Any
    conf: float
    extra: dict = field(default_factory=dict)


@dataclass
class Entity:
    id: str
    collection: str
    fields: dict
    names: list
    source_tool: str


@dataclass
class Call:
    name: str
    args: dict
    call_id: str = ""


@dataclass
class Ask:
    tool_name: str
    params: list


@dataclass
class GateResult:
    calls: list           # được phép thực thi, theo thứ tự
    ask: Any = None      # Ask | None
    refuse: bool = False
    notes: list = field(default_factory=list)
    needs_read: list = field(default_factory=list)   # [(tool_name, param, collection)]
    deferred: list = field(default_factory=list)     # call bị hoãn


class Deadline:
    """Hạn giờ cho một mẫu."""

    def __init__(self, seconds: float):
        import time
        self.seconds = seconds
        self.start = time.monotonic()

    def expired(self) -> bool:
        import time
        return (time.monotonic() - self.start) >= self.seconds

    def remaining(self) -> float:
        import time
        return max(0.0, self.seconds - (time.monotonic() - self.start))
