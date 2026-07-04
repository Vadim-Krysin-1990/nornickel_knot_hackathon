"""Вопрос на естественном языке -> структурный интент."""
from __future__ import annotations

from .. import llm

INTENT_SYSTEM = """Ты — парсер вопросов к графу знаний по горно-металлургической отрасли
(гидрометаллургия, пирометаллургия, обогащение, экология).
Верни СТРОГО JSON:
{
  "intent": "effects" | "timeline" | "gaps" | "contradictions" | "general",
  "material": "строка или null",   // материал/вещество (никель, католит, шахтная вода...)
  "property": "строка или null",   // показатель (извлечение, сухой остаток, выход...)
  "mode_hint": "строка или null",  // процесс/режим (выщелачивание, электроэкстракция...)
  "geography": "строка или null",  // "РФ" | "зарубеж" | страна — если вопрос про практику региона
  "equipment": "строка или null",
  "lab": "строка или null"
}
intent: effects — "что делали по X при Y, эффект на Z" / "какие методы применялись";
timeline — история работ; gaps — про пробелы/что не исследовано;
contradictions — про противоречия/разногласия в данных; general — всё остальное."""


def parse_intent(question: str) -> dict:
    if llm.has_llm():
        try:
            data = llm.chat_json(
                [
                    {"role": "system", "content": INTENT_SYSTEM},
                    {"role": "user", "content": question},
                ]
            )
            data.setdefault("intent", "general")
            return data
        except Exception:
            pass
    return _heuristic(question)


def _heuristic(question: str) -> dict:
    q = question.lower()
    intent = "effects"
    if any(w in q for w in ("пробел", "не исследован", "не изуч", "gap")):
        intent = "gaps"
    elif any(w in q for w in ("истори", "хронолог", "таймлайн", "когда")):
        intent = "timeline"
    elif any(w in q for w in ("противореч", "разноглас", "конфликт", "расхожден")):
        intent = "contradictions"
    geography = None
    if any(w in q for w in ("росси", "отечествен", " рф", "рф ")):
        geography = "РФ"
    elif any(w in q for w in ("зарубеж", "миров", "иностранн")):
        geography = "зарубеж"
    return {
        "intent": intent,
        "material": None,
        "property": None,
        "mode_hint": None,
        "geography": geography,
        "equipment": None,
        "lab": None,
        "_fallback": True,
        "_raw": question,
    }
