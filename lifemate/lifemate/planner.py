"""Planner: LLM sinh kế hoạch tool call (EXECUTION-PLAN.md §8.16)."""
from lifemate.catalog import to_llm_tools


def plan(llm, tools, messages, log=None):
    """Trả (calls, text, assistant_message).

    Truyền **toàn bộ** tools (kể cả tool đọc) để planner gọi được read tool có tham số ở lượt sau.
    """
    if llm is None:
        return [], "", {}
    return llm.generate(messages, tools=to_llm_tools(tools), log=log)
