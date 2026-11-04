"""Prefetch: gọi tool đọc trước khi lập kế hoạch (EXECUTION-PLAN.md §8.14).

Luôn chạy SAU scope (R3). Mặc định `PREFETCH_MODE="off"` vì đọc thừa làm giảm precision.
"""
from lifemate.bm25 import BM25, tokenize
from lifemate.catalog import readers_for


def _tool_document(tool) -> str:
    return " ".join([tool.name or "", tool.description or "", tool.returns or ""])


def select_prefetch_tools(tools, transcript, ref_sources, mode, max_reads) -> list:
    """Chọn tool đọc để prefetch."""
    if mode == "off":
        return []
    tools = tools or {}
    chosen = []
    seen = set()

    def add(tool):
        if tool is None or tool.name in seen:
            return
        seen.add(tool.name)
        chosen.append(tool)

    if mode == "deps":
        writes = [t for t in tools.values() if t.kind == "write"]
        if writes:
            docs = [_tool_document(t) for t in writes]
            index = BM25(docs)
            ranked = index.rank(tokenize(transcript or ""))
            for i, _score in ranked[:3]:
                tool = writes[i]
                colls = []
                for pname, pspec in (tool.props or {}).items():
                    if isinstance(pspec, dict) and pspec.get("x-ref"):
                        colls.append(str(pspec["x-ref"]).split(".")[-1])
                for coll in colls:
                    for reader in readers_for(coll, tools, ref_sources):
                        if not reader.required:
                            add(reader)
                            break
    elif mode == "all":
        for tool in sorted(tools.values(), key=lambda t: t.name):
            if tool.kind == "read" and not tool.required and not tool.one_of:
                add(tool)
    return chosen[:max_reads]


def run_prefetch(env, store, tools_to_call, log=None) -> None:
    """Gọi từng tool đọc và nạp kết quả vào store."""
    from lifemate.executor import safe_call
    for tool in tools_to_call or []:
        result = safe_call(env, tool.name, {}, log)
        store.ingest(tool.name, {}, result)
