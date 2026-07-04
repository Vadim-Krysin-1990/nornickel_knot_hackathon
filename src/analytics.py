"""Эвристики для дашборда руководителя: бакетинг документов по направлениям
(гидрометаллургия/пирометаллургия/...) по ключевым словам в заголовке/тегах —
в онтологии нет явного поля «домен», поэтому это приближение, а не факт из графа.
Чистый Python, без зависимости от Neo4j — легко тестировать изолированно.
"""
from __future__ import annotations

from collections import Counter

DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "Гидрометаллургия": ["выщелачив", "электроэкстракц", "экстракц", "раствор", "электролит",
                          "сорбц", "осаждени", "гидромет", "католит"],
    "Пирометаллургия": ["плавка", "печь", "штейн", "шлак", "пвп", "конвертир", "обжиг",
                         "пирометалл", "взвешен", "файнштейн"],
    "Обогащение": ["флотаци", "дроблени", "измельчени", "обогащен", "концентрат"],
    "Экология": ["выброс", "очистк", "экологи", "хвостохранил", "загрязн", "атмосфер",
                 "обессолив", "сточн"],
    "Переработка отходов": ["отход", "техноген", "хвост", "утилизац", "вторичн", "гипс"],
    "Геомеханика/горное дело": ["рудник", "выработк", "геомехан", "горн", "шахт", "бурени"],
}


def bucket_domain(title: str | None, doc_type: str | None, tags: list[str] | None) -> str:
    text = " ".join([title or "", doc_type or "", " ".join(tags or [])]).lower()
    best, best_hits = "Прочее", 0
    for domain, keywords in DOMAIN_KEYWORDS.items():
        hits = sum(1 for kw in keywords if kw in text)
        if hits > best_hits:
            best, best_hits = domain, hits
    return best


def domain_counts(doc_rows: list[dict]) -> list[dict]:
    """doc_rows: [{"title","doc_type","tags": [...]}] -> [{"domain","n"}] по убыванию."""
    counter = Counter(
        bucket_domain(r.get("title"), r.get("doc_type"), r.get("tags")) for r in doc_rows
    )
    return [{"domain": k, "n": v} for k, v in counter.most_common()]
