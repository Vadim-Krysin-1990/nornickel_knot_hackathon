"""Загрузка корпуса в граф и векторное хранилище.

Быстрый старт (без LLM и без эмбеддингов, только граф):
    python scripts/load_all.py --no-embed

Полный прогон с LLM-экстракцией вместо ground truth:
    python scripts/load_all.py --use-llm
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.graph.loader import GraphStore  # noqa: E402
from src.ontology.schema import ExtractionResult  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=str(ROOT / "data" / "synthetic"))
    ap.add_argument("--use-llm", action="store_true", help="экстракция документов через LLM вместо ground truth")
    ap.add_argument("--no-embed", action="store_true", help="пропустить эмбеддинги/Qdrant")
    ap.add_argument("--wipe", action="store_true", help="очистить граф перед загрузкой")
    args = ap.parse_args()

    data_dir = Path(args.data_dir)
    store = GraphStore()
    if args.wipe:
        print("Очищаю граф...")
        store.wipe()
    store.init_schema()

    # --- Граф ---
    n = 0
    if args.use_llm:
        from src.extract.extractor import extract_document
        from src.ingest.parsers import iter_documents, read_document

        for p in iter_documents(data_dir / "docs"):
            text = read_document(p)
            res = extract_document(doc_id=p.stem, title=p.stem, text=text, source_path=str(p))
            store.load(res)
            n += 1
            print(f"  [LLM] {p.name}: +{len(res.relations)} связей")
    else:
        for p in sorted((data_dir / "truth").glob("*.json")):
            res = ExtractionResult.model_validate_json(p.read_text(encoding="utf-8"))
            store.load(res)
            n += 1
    print(f"Граф: загружено {n} документов")

    # --- Векторы ---
    if not args.no_embed:
        from src.ingest.chunker import chunk_text
        from src.ingest.parsers import iter_documents, read_document
        from src.search import vectorstore

        vectorstore.ensure_collection()
        for p in iter_documents(data_dir / "docs"):
            chunks = chunk_text(read_document(p))
            vectorstore.upsert_chunks(doc_id=p.stem, source_path=str(p), chunks=chunks)
        print("Qdrant: чанки загружены")
    else:
        print("Эмбеддинги пропущены (--no-embed)")

    store.close()
    print("Готово. Проверь: http://localhost:7474 (neo4j / hackathon2026)")


if __name__ == "__main__":
    main()
