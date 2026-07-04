"""Разовая простановка даты актуализации для уже загруженных узлов —
до этого патча loaded_at писался не на все MERGE. Безопасно перезапускать:
трогает только узлы без loaded_at.

    python scripts/stamp_freshness.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.graph.loader import GraphStore  # noqa: E402


def main():
    store = GraphStore()
    with store.driver.session() as s:
        res = s.run(
            "MATCH (n) WHERE n.loaded_at IS NULL "
            "SET n.loaded_at = toString(datetime()) RETURN count(n) AS n"
        ).single()
        print(f"Проставлена дата актуализации: {res['n']} узлов")
    store.close()


if __name__ == "__main__":
    main()
