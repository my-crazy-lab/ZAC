"""Nạp & chuẩn hoá tools catalog (EXECUTION-PLAN.md §8.4).

Không hard-code tên app/tool: mọi thứ đọc từ catalog của split.
"""
import difflib
import re

from lifemate.datatypes import Tool

ASK_TOOL_NAME = "sys.ask_missing_info"

_FALLBACK_ASK = {
    "name": ASK_TOOL_NAME,
    "kind": "meta",
    "description": "Báo các tham số bắt buộc còn thiếu của một tool",
    "parameters": {
        "type": "object",
        "properties": {
            "tool_name": {"type": "string"},
            "params": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["tool_name", "params"],
    },
    "returns": "",
    "app": "sys",
}


def _one_of_groups(parameters: dict) -> list:
    """Chuẩn hoá `x-one-of` (mức parameters lẫn mức property) thành list nhóm."""
    groups = []
    params = parameters or {}
    raw = params.get("x-one-of")
    if isinstance(raw, list):
        for group in raw:
            if isinstance(group, str):
                groups.append([group])
            elif isinstance(group, list):
                names = [g for g in group if isinstance(g, str)]
                if names:
                    groups.append(names)
    props = params.get("properties") or {}
    for prop, spec in props.items():
        if not isinstance(spec, dict):
            continue
        raw_p = spec.get("x-one-of")
        if isinstance(raw_p, list):
            names = [g for g in raw_p if isinstance(g, str)]
            if prop in names:
                names = [g for g in names if g != prop]
            if names:
                groups.append([prop] + names if prop not in names else names)
    return groups


def _strip_accents(text: str) -> str:
    import unicodedata
    if not isinstance(text, str):
        return ""
    text = "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")
    return text.replace("đ", "d").replace("Đ", "D").lower()


def _singular(text: str) -> str:
    if text.endswith("ies") and len(text) > 4:
        return text[:-3] + "y"
    if text.endswith("es") and len(text) > 3:
        return text[:-2]
    if text.endswith("s") and len(text) > 2:
        return text[:-1]
    return text


class Catalog:
    """Catalog của một split: toàn bộ tool + lọc theo `installed_apps`."""

    def __init__(self, path: str):
        import json
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        self.raw = data
        self._all = {}
        for app in data.get("apps", []):
            app_id = app.get("id") or ""
            for tool in app.get("tools", []):
                parameters = tool.get("parameters") or {}
                props = parameters.get("properties") or {}
                self._all[tool["name"]] = Tool(
                    name=tool["name"],
                    app=tool.get("app") or app_id,
                    kind=tool.get("kind") or "write",
                    description=tool.get("description") or "",
                    app_name_vi=app.get("name_vi") or "",
                    app_description=app.get("description") or "",
                    returns=tool.get("returns") or "",
                    parameters=parameters,
                    required=list(parameters.get("required") or []),
                    props=props,
                    one_of=_one_of_groups(parameters),
                )

    def all_tools(self) -> dict:
        """Toàn catalog (dùng cho scope)."""
        return dict(self._all)

    def tools_for(self, installed_apps: dict) -> dict:
        """Tool được phép gọi trong mẫu: thuộc app đã cài và (nếu có) nằm trong danh sách tool của app."""
        out = {}
        installed_apps = installed_apps or {}
        for app_id, spec in installed_apps.items():
            names = None
            if isinstance(spec, dict):
                raw = spec.get("tools")
            else:
                raw = spec
            if isinstance(raw, list) and raw:
                names = set()
                for item in raw:
                    if isinstance(item, str):
                        names.add(item)
                    elif isinstance(item, dict) and isinstance(item.get("name"), str):
                        names.add(item["name"])
            for name, tool in self._all.items():
                if tool.app != app_id:
                    continue
                if names is not None and name not in names:
                    continue
                out[name] = tool
        if ASK_TOOL_NAME not in out:
            ask = self._all.get(ASK_TOOL_NAME)
            if ask is not None:
                out[ASK_TOOL_NAME] = ask
            else:
                out[ASK_TOOL_NAME] = Tool(
                    name=_FALLBACK_ASK["name"],
                    app="sys",
                    kind="meta",
                    description=_FALLBACK_ASK["description"],
                    app_name_vi="Hệ thống",
                    app_description="",
                    returns="",
                    parameters=_FALLBACK_ASK["parameters"],
                    required=list(_FALLBACK_ASK["parameters"]["required"]),
                    props=_FALLBACK_ASK["parameters"]["properties"],
                    one_of=[],
                )
        return out


def to_llm_tools(tools: dict) -> list:
    """Chuyển sang lược đồ function của OpenAI: bỏ khóa `x-`, ghi chú thêm vào description."""
    out = []
    for name, tool in tools.items():
        params = {}
        for key, value in (tool.parameters or {}).items():
            if key.startswith("x-"):
                continue
            if key == "properties" and isinstance(value, dict):
                props = {}
                for pname, pspec in value.items():
                    if not isinstance(pspec, dict):
                        props[pname] = pspec
                        continue
                    pspec = dict(pspec)
                    notes = []
                    if "x-ref" in pspec:
                        notes.append("(ID phải lấy từ dữ liệu ứng dụng đã đọc)")
                    if pspec.get("x-match") == "fuzzy":
                        notes.append("(văn bản tự do: dùng đúng từ khóa người dùng nói)")
                    pspec = {k: v for k, v in pspec.items() if not k.startswith("x-")}
                    if notes:
                        base = pspec.get("description") or ""
                        pspec["description"] = (base + " " + " ".join(notes)).strip()
                    props[pname] = pspec
                params["properties"] = props
            else:
                params[key] = value
        description = tool.description or ""
        if tool.one_of:
            names = ", ".join(" | ".join(g) for g in tool.one_of)
            description = f"{description} Cần ít nhất một trong: {names}.".strip()
        out.append({
            "type": "function",
            "function": {
                "name": tool.name,
                "description": description,
                "parameters": params or {"type": "object", "properties": {}},
            },
        })
    return out


def resolve_tool_name(name: str, tools: dict):
    """Chuẩn hoá tên tool: khớp chính xác → `__`/`/` → bỏ ký tự lạ → close match."""
    if not isinstance(name, str) or not name:
        return None
    if name in tools:
        return name
    candidate = name.replace("__", ".").replace("/", ".")
    if candidate in tools:
        return candidate
    flat = re.sub(r"[^a-z0-9]", "", candidate.lower())
    exact = [t for t in tools if re.sub(r"[^a-z0-9]", "", t.lower()) == flat]
    if len(exact) == 1:
        return exact[0]
    matches = difflib.get_close_matches(candidate, list(tools.keys()), n=1, cutoff=0.9)
    if matches:
        return matches[0]
    return None


def readers_for(coll: str, tools: dict, ref_sources=None) -> list:
    """Tool đọc có thể trả về collection `coll`."""
    if not coll:
        return []
    tools = tools or {}
    ref_sources = ref_sources or {}
    key = _singular(_strip_accents(coll))
    out = []
    for name, tool in tools.items():
        if tool.kind != "read":
            continue
        by_source = False
        src = ref_sources.get(coll) or {}
        if isinstance(src, dict) and name in src:
            by_source = True
        if not by_source:
            hay = _strip_accents(" ".join([tool.name, tool.returns or "", tool.description or ""]))
            if key and key in hay:
                by_source = True
        if by_source:
            out.append(tool)
    out.sort(key=lambda t: (len(t.required or []), t.name))
    return out
