"""Загрузка РЕАЛЬНОГО корпуса кейса в граф + Qdrant.

Корпус (разведка 02.07): 1453 файла / 4.9 ГБ, каталогов-справочников нет —
граф строится LLM-экстракцией. Очереди по ценности:
  P1 — Статьи, Обзоры, Доклады (внутренние документы: авторы, лаборатории)
  P2 — Материалы конференций
  P3 — Журналы (объёмные подшивки — сначала только в векторный индекс)

Примеры:
    python scripts/load_real.py --data-dir "data/real" --dry-run          # манифест без загрузки
    python scripts/load_real.py --data-dir "data/real" --priority 1 --max-docs 30
    python scripts/load_real.py --data-dir "data/real" --priority 2 --no-extract  # только чанки в Qdrant
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.ingest.parsers import clean_text, iter_documents, read_document  # noqa: E402

PRIORITY = {"Статьи": 1, "Обзоры": 1, "Доклады": 1, "Материалы конференций": 2, "Журналы": 3}
MIN_CHARS = 300  # меньше — вероятно скан без текстового слоя -> в OCR-очередь


def doc_meta(p: Path, root: Path) -> dict:
    rel = p.relative_to(root)
    parts = rel.parts
    category = parts[0] if len(parts) > 1 else "прочее"
    sub = parts[1] if len(parts) > 2 else ""
    year_m = re.search(r"\b(19|20)\d{2}\b", str(rel))
    return {
        "категория": category,
        "подраздел": sub,
        "год": int(year_m.group()) if year_m else None,
        "priority": PRIORITY.get(category, 2),
    }


def make_doc_id(p: Path, root: Path) -> str:
    rel = str(p.relative_to(root))
    h = hashlib.md5(rel.encode("utf-8")).hexdigest()[:8]
    stem = re.sub(r"[^0-9a-zA-Zа-яА-ЯёЁ]+", "-", p.stem)[:40].strip("-").lower()
    return f"doc-{h}-{stem}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True, help="корень «Источники информации»")
    ap.add_argument("--priority", type=int, default=1, help="грузить очереди с priority <= N")
    ap.add_argument("--max-docs", type=int, default=0, help="лимит документов (0 = без лимита)")
    ap.add_argument("--no-embed", action="store_true", help="без Qdrant/эмбеддингов")
    ap.add_argument("--no-extract", action="store_true", help="без LLM-экстракции (только чанки)")
    ap.add_argument("--wipe", action="store_true", help="очистить граф перед загрузкой")
    ap.add_argument("--dry-run", action="store_true", help="только манифест manifest.csv")
    ap.add_argument("--only-errors", action="store_true",
                    help="перегнать только FAIL-документы из load_errors.csv")
    ap.add_argument("--by-size", action="store_true",
                    help="сначала крупные файлы (прокси на содержательность) вместо алфавита")
    args = ap.parse_args()

    root = Path(args.data_dir)
    docs = [(p, doc_meta(p, root)) for p in iter_documents(root)]
    docs = [(p, m) for p, m in docs if m["priority"] <= args.priority]
    if args.by_size:
        docs.sort(key=lambda x: (x[1]["priority"], -x[0].stat().st_size))
    else:
        docs.sort(key=lambda x: (x[1]["priority"], str(x[0])))
    if args.only_errors:
        with open("load_errors.csv", encoding="utf-8") as f:
            bad = {row[0] for row in csv.reader(f) if len(row) > 1 and row[1] == "FAIL"}
        docs = [(p, m) for p, m in docs if str(p.relative_to(root)) in bad]
    if args.max_docs:
        docs = docs[: args.max_docs]
    print(f"К обработке: {len(docs)} документов (priority <= {args.priority})")

    if args.dry_run:
        with open("manifest.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["path", "категория", "подраздел", "год", "priority", "size_kb"])
            for p, m in docs:
                w.writerow([p.relative_to(root), m["категория"], m["подраздел"],
                            m["год"], m["priority"], p.stat().st_size // 1024])
        print("Манифест: manifest.csv")
        return

    from src.graph.loader import GraphStore

    store = GraphStore()
    if args.wipe:
        print("Очищаю граф...")
        store.wipe()
    store.init_schema()

    if not args.no_embed:
        from src.ingest.chunker import chunk_text
        from src.search import vectorstore

        vectorstore.ensure_collection()

    if not args.no_extract:
        from src.extract.extractor import extract_document

    ok = skipped = failed = 0
    err_log = open("load_errors.csv", "a", newline="", encoding="utf-8")
    err_w = csv.writer(err_log)
    for i, (p, meta) in enumerate(docs, 1):
        doc_id = make_doc_id(p, root)
        t0 = time.time()
        try:
            text = clean_text(read_document(p))
            if len(text) < MIN_CHARS:
                skipped += 1
                err_w.writerow([p.relative_to(root), "SKIP", "текста нет — вероятно скан (OCR)"])
                print(f"[{i}/{len(docs)}] SKIP (скан?) {p.name}")
                continue
            if not args.no_extract:
                res = None
                for attempt in (1, 2):
                    try:
                        res = extract_document(
                            doc_id=doc_id, title=p.stem, text=text,
                            source_path=str(p.relative_to(root)),
                            source_meta={k: v for k, v in meta.items() if k != "priority"},
                        )
                        break
                    except Exception as e:
                        transient = any(s in str(e).lower() for s in
                                        ("timed out", "timeout", "resolve", "connection"))
                        if attempt == 1 and transient:
                            print(f"    сеть моргнула, повтор через 20с: {str(e)[:80]}")
                            time.sleep(20)
                        else:
                            raise
                store.load(res)
            if not args.no_embed:
                vectorstore.upsert_chunks(
                    doc_id=doc_id, source_path=str(p.relative_to(root)),
                    chunks=chunk_text(text),
                )
            ok += 1
            print(f"[{i}/{len(docs)}] OK {p.name} ({time.time() - t0:.1f}с)")
        except Exception as e:
            failed += 1
            err_w.writerow([p.relative_to(root), "FAIL", str(e)[:200]])
            print(f"[{i}/{len(docs)}] FAIL {p.name}: {e}")
    err_log.close()
    store.close()
    print(f"\nГотово: ok={ok}, skip={skipped}, fail={failed}. Ошибки: load_errors.csv")
    print("Не забудь: POST /relink — обновить справочник entity linking")


if __name__ == "__main__":
    main()
