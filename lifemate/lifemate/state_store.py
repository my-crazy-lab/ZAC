"""Kho trạng thái: gom mọi kết quả `env.call` thành snapshot / entities / ids (EXECUTION-PLAN.md §8.6).

R4: dữ liệu app chỉ lấy được qua tool đọc — `StateStore` là nơi duy nhất biết ID.
"""
import json
import re

from lifemate.datatypes import Entity

_ISO_DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2})?")
_ALL_DIGITS = re.compile(r"^\d+$")


def args_key(args: dict) -> str:
    return json.dumps(args or {}, sort_keys=True, ensure_ascii=False)


class StateStore:
    def __init__(self):
        self.snapshot = {}            # "tool|{args}" → result
        self.entities = {}            # (collection, id) → Entity
        self.ids = {}                 # collection → set(id)
        self.collections_read = set()  # collection đã xuất hiện trong kết quả
        self.executed = []            # (tool, args_key)

    # ------------------------------------------------------------------
    def ingest(self, tool: str, args: dict, result: dict) -> None:
        self.snapshot[f"{tool}|{args_key(args)}"] = result
        self.executed.append((tool, args_key(args)))
        if not isinstance(result, dict):
            return
        if result.get("ok") is not True:
            return
        self._walk(result, None, tool)

    def _walk(self, node, parent_key, tool):
        if isinstance(node, dict):
            for key, value in node.items():
                if isinstance(value, list):
                    self.collections_read.add(key)
                    for item in value:
                        if isinstance(item, dict):
                            self._add_entity(key, item, tool)
                            self._walk(item, key, tool)
                        else:
                            self._walk(item, key, tool)
                elif isinstance(value, dict):
                    if "id" in value:
                        self._add_entity(key, value, tool)
                    self._walk(value, key, tool)
        elif isinstance(node, list):
            for item in node:
                self._walk(item, parent_key, tool)

    def _add_entity(self, collection: str, item: dict, tool: str):
        raw_id = item.get("id")
        if raw_id is None or isinstance(raw_id, bool):
            return
        if not isinstance(raw_id, (str, int, float)):
            return
        ident = str(raw_id)
        fields = {}
        names = []
        for key, value in item.items():
            if key == "id":
                continue
            if isinstance(value, str):
                fields[key] = value
                if _is_name(value):
                    names.append(value)
        entity = Entity(id=ident, collection=collection, fields=fields, names=names, source_tool=tool)
        self.entities[(collection, ident)] = entity
        self.ids.setdefault(collection, set()).add(ident)
        self.ids.setdefault("*", set()).add(ident)

    # ------------------------------------------------------------------
    def has_called(self, tool: str, args: dict) -> bool:
        key = args_key(args)
        for name, akey in self.executed:
            if name == tool and akey == key:
                return True
        return False

    def ids_for(self, coll: str) -> set:
        if coll in self.ids:
            return set(self.ids[coll])
        from lifemate import config
        if getattr(config, "XREF_MODE", "strict") == "lenient":
            all_ids = set()
            for ids in self.ids.values():
                all_ids |= ids
            return all_ids
        return set()

    def entity_list(self) -> list:
        return list(self.entities.values())

    def entities_in(self, collection: str) -> list:
        return [e for (coll, _), e in self.entities.items() if coll == collection]


def _is_name(value: str) -> bool:
    if not isinstance(value, str):
        return False
    v = value.strip()
    if not v or len(v) > 80:
        return False
    if _ISO_DATETIME.match(v):
        return False
    if _ALL_DIGITS.match(v) and len(v) > 6:
        return False
    return True
