"""Бэкфилл уже загруженного графа: LLM в обзорах вешает экспериментальные связи
прямо на Document, из-за чего цепочка EFFECTS_CY пуста. Создаём Experiment на
документ и перевешиваем связи. Идемпотентно, экстракция не нужна.

    python scripts/backfill_experiments.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.graph.loader import GraphStore  # noqa: E402

REL_TYPES = ["USES_MATERIAL", "UNDER_MODE", "UNDER_CONDITION",
             "ON_EQUIPMENT", "CONDUCTED_BY", "MEASURES", "HAS_FINDING"]

MOVE_CY = """
MATCH (d:Document)-[r:{rt}]->(x)
MERGE (e:Experiment {{id: 'exp-' + d.id}})
  ON CREATE SET e.title = d.title, e.date = d.date, e.geography = d.geography
MERGE (d)-[:DESCRIBES]->(e)
MERGE (e)-[:{rt}]->(x)
DELETE r
RETURN count(*) AS moved
"""

# Findings, у которых нет ни одного эксперимента, но есть документ-источник
# через VALIDATED_BY — тоже подцепим (редкий случай)
ORPHAN_FINDINGS_CY = """
MATCH (f:Finding)-[:VALIDATED_BY]->(d:Document)
WHERE NOT (:Experiment)-[:HAS_FINDING]->(f)
MERGE (e:Experiment {id: 'exp-' + d.id})
  ON CREATE SET e.title = d.title, e.date = d.date, e.geography = d.geography
MERGE (d)-[:DESCRIBES]->(e)
MERGE (e)-[:HAS_FINDING]->(f)
RETURN count(*) AS moved
"""


def main():
    store = GraphStore()
    with store.driver.session() as s:
        total = 0
        for rt in REL_TYPES:
            moved = s.run(MOVE_CY.format(rt=rt)).single()["moved"]
            total += moved
            print(f"{rt}: перевешено {moved}")
        orphans = s.run(ORPHAN_FINDINGS_CY).single()
        print(f"orphan findings: {orphans['moved'] if orphans else 0}")
        n_exp = s.run("MATCH (e:Experiment) RETURN count(e) AS n").single()["n"]
        print(f"\nИтого перевешено связей: {total}; экспериментов в графе: {n_exp}")
    store.close()


if __name__ == "__main__":
    main()
