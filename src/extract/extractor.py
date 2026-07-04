"""Экстракция документа в ExtractionResult через LLM + валидация Pydantic."""
from __future__ import annotations

from .. import llm
from ..ontology.schema import DocumentMeta, Experiment, ExtractionResult, Relation
from .prompts import EXTRACTION_SYSTEM, build_user_prompt

# Связи «эксперимента»: если LLM повесил их на документ (типично для обзоров) —
# перевешиваем на гарантированный узел Experiment, иначе цепочка
# (Material)<-[:USES_MATERIAL]-(Experiment)-[:HAS_FINDING]->(Finding) пустеет.
EXP_REL_TYPES = {
    "USES_MATERIAL", "UNDER_MODE", "UNDER_CONDITION",
    "ON_EQUIPMENT", "CONDUCTED_BY", "MEASURES", "HAS_FINDING",
}


def extract_document(
    doc_id: str,
    title: str,
    text: str,
    source_path: str = "",
    source_meta: dict | None = None,
) -> ExtractionResult:
    """source_meta — метаданные из пути файла (категория, журнал, год, география):
    дешёвый контекст для LLM и дефолты для узла Document."""
    meta = source_meta or {}
    meta_str = "; ".join(f"{k}: {v}" for k, v in meta.items() if v)
    data = llm.chat_json(
        [
            {"role": "system", "content": EXTRACTION_SYSTEM},
            {"role": "user", "content": build_user_prompt(doc_id, title, text, source_meta=meta_str)},
        ],
        max_tokens=6000,
    )
    res = ExtractionResult.model_validate(data)

    # Гарантируем узел Document с source_path (для provenance в UI)
    doc = next((d for d in res.documents if d.id == doc_id), None)
    if doc is None:
        doc = DocumentMeta(id=doc_id, title=title, source_path=source_path)
        res.documents.append(doc)
    doc.source_path = doc.source_path or source_path
    # метаданные пути надёжнее LLM — заполняем пропуски
    doc.doc_type = doc.doc_type or meta.get("категория")
    doc.year = doc.year or meta.get("год")
    doc.geography = doc.geography or meta.get("география")

    _ensure_experiment(res, doc_id, title, doc.geography)
    return res


def _ensure_experiment(res: ExtractionResult, doc_id: str, title: str, geography: str | None):
    """Обзор/статья без собственных экспериментов: создаём один узел
    «исследование по документу» и цепляем к нему всё извлечённое."""
    if res.experiments:
        return
    exp_id = f"exp-{doc_id}"
    res.experiments.append(Experiment(id=exp_id, title=title, geography=geography))
    # перевешиваем связи, которые LLM повесил на документ
    for rel in res.relations:
        if rel.source == doc_id and rel.type in EXP_REL_TYPES:
            rel.source = exp_id
    linked = {(r.type, r.target) for r in res.relations if r.source == exp_id}
    for rtype, items in (
        ("USES_MATERIAL", res.materials),
        ("UNDER_MODE", res.modes),
        ("UNDER_CONDITION", res.conditions),
        ("MEASURES", res.properties),
        ("HAS_FINDING", res.findings),
    ):
        for it in items:
            if (rtype, it.id) not in linked:
                res.relations.append(Relation(source=exp_id, type=rtype, target=it.id))
    res.relations.append(Relation(source=doc_id, type="DESCRIBES", target=exp_id))
