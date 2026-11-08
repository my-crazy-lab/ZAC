"""Local, typed graph for README-driven business schema mapping.

This is deliberately not a graph database: the graph is a compact, deterministic
intermediate representation used to build prompts and validate mappings.
"""

from __future__ import annotations

import hashlib
from typing import Any

from text.normalize import nd
from schema.mapper import parse_readme_facts


def _id(kind: str, *parts: object) -> str:
    raw = "|".join([kind, *(str(p) for p in parts)])
    return f"{kind}:{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:12]}"


def build_business_graph(tables: list[Any], readme: str,
                         mapping: dict[str, Any]) -> dict[str, Any]:
    """Build nodes/edges from real tables, README facts, and chosen mapping."""
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, str]] = []

    def node(kind: str, name: str, **props: Any) -> str:
        nid = _id(kind, name)
        nodes.append({"id": nid, "kind": kind, "name": name, **props})
        return nid

    def edge(source: str, predicate: str, target: str) -> None:
        edges.append({"source": source, "predicate": predicate, "target": target})

    business = node("business", "current")
    table_ids: dict[str, str] = {}
    for table in tables:
        table_name = str(table.name)
        tid = node("table", table_name, source=str(getattr(table, "source", "")),
                   columns=[str(c) for c in table.df.columns])
        table_ids[table_name] = tid
        edge(business, "has_table", tid)

    entities = (mapping or {}).get("entities", {})
    for entity, info in sorted(entities.items()):
        canonical = node("entity", entity)
        table_names = info.get("tables") or [info.get("table", "")]
        for table_name in table_names:
            if table_name in table_ids:
                edge(table_ids[table_name], "maps_to", canonical)
        for role, column in sorted((info.get("cols") or {}).items()):
            table_name = info.get("table", "")
            if table_name not in table_ids:
                continue
            col_id = node("column", f"{table_name}.{column}", role=role)
            edge(table_ids[table_name], "has_column", col_id)
            edge(col_id, "represents", f"role:{role}")

    facts = parse_readme_facts(readme)
    rule_nodes: list[dict[str, str]] = []
    for convention in facts.get("conventions", []):
        rid = node("rule", convention)
        edge(business, "has_rule", rid)
        rule_nodes.append({"id": rid, "text": convention})

    return {"nodes": nodes, "edges": edges, "facts": facts,
            "rules": rule_nodes}


def validate_business_graph(graph: dict[str, Any], mapping: dict[str, Any]) -> list[str]:
    """Return mapping references that cannot be resolved to real graph nodes."""
    node_names = {(n["kind"], n["name"]) for n in graph.get("nodes", [])}
    errors: list[str] = []
    for entity, info in ((mapping or {}).get("entities", {}) or {}).items():
        for table_name in info.get("tables") or [info.get("table", "")]:
            if table_name and ("table", table_name) not in node_names:
                errors.append(f"entity {entity}: missing table {table_name}")
        table_name = info.get("table", "")
        columns = next((n.get("columns", []) for n in graph.get("nodes", [])
                        if n["kind"] == "table" and n["name"] == table_name), [])
        for role, column in (info.get("cols") or {}).items():
            if column not in columns:
                errors.append(f"entity {entity}: missing column {table_name}.{column} ({role})")
    return errors


