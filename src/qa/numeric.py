"""Числовые ограничения в вопросе -> сопоставление с Condition-узлами графа.
Регулярка вместо LLM-JSON: детерминированно, работает и без LLM-ключа
(в т.ч. когда LLM недоступна — graceful degradation).
"""
from __future__ import annotations

import re
from math import inf

from rapidfuzz import fuzz

_UNIT = r"мг/л|мг/дм3|мг/дм³|°c|°с|мпа|м/ч|м3/ч|%|г/т|г/л"
_PARAM = r"[а-яёa-z]+(?:\s+[а-яёa-z]+){0,2}"
_STOP = {"по", "для", "при", "в", "с", "до", "от", "на", "и", "не", "а", "но"}

_RANGE_RE = re.compile(
    rf"(?P<param>{_PARAM})?\s*"
    rf"(?P<v1>\d+(?:[.,]\d+)?)\s*[-–—]\s*(?P<v2>\d+(?:[.,]\d+)?)\s*"
    rf"(?P<unit>{_UNIT})?",
    re.IGNORECASE,
)
_LE_RE = re.compile(
    rf"(?P<param>{_PARAM})?\s*"
    rf"(?:≤|<=|не более|не превыша\w*)\s*(?P<v>\d+(?:[.,]\d+)?)\s*"
    rf"(?P<unit>{_UNIT})?",
    re.IGNORECASE,
)
_GE_RE = re.compile(
    rf"(?P<param>{_PARAM})?\s*"
    rf"(?:≥|>=|не менее|от)\s*(?P<v>\d+(?:[.,]\d+)?)\s*"
    rf"(?P<unit>{_UNIT})?",
    re.IGNORECASE,
)


def _num(s: str) -> float:
    return float(s.replace(",", "."))


def _clean_param(raw: str | None) -> str | None:
    words = (raw or "").strip().lower().split()
    while words and words[-1] in _STOP:
        words.pop()
    p = " ".join(words)
    return p if p and len(p) >= 3 else None


# эквивалентные записи одной единицы -> канонический вид (мг/л == мг/дм3 == мг/дм³ — 1 л = 1 дм³)
_UNIT_CANON = {
    "мг/л": "мг/л", "мг/дм3": "мг/л", "мг/дм³": "мг/л",
    "°c": "°c", "°с": "°c",
    "м3/ч": "м3/ч", "м/ч": "м/ч",
    "г/т": "г/т", "г/л": "г/л", "мпа": "мпа", "%": "%",
}


def _units_compatible(u1: str | None, u2: str | None) -> bool:
    """Разные единицы (например, °C и мг/л) не должны считаться пересекающимися
    диапазонами — иначе температура «совпадёт» с концентрацией по числу."""
    if not u1 or not u2:
        return True  # нет данных для проверки -> не блокируем (полнота важнее точности в MVP)
    return _UNIT_CANON.get(u1, u1) == _UNIT_CANON.get(u2, u2)


def extract_numeric_constraints(text: str) -> list[dict]:
    """Достаёт из текста вопроса числовые ограничения: диапазоны и <=/>=.

    Возвращает [{"param": str|None, "operator": "range"|"<="|">=",
    "value": float, "value_max": float|None, "unit": str|None, "raw": str}].
    param=None означает «не удалось надёжно распознать параметр» —
    сопоставление тогда идёт только по значению, без фильтра по имени.
    """
    out: list[dict] = []
    covered: list[tuple[int, int]] = []

    for m in _RANGE_RE.finditer(text):
        span = m.span()
        if any(a <= span[0] < b for a, b in covered):
            continue
        out.append({
            "param": _clean_param(m.group("param")),
            "operator": "range",
            "value": _num(m.group("v1")),
            "value_max": _num(m.group("v2")),
            "unit": (m.group("unit") or "").lower() or None,
            "raw": m.group(0).strip(),
        })
        covered.append(span)

    for rex, op in ((_LE_RE, "<="), (_GE_RE, ">=")):
        for m in rex.finditer(text):
            span = m.span()
            if any(a <= span[0] < b for a, b in covered):
                continue
            out.append({
                "param": _clean_param(m.group("param")),
                "operator": op,
                "value": _num(m.group("v")),
                "value_max": None,
                "unit": (m.group("unit") or "").lower() or None,
                "raw": m.group(0).strip(),
            })
            covered.append(span)

    return out


def _interval(operator: str | None, value: float | None, value_max: float | None):
    if value is None:
        return None
    if operator == "range" and value_max is not None:
        return (min(value, value_max), max(value, value_max))
    if operator in ("<=", "<"):
        return (-inf, value)
    if operator in (">=", ">"):
        return (value, inf)
    if operator == "=":
        return (value, value)
    return None


def _overlaps(a: tuple[float, float], b: tuple[float, float]) -> bool:
    return a[0] <= b[1] and b[0] <= a[1]


def match_conditions(constraints: list[dict], condition_rows: list[dict],
                      name_threshold: int = 55) -> list[dict]:
    """Для каждого Condition-узла графа проверяет, пересекается ли его диапазон
    с диапазоном из вопроса. Если параметр в вопросе не распознан уверенно —
    сравнение идёт по всем условиям (полнота важнее точности для MVP)."""
    if not constraints:
        return []
    matched = []
    for row in condition_rows:
        row_iv = _interval(row.get("operator"), row.get("value"), row.get("value_max"))
        if row_iv is None:
            continue
        row_name = (row.get("name") or "").lower()
        for c in constraints:
            if c["param"] and fuzz.partial_ratio(c["param"], row_name) < name_threshold:
                continue
            if not _units_compatible(c.get("unit"), row.get("unit")):
                continue
            c_iv = _interval(c["operator"], c["value"], c["value_max"])
            if c_iv is None:
                continue
            matched.append({**row, "requested": c["raw"], "fits": _overlaps(c_iv, row_iv)})
    return matched


def filter_conditions(condition_rows: list[dict], name: str | None, operator: str,
                       value: float, value_max: float | None = None,
                       unit: str | None = None) -> list[dict]:
    """Точный поиск по явно заданному условию (форма в UI, не NL-вопрос) —
    та же логика сопоставления, что и у эвристики из вопроса, но без regex."""
    constraint = {
        "param": (name or "").strip().lower() or None,
        "operator": operator, "value": value, "value_max": value_max,
        "unit": (unit or "").strip().lower() or None, "raw": f"{operator} {value}",
    }
    return match_conditions([constraint], condition_rows, name_threshold=40)
