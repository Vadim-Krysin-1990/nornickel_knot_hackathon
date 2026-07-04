"""Онтология "Научного клубка".

Узлы: Material, Property, Mode, Equipment, Person, Lab, Experiment,
Finding, Document, Tag.
Ключевая цепочка под эталонный вопрос трека
("что делали по сплавам X при режиме Y и какой эффект на свойство Z"):

(Material)<-[:USES_MATERIAL]-(Experiment)-[:UNDER_MODE]->(Mode)
(Experiment)-[:HAS_FINDING]->(Finding)-[:AFFECTS {direction}]->(Property)
(Document)-[:DESCRIBES]->(Experiment)
"""
from __future__ import annotations

import re
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class EffectDirection(str, Enum):
    increase = "increase"
    decrease = "decrease"
    none = "none"
    mixed = "mixed"


# LLM на реальном корпусе возвращает вольные значения — нормализуем, а не падаем
_DIRECTION_SYNONYMS = {
    "positive": "increase", "рост": "increase", "повышение": "increase", "увеличение": "increase",
    "negative": "decrease", "снижение": "decrease", "уменьшение": "decrease",
    "нет": "none", "не изменилось": "none", "неоднозначно": "mixed",
}


def _normalize_direction(v):
    if isinstance(v, str):
        vv = v.strip().lower()
        vv = _DIRECTION_SYNONYMS.get(vv, vv)
        if vv not in {"increase", "decrease", "none", "mixed"}:
            return "mixed"
        return vv
    return v


def _coerce_number(v):
    """'200-220 г/дм3' -> 200.0; '≤300 мг/л' -> 300.0; мусор -> None."""
    if isinstance(v, str):
        m = re.search(r"-?\d+(?:[.,]\d+)?", v)
        return float(m.group().replace(",", ".")) if m else None
    return v


class Material(BaseModel):
    id: str
    name: str
    aliases: list[str] = Field(default_factory=list)
    material_class: str | None = None  # сплав / порошок / покрытие ...
    composition: str | None = None


class Property(BaseModel):
    id: str
    name: str
    unit: str | None = None


class Mode(BaseModel):
    """Режим/процесс. label — человекочитаемая нормализация,
    структурные параметры — для фильтров и матрицы пробелов."""
    id: str
    label: str
    process: str | None = None  # выщелачивание / электроэкстракция / флотация / плавка ...
    temperature_c: float | None = None
    duration_h: float | None = None
    atmosphere: str | None = None
    pressure_mpa: float | None = None


class Condition(BaseModel):
    """Числовое условие/ограничение: «сульфаты ≤300 мг/л», «скорость потока 2–4 м/ч».
    operator: <= | >= | = | range (для range заполняются value и value_max)."""
    id: str
    name: str  # параметр: концентрация сульфатов / сухой остаток / скорость циркуляции ...
    operator: str | None = None
    value: float | None = None
    value_max: float | None = None
    unit: str | None = None
    raw: str | None = None  # исходная формулировка из текста

    @field_validator("value", "value_max", mode="before")
    @classmethod
    def _v_num(cls, v):
        return _coerce_number(v)


class Equipment(BaseModel):
    id: str
    name: str
    eq_type: str | None = None


class Person(BaseModel):
    id: str
    name: str
    role: str | None = None


class Lab(BaseModel):
    id: str
    name: str


class Experiment(BaseModel):
    id: str
    title: str
    date: str | None = None  # ISO YYYY-MM-DD
    objective: str | None = None
    status: str | None = None
    geography: str | None = None  # РФ / зарубежная практика; страна, если известна

    @field_validator("date", mode="before")
    @classmethod
    def _v_date(cls, v):
        return str(v) if isinstance(v, (int, float)) else v


class Finding(BaseModel):
    id: str
    text: str
    effect_direction: EffectDirection = EffectDirection.none
    magnitude: str | None = None  # "+12%", "−40 HV" ...
    confidence: float | None = None

    @field_validator("effect_direction", mode="before")
    @classmethod
    def _v_dir(cls, v):
        return _normalize_direction(v)

    @field_validator("magnitude", mode="before")
    @classmethod
    def _v_mag(cls, v):
        return str(v) if isinstance(v, (int, float)) else v


class DocumentMeta(BaseModel):
    id: str
    title: str
    doc_type: str | None = None  # статья / обзор / доклад / журнал / материалы конференции ...
    date: str | None = None
    source_path: str | None = None
    geography: str | None = None  # РФ / зарубежная практика; страна, если известна
    language: str | None = None   # ru / en
    year: int | None = None       # год публикации (из метаданных пути или текста)

    @field_validator("date", mode="before")
    @classmethod
    def _v_date(cls, v):
        return str(v) if isinstance(v, (int, float)) else v

    @field_validator("year", mode="before")
    @classmethod
    def _v_year(cls, v):
        n = _coerce_number(v)
        return int(n) if n else None


class Tag(BaseModel):
    id: str
    name: str


class Relation(BaseModel):
    source: str  # id узла-источника
    type: str    # из RELATION_TYPES
    target: str  # id узла-цели
    props: dict[str, str | float | int] = Field(default_factory=dict)


class ExtractionResult(BaseModel):
    """Единица загрузки в граф — результат экстракции одного документа
    (или ground truth синтетики)."""
    materials: list[Material] = Field(default_factory=list)
    properties: list[Property] = Field(default_factory=list)
    modes: list[Mode] = Field(default_factory=list)
    conditions: list[Condition] = Field(default_factory=list)
    equipment: list[Equipment] = Field(default_factory=list)
    persons: list[Person] = Field(default_factory=list)
    labs: list[Lab] = Field(default_factory=list)
    experiments: list[Experiment] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    documents: list[DocumentMeta] = Field(default_factory=list)
    tags: list[Tag] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)


# поле ExtractionResult -> label узла в Neo4j
ENTITY_LABELS: dict[str, str] = {
    "materials": "Material",
    "properties": "Property",
    "modes": "Mode",
    "conditions": "Condition",
    "equipment": "Equipment",
    "persons": "Person",
    "labs": "Lab",
    "experiments": "Experiment",
    "findings": "Finding",
    "documents": "Document",
    "tags": "Tag",
}

RELATION_TYPES = [
    "DESCRIBES",      # Document -> Experiment
    "AUTHORED_BY",    # Document -> Person
    "MEMBER_OF",      # Person -> Lab
    "USES_MATERIAL",  # Experiment -> Material
    "UNDER_MODE",     # Experiment -> Mode
    "ON_EQUIPMENT",   # Experiment -> Equipment
    "CONDUCTED_BY",   # Experiment -> Lab
    "MEASURES",       # Experiment -> Property
    "HAS_FINDING",    # Experiment -> Finding
    "AFFECTS",        # Finding -> Property  {direction, magnitude}
    "TAGGED",         # Document -> Tag
    "UNDER_CONDITION",  # Experiment -> Condition (числовые условия/ограничения)
    "CONTRADICTS",      # Finding -> Finding (противоречащие выводы)
    "VALIDATED_BY",     # Finding -> Document (вывод подтверждён источником)
    "EXPERT_IN",        # Person -> Tag (область экспертизы)
]
