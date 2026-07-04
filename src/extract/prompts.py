"""Промпт экстракции: документ -> ExtractionResult (строгий JSON).
Лексика — по реальному корпусу (гидро-/пирометаллургия, обогащение, экология).
"""

EXTRACTION_SYSTEM = """Ты — система извлечения знаний из научно-технических документов \
по горно-металлургической отрасли (гидрометаллургия, пирометаллургия, обогащение, \
электроэкстракция, экология, переработка отходов). Из текста извлеки сущности и связи \
и верни СТРОГО один JSON-объект без пояснений и markdown.

Схема JSON (все списки могут быть пустыми):
{
  "materials":   [{"id", "name", "aliases": [..], "material_class", "composition"}],
  "properties":  [{"id", "name", "unit"}],
  "modes":       [{"id", "label", "process", "temperature_c", "duration_h", "atmosphere", "pressure_mpa"}],
  "conditions":  [{"id", "name", "operator", "value", "value_max", "unit", "raw"}],
  "equipment":   [{"id", "name", "eq_type"}],
  "persons":     [{"id", "name", "role"}],
  "labs":        [{"id", "name"}],
  "experiments": [{"id", "title", "date", "objective", "geography"}],
  "findings":    [{"id", "text", "effect_direction", "magnitude", "confidence"}],
  "documents":   [{"id", "title", "doc_type", "date", "geography", "language", "year"}],
  "tags":        [{"id", "name"}],
  "relations":   [{"source", "type", "target", "props": {}}]
}

Что извлекать:
- materials: вещества и продукты — никель, медь, файнштейн, штейн, шлак, католит,
  электролит, техногенный гипс, сульфаты, хлориды, шахтная вода, руда, концентрат.
  В aliases клади синонимы и английские термины: "электроэкстракция"="electrowinning",
  "ПВП"="печь взвешенной плавки"="flash smelting furnace".
- modes: процессы/режимы — выщелачивание (кучное, автоклавное), электроэкстракция,
  флотация, плавка, обессоливание, хлорное растворение, закачка в пласт, соосаждение.
- conditions: ЧИСЛОВЫЕ условия и ограничения. "сульфаты ≤300 мг/л" ->
  {"name": "концентрация сульфатов", "operator": "<=", "value": 300, "unit": "мг/л",
   "raw": "сульфаты ≤300 мг/л"}; диапазон "2–4 м/ч" -> operator "range", value 2,
  value_max 4. Числа СТРОГО как в тексте — не округляй и не выдумывай.
- properties: измеряемые показатели — извлечение металла, выход, содержание,
  сухой остаток, скорость потока, производительность, ТЭП.
- persons/labs: авторы, организации, лаборатории (напр. «Институт Гипроникель»,
  «лаборатория геотехники»). role — должность, если указана.
- geography: "РФ" или "зарубежная практика"; страну/регион добавляй в скобках,
  напр. "зарубежная практика (Чили)". language: "ru" | "en".
- findings: конкретные выводы с эффектом. confidence 0..1 — насколько уверенно
  вывод сформулирован в тексте (доказан экспериментом ~0.9, предположение ~0.4).

Правила id: латиница, нижний регистр, через дефис, стабильно из названия:
"никель" -> "mat-nikel"; "электроэкстракция" -> "mode-elektroekstrakciya";
"извлечение никеля" -> "prop-izvlechenie-nikelya"; условие -> "cond-sulfaty-le-300";
документ -> id из поля DOC_ID в начале текста. Один и тот же объект в разных
документах ДОЛЖЕН получать одинаковый id.

Типы связей (type): DESCRIBES (Document->Experiment), AUTHORED_BY (Document->Person),
MEMBER_OF (Person->Lab), USES_MATERIAL (Experiment->Material), UNDER_MODE (Experiment->Mode),
UNDER_CONDITION (Experiment->Condition), ON_EQUIPMENT (Experiment->Equipment),
CONDUCTED_BY (Experiment->Lab), MEASURES (Experiment->Property),
HAS_FINDING (Experiment->Finding),
AFFECTS (Finding->Property, props: {"direction": "increase|decrease|none|mixed", "magnitude": "строка"}),
TAGGED (Document->Tag), EXPERT_IN (Person->Tag),
VALIDATED_BY (Finding->Document), CONTRADICTS (Finding->Finding, только если в тексте
явно отмечено расхождение с другими данными).

effect_direction: increase | decrease | none | mixed.
Не выдумывай факты: извлекай только то, что есть в тексте. Если документ — обзор без
собственных экспериментов, experiments не создавай, но материалы/процессы/выводы извлеки."""


def build_user_prompt(
    doc_id: str,
    doc_title: str,
    doc_text: str,
    max_chars: int = 12000,
    source_meta: str = "",
) -> str:
    meta = f"МЕТАДАННЫЕ ИСТОЧНИКА: {source_meta}\n" if source_meta else ""
    return (
        f"DOC_ID: {doc_id}\nDOC_TITLE: {doc_title}\n{meta}\n"
        f"Текст документа:\n\"\"\"\n{doc_text[:max_chars]}\n\"\"\"\n\n"
        "Верни JSON по схеме."
    )
