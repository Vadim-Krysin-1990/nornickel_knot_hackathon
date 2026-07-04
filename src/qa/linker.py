"""Линковка упоминаний на узлы графа: rapidfuzz по name + aliases.
Критично для сплавов: "ВТ6" == "Ti-6Al-4V", "ЭП718" == "ХН45МВТЮБР".
"""
from __future__ import annotations

from rapidfuzz import fuzz, process

from ..graph.queries import GraphQueries


class EntityLinker:
    def __init__(self, gq: GraphQueries):
        self.gq = gq
        self._index: dict[str, list[tuple[str, str, str]]] = {}  # label -> [(вариант, id, name)]
        self.refresh()

    def refresh(self):
        self._index = {}
        for row in self.gq.entity_names():
            label = row["label"]
            variants = [row["name"]] + list(row.get("aliases") or [])
            bucket = self._index.setdefault(label, [])
            for v in variants:
                if v:
                    bucket.append((str(v), row["id"], row["name"]))

    def link(self, mention: str | None, label: str, threshold: int = 72) -> dict | None:
        if not mention:
            return None
        bucket = self._index.get(label, [])
        if not bucket:
            return None
        choices = [b[0] for b in bucket]
        hit = process.extractOne(mention, choices, scorer=fuzz.WRatio)
        if hit and hit[1] >= threshold:
            _, score, idx = hit
            variant, node_id, name = bucket[idx]
            return {"id": node_id, "name": name, "matched": variant, "score": score}
        return None
