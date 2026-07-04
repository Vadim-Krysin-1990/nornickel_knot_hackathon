"""GraphRAG-оркестратор: вопрос -> ответ + факты из графа + цитаты из документов.
Работает и без LLM (отдаёт структурированную таблицу фактов) — демо не умрёт без ключа.
"""
from __future__ import annotations

from .. import llm
from ..graph.queries import GraphQueries
from .intent import parse_intent
from .linker import EntityLinker
from .numeric import extract_numeric_constraints, match_conditions

ANSWER_SYSTEM = """Ты — ассистент научной базы знаний R&D Норникеля (горно-металлургическая
отрасль). Отвечай на русском, кратко и по делу, опираясь ТОЛЬКО на переданные факты из графа
и фрагменты документов.
Каждое утверждение помечай источником в квадратных скобках: [doc_id] или [эксперимент: id].
У каждого факта в списке указана строка «источников: N» — используй её как уровень
достоверности: N=1 помечай как «единичное наблюдение», N>=2 — как «подтверждено N
источниками». Никогда не оценивай достоверность на глаз, только по этой цифре.
Если у факта есть «актуально на: <дата>» — это дата последнего обновления факта в базе,
упоминай её, если пользователь спрашивает о свежести данных.
Если факты противоречат друг другу — явно выдели зону разногласий.
Если передан блок «Числовые условия из графа, сопоставленные с запросом» — используй пометки
ПОДХОДИТ/не подходит оттуда напрямую (это пересечение диапазонов, эвристика — предупреди,
что итоговое решение проверяется по первоисточнику). Если такого блока нет, но в вопросе
были числа — поищи совпадения в тексте выводов и magnitude сам и отметь подходит/не подходит.
Если прямого ответа в фактах нет, но среди фрагментов есть релевантные документы —
НЕ отвечай «ничего не найдено»: укажи, в каких документах содержится ответ
(название, видимые разделы/оглавление) и что именно там искать.
Если фактов и релевантных документов нет — прямо скажи, чего не хватает (пробел в данных)."""


class Pipeline:
    def __init__(self):
        self.gq = GraphQueries()
        self.linker = EntityLinker(self.gq)

    def ask(self, question: str, k_chunks: int = 5, geography: str | None = None) -> dict:
        intent = parse_intent(question)
        geo = geography or intent.get("geography")

        mat = self.linker.link(intent.get("material"), "Material")
        prop = self.linker.link(intent.get("property"), "Property")

        rows: list[dict] = []
        if intent["intent"] == "timeline" and mat:
            rows = self.gq.timeline(mat["id"])
        elif intent["intent"] == "gaps":
            rows = [r for r in self.gq.gap_matrix() if r["n_experiments"] == 0]
            if mat:
                rows = [r for r in rows if r["material"] == mat["name"]]
        elif intent["intent"] == "contradictions":
            rows = self.gq.contradictions()
        else:
            rows = self.gq.find_effects(
                material_id=mat["id"] if mat else None,
                property_id=prop["id"] if prop else None,
                mode_hint=intent.get("mode_hint"),
                geography=geo,
            )

        numeric_matches: list[dict] = []
        constraints = extract_numeric_constraints(question)
        if constraints:
            try:
                numeric_matches = match_conditions(constraints, self.gq.all_conditions())
            except Exception:
                numeric_matches = []

        experts: list[dict] = []
        if mat:
            try:
                experts = self.gq.experts_by_entity(mat["id"])
            except Exception:
                experts = []

        chunks = self._vector_search(question, k_chunks)
        answer = self._synthesize(question, rows, chunks, numeric_matches)

        return {
            "answer": answer,
            "intent": intent,
            "linked": {"material": mat, "property": prop},
            "facts": rows,
            "numeric_matches": numeric_matches,
            "experts": experts,
            "chunks": chunks,
            "focus_entity": (mat or prop or {}).get("id"),
        }

    def _vector_search(self, question: str, k: int) -> list[dict]:
        try:
            from ..search import vectorstore

            return vectorstore.search(question, k=k)
        except Exception:
            return []  # qdrant не поднят / эмбеддинги не загружены — живём на графе

    def _synthesize(self, question: str, rows: list[dict], chunks: list[dict],
                     numeric_matches: list[dict] | None = None) -> str:
        numeric_matches = numeric_matches or []
        if not rows and not chunks and not numeric_matches:
            return ("По графу ничего не нашлось — либо переформулируйте вопрос, "
                    "либо это пробел в данных (см. вкладку «Пробелы»).")
        if not llm.has_llm():
            return self._tabular(rows, numeric_matches)
        facts = "\n".join(f"- {self._annotate(r)}" for r in rows[:25])
        passages = "\n\n".join(
            f"[{c.get('doc_id')}] {c.get('text', '')[:600]}" for c in chunks
        )
        numeric_block = self._numeric_block(numeric_matches)
        try:
            return llm.chat(
                [
                    {"role": "system", "content": ANSWER_SYSTEM},
                    {
                        "role": "user",
                        "content": (
                            f"Вопрос: {question}\n\nФакты из графа:\n{facts or '(нет)'}"
                            f"\n\nФрагменты документов:\n{passages or '(нет)'}"
                            f"{numeric_block}"
                        ),
                    },
                ],
                temperature=0.2,
            )
        except Exception as e:
            return self._tabular(rows, numeric_matches) + f"\n\n(LLM недоступна: {e})"

    @staticmethod
    def _annotate(row: dict) -> str:
        """Дописывает «источников: N» и «актуально на: дата» — LLM использует
        это как готовые метрики вместо оценки на глаз."""
        docs = row.get("documents") or []
        n_docs = len({d.get("id") for d in docs if isinstance(d, dict) and d.get("id")})
        actualized = row.get("actualized_at")
        suffix = f" [источников: {n_docs or 1}]"
        if actualized:
            suffix += f" [актуально на: {str(actualized)[:10]}]"
        return f"{row}{suffix}"

    @staticmethod
    def _numeric_block(numeric_matches: list[dict]) -> str:
        if not numeric_matches:
            return ""
        lines = []
        for nm in numeric_matches[:15]:
            verdict = "ПОДХОДИТ" if nm.get("fits") else "не подходит"
            lines.append(
                f"- {nm.get('name')} = {nm.get('raw') or nm.get('value')} {nm.get('unit') or ''} "
                f"(запрошено: {nm.get('requested')}) -> {verdict} "
                f"[{nm.get('material') or ''} · {nm.get('experiment') or ''}]"
            )
        return "\n\nЧисловые условия из графа, сопоставленные с запросом:\n" + "\n".join(lines)

    @staticmethod
    def _tabular(rows: list[dict], numeric_matches: list[dict] | None = None) -> str:
        lines = []
        for r in rows[:15]:
            if "finding" in r:
                docs = ", ".join(d["title"] for d in r.get("documents", []) if d.get("title"))
                lines.append(
                    f"• {r.get('material')} | {r.get('mode') or 'режим н/д'} -> "
                    f"{r.get('property')}: {r.get('finding')} "
                    f"({r.get('direction')}, {r.get('magnitude') or '—'}) [{docs}]"
                )
            else:
                lines.append(f"• {r}")
        if numeric_matches:
            lines.append("")
            lines.append("Числовые условия из графа:")
            for nm in numeric_matches[:15]:
                verdict = "подходит" if nm.get("fits") else "не подходит"
                lines.append(f"• {nm.get('name')}: {nm.get('raw')} ({verdict})")
        if not lines:
            return "Фактов не найдено."
        return "Найдено в графе:\n" + "\n".join(lines)
