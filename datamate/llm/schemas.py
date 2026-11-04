"""JSON schema cho các lời gọi LLM (M9/M10).

Tất cả lời gọi LLM đều **có schema** ⇒ parse + validate tự động, không cần
regex rời rạc.
"""

from __future__ import annotations

FILTER_SCHEMA = {
    "type": "object",
    "properties": {
        "field": {"type": "string",
                  "enum": ["product", "category", "customer", "channel", "pay_method",
                           "employee", "customer_group", "size", "unit_name"]},
        "op": {"type": "string", "enum": ["=", "!=", "in"]},
        "values": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["field", "op", "values"],
    "additionalProperties": False,
}

SPEC_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {
            "type": "string",
            "enum": ["aggregate_total", "compare_periods", "compare_series", "rank_top",
                     "lookup_single", "filter_list", "boolean_check", "point_in_time",
                     "group_share", "cancel_rate", "other"],
        },
        "metric": {"type": "string"},
        "subject": {"type": "string",
                    "enum": ["product", "category", "customer", "day", "week", "month",
                             "channel", "pay_method", "employee", "customer_group",
                             "window", "none"]},
        "filters": {"type": "array", "items": FILTER_SCHEMA},
        "time": {"type": "array", "items": {"type": "string"}},
        "having": {"type": "object"},
        "order": {"type": "string", "enum": ["asc", "desc"]},
        "limit": {"type": "integer"},
        "output": {"type": "string",
                   "enum": ["number", "percent", "string", "date", "boolean", "list",
                            "table"]},
        "params": {"type": "object"},
    },
    "required": ["intent", "metric", "subject", "filters", "time", "output"],
    "additionalProperties": False,
}

ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "type": {"type": "string",
                 "enum": ["string", "number", "percent", "date", "boolean", "list",
                          "table", "unanswerable", "abstain"]},
        "answer": {},
        "reason": {"type": "string"},
    },
    "required": ["type"],
    "additionalProperties": False,
}

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "correct": {"type": "boolean"},
        "confidence": {"type": "number"},
        "note": {"type": "string"},
    },
    "required": ["correct", "confidence"],
    "additionalProperties": False,
}

CATEGORY_SCHEMA = {
    "type": "object",
    "properties": {
        "category": {"type": "string"},
        "feature": {"type": "string"},
        "needs_other_data": {"type": "boolean"},
    },
    "required": ["category", "feature", "needs_other_data"],
    "additionalProperties": False,
}

TIE_SCHEMA = {
    "type": "object",
    "properties": {
        "tie": {"type": "boolean"},
        "reason": {"type": "string"},
    },
    "required": ["tie"],
    "additionalProperties": False,
}
