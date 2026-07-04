"""Диагностика графа: узлы, связи, паттерны, изолированные узлы, готовность QA-цепочки.

    python scripts/graph_stats.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.graph.queries import GraphQueries  # noqa: E402


def main():
    gq = GraphQueries()
    print("=== Узлы ===")
    for r in gq._run("MATCH (n) RETURN labels(n)[0] AS label, count(*) AS n ORDER BY n DESC"):
        print(f"  {r['label']}: {r['n']}")
    print("=== Связи ===")
    for r in gq._run("MATCH ()-[r]->() RETURN type(r) AS t, count(*) AS n ORDER BY n DESC"):
        print(f"  {r['t']}: {r['n']}")
    print("=== Топ паттернов ===")
    for r in gq._run(
        "MATCH (a)-[r]->(b) RETURN labels(a)[0] + '-[' + type(r) + ']->' + labels(b)[0] AS pat, "
        "count(*) AS n ORDER BY n DESC LIMIT 20"
    ):
        print(f"  {r['pat']}: {r['n']}")
    print("=== Изолированные узлы (не связаны ни с чем) ===")
    for r in gq._run(
        "MATCH (n) WHERE NOT (n)--() RETURN labels(n)[0] AS label, count(*) AS n ORDER BY n DESC"
    ):
        print(f"  {r['label']}: {r['n']}")
    print("=== Готовность QA-цепочки ===")
    row = gq._run(
        "MATCH (m:Material)<-[:USES_MATERIAL]-(e:Experiment)-[:HAS_FINDING]->(f:Finding)"
        "-[:AFFECTS]->(p:Property) RETURN count(*) AS full_chains"
    )[0]
    print(f"  полных цепочек Material<-Experiment->Finding->Property: {row['full_chains']}")
    row = gq._run(
        "MATCH (e:Experiment)-[:HAS_FINDING]->(f:Finding) "
        "WHERE NOT (f)-[:AFFECTS]->() RETURN count(f) AS n"
    )[0]
    print(f"  findings без AFFECTS->Property: {row['n']}")
    gq.store.close()


if __name__ == "__main__":
    main()