def semantic_graph_issues(question: str, graph: dict[str, Any], spec: Any = None) -> list[str]:
    """Check that a candidate's business meaning has graph-backed sources."""
    q = nd(question)
    roles = {n.get("role") for n in graph.get("nodes", []) if n.get("kind") == "column"}
    entities = {n.get("name") for n in graph.get("nodes", []) if n.get("kind") == "entity"}
    rules = " ".join(nd(r.get("text", "")) for r in graph.get("rules", []))
    issues: list[str] = []

    if any(x in q for x in ("doanh thu", "doanh so", "tong tien", "ban duoc bao nhieu tien")):
        if not ({"line_amount", "order_total"} & roles):
            issues.append("revenue không có nguồn tiền line_amount/order_total")
    if any(x in q for x in ("so luong", "ban chay", "san pham ban")):
        if "lines" not in entities or not ({"qty", "qty_base"} & roles):
            issues.append("qty không có nguồn dòng hàng qty/qty_base")
    if any(x in q for x in ("so don", "bao nhieu don", "don hang")):
        if "orders" not in entities and not ({"order_id", "order_date"} <= roles):
            issues.append("orders thiếu order_id và order_date")
    if spec is not None and getattr(spec, "output", "") == "percent":
        intent = getattr(spec, "intent", "")
        params = getattr(spec, "params", {}) or {}
        if intent not in {"cancel_rate", "group_share", "compare_periods"} \
                and not any(k in params for k in ("denominator", "base", "total")):
            issues.append("percent chưa có numerator/denominator rõ ràng")
    if any(x in q for x in ("don huy", "don bi huy", "huy don", "cancel")) \
            and "status_raw" not in roles and "huy" not in rules:
        issues.append("is_cancelled thiếu status rule")
    if any(x in q for x in ("phi ship", "phi van chuyen", "shipping")) \
            and "shipping_fee" not in roles:
        issues.append("shipping_fee thiếu nguồn hoặc README rule")
    if any(x in q for x in ("voucher", "dung diem", "diem")) \
            and "order_voucher" not in roles:
        issues.append("voucher/order_discount thiếu nguồn hoặc README rule")
    if any(x in q for x in ("quy doi", "don vi co ban", "so luong le")) \
            and not ({"qty_base", "unit_factor"} & roles):
        issues.append("qty_base thiếu unit conversion rule")
    return issues


def render_graph_card(graph: dict[str, Any], question: str = "",
                      max_rules: int = 8) -> str:
    """Render only the compact graph facts useful to an SLM prompt."""
    lines = ["[BUSINESS GRAPH]", "Use only these README-backed mappings and rules."]
    by_entity: dict[str, list[str]] = {}
    for edge in graph.get("edges", []):
        if edge["predicate"] != "maps_to":
            continue
        source = next((n for n in graph["nodes"] if n["id"] == edge["source"]), None)
        target = next((n for n in graph["nodes"] if n["id"] == edge["target"]), None)
        if source and target:
            by_entity.setdefault(target["name"], []).append(source["name"])
    q = nd(question)
    keywords = {
        "orders": ("doanh thu", "don hang", "hoa don", "so don", "don"),
        "lines": ("hang", "san pham", "so luong", "ban chay", "doanh thu"),
        "customers": ("khach",), "payments": ("thanh toan", "thu tien", "cong no", "no"),
        "inventory": ("ton kho", "ton", "het hang"), "imports": ("nhap hang", "nhap"),
        "deliveries": ("giao hang", "luot giao"),
    }
    selected = {entity for entity, words in keywords.items()
                if any(word in q for word in words)}
    selected_tables = {table for entity, tables in by_entity.items()
                       if not selected or entity in selected for table in tables}
    for node in sorted((n for n in graph.get("nodes", []) if n["kind"] == "table"
                        and n["name"] in selected_tables), key=lambda n: n["name"]):
        lines.append(f"- table {node['name']}: {', '.join(node.get('columns', [])[:16])}")
    for entity, table_names in sorted(by_entity.items()):
        if selected and entity not in selected:
            continue
        lines.append(f"- entity {entity}: tables={', '.join(sorted(set(table_names)))}")
        for node in graph.get("nodes", []):
            if node["kind"] == "column" and any(
                    node["name"].startswith(f"{table}.") for table in table_names):
                lines.append(f"  - {node.get('role', 'column')}: {node['name']}")
    for rule in graph.get("rules", [])[:max_rules]:
        text = nd(rule["text"])
        if not selected or any(word in text for words in keywords.values() for word in words):
            lines.append(f"- rule: {rule['text']}")
    if len(lines) == 2:
        lines.append("- no question-specific mapping found")
    return "\n".join(lines)


__all__ = ["build_business_graph", "validate_business_graph", "render_graph_card"]
