"""Quyết định ngoài phạm vi (EXECUTION-PLAN.md §8.13).

MVP1 dùng stub `return True, {}`; MVP3 dùng BM25 + LLM.
"""
from lifemate import config
from lifemate.bm25 import BM25, tokenize
from lifemate.vi_norm import STOPWORDS_VI


def _tool_document(tool) -> str:
    return " ".join([
        tool.app or "",
        tool.app_name_vi or "",
        tool.app_description or "",
        tool.name or "",
        tool.description or "",
    ])


def _content_tokens(text: str) -> list:
    return [t for t in tokenize(text) if t not in STOPWORDS_VI]


def _coverage(query_tokens: list, document: str) -> float:
    if not query_tokens:
        return 0.0
    doc_tokens = set(tokenize(document))
    hit = sum(1 for t in query_tokens if t in doc_tokens)
    return hit / len(query_tokens)


def bm25_scope_features(transcript: str, installed_tools: dict, all_tools: dict) -> dict:
    """Đặc trưng BM25 của transcript so với catalog."""
    all_items = list(all_tools.values())
    if not all_items:
        return {"ratio": 1.0, "coverage": 0.0, "best_installed": None, "best_all": None}
    docs = [_tool_document(t) for t in all_items]
    index = BM25(docs)
    query = _content_tokens(transcript)
    ranked = index.rank(query)
    best_all = 0.0
    best_all_tool = None
    best_installed = 0.0
    best_installed_tool = None
    for i, score in ranked:
        tool = all_items[i]
        if score > best_all:
            best_all = score
            best_all_tool = tool.name
        if tool.name in installed_tools and score > best_installed:
            best_installed = score
            best_installed_tool = tool.name
    ratio = best_installed / max(best_all, 1e-6)
    coverage = 0.0
    if best_installed_tool is not None:
        coverage = _coverage(query, _tool_document(installed_tools[best_installed_tool]))
    return {
        "ratio": ratio,
        "coverage": coverage,
        "best_installed": best_installed_tool,
        "best_all": best_all_tool,
        "best_all_score": best_all,
        "best_installed_score": best_installed,
    }


def scope_llm_prompt(transcript: str, installed_tools: dict) -> list:
    lines = []
    for name, tool in installed_tools.items():
        if name == "sys.ask_missing_info":
            continue
        lines.append(f"{tool.name}: {tool.description}")
    return [
        {
            "role": "system",
            "content": (
                "Trả lời đúng một từ. CO nếu có công cụ nào thực hiện được yêu cầu, hoặc yêu cầu "
                "thiếu thông tin nhưng thuộc phạm vi của công cụ. KHONG nếu không công cụ nào liên quan."
            ),
        },
        {
            "role": "user",
            "content": "Các công cụ đã cài:\n" + "\n".join(lines) + f"\nYêu cầu: {transcript}",
        },
    ]


def in_scope(llm, hyps, installed_tools, all_tools, ctx, log=None) -> tuple:
    """Trả (bool, dict debug)."""
    transcript = ""
    for hyp in hyps or []:
        text = getattr(hyp, "text", "") or ""
        if text.strip():
            transcript = text
            break
    debug = {"transcript": transcript, "mode": "bm25+llm"}
    if not transcript.strip():
        debug["decision"] = "empty_transcript"
        return False, debug

    feats = bm25_scope_features(transcript, installed_tools or {}, all_tools or {})
    debug.update(feats)

    if (feats["ratio"] >= config.SCOPE_SKIP_LLM_IF_RATIO_GE
            and feats["coverage"] >= config.SCOPE_COVERAGE_THRESHOLD):
        debug["decision"] = "in_scope_by_ratio"
        return True, debug

    answer = ""
    if llm is not None and getattr(llm, "available", False):
        calls, text, _ = llm.generate(scope_llm_prompt(transcript, installed_tools or {}), tools=None,
                                      max_tokens=3, log=log)
        answer = (text or "").strip().upper()
    debug["llm_answer"] = answer

    if "KHONG" in answer:
        out_of_scope = (feats["ratio"] < config.SCOPE_RATIO_THRESHOLD
                        or feats["coverage"] < config.SCOPE_COVERAGE_THRESHOLD)
    elif answer.startswith("CO") or answer in ("CÓ", "CO.", "CO!"):
        out_of_scope = False
    else:
        # LLM không trả lời được (chưa cấu hình / lỗi) ⇒ quyết định bằng tín hiệu từ vựng
        out_of_scope = (feats["ratio"] < config.SCOPE_RATIO_THRESHOLD
                        or feats["coverage"] < config.SCOPE_COVERAGE_THRESHOLD)
    debug["decision"] = "out_of_scope" if out_of_scope else "in_scope"
    return (not out_of_scope), debug
