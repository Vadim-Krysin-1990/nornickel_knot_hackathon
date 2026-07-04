"""Готовые Cypher-запросы под сценарии трека."""
from __future__ import annotations

from .loader import GraphStore

# --- Эталонный вопрос трека: материал X + режим Y -> эффект на свойство Z ---
EFFECTS_CY = """
MATCH (m:Material)<-[:USES_MATERIAL]-(e:Experiment)
WHERE $material_id IS NULL OR m.id = $material_id
OPTIONAL MATCH (e)-[:UNDER_MODE]->(mo:Mode)
WITH m, e, mo
WHERE $mode_hint IS NULL
   OR toLower(coalesce(mo.label, '') + ' ' + coalesce(mo.process, '')) CONTAINS toLower($mode_hint)
MATCH (e)-[:HAS_FINDING]->(f:Finding)
OPTIONAL MATCH (f)-[af:AFFECTS]->(p:Property)
WITH m, e, mo, f, p
WHERE $property_id IS NULL OR (p IS NOT NULL AND p.id = $property_id)
OPTIONAL MATCH (d:Document)-[:DESCRIBES]->(e)
WITH m, e, mo, f, p, d
WHERE $geography IS NULL
   OR toLower(coalesce(e.geography, '') + ' ' + coalesce(d.geography, '')) CONTAINS toLower($geography)
OPTIONAL MATCH (e)-[:CONDUCTED_BY]->(lab:Lab)
RETURN m.name AS material,
       e.id AS experiment_id, e.title AS experiment, e.date AS date,
       coalesce(e.geography, d.geography) AS geography,
       mo.label AS mode,
       p.name AS property,
       f.text AS finding, f.effect_direction AS direction, f.magnitude AS magnitude,
       f.confidence AS confidence,
       coalesce(e.loaded_at, d.loaded_at) AS actualized_at,
       lab.name AS lab,
       collect(DISTINCT {id: d.id, title: d.title, path: d.source_path, loaded_at: d.loaded_at}) AS documents
ORDER BY coalesce(e.date, '') DESC
LIMIT $limit
"""

# --- Противоречия: два вывода с противоположным направлением на одно свойство ---
CONTRADICTIONS_CY = """
MATCH (f1:Finding)-[:AFFECTS]->(p:Property)<-[:AFFECTS]-(f2:Finding)
WHERE f1.effect_direction = 'increase' AND f2.effect_direction = 'decrease'
MATCH (e1:Experiment)-[:HAS_FINDING]->(f1), (e2:Experiment)-[:HAS_FINDING]->(f2)
OPTIONAL MATCH (e1)-[:USES_MATERIAL]->(m1:Material)
OPTIONAL MATCH (e2)-[:USES_MATERIAL]->(m2:Material)
WITH p, f1, f2, e1, e2, m1, m2
WHERE m1 IS NULL OR m2 IS NULL OR m1.id = m2.id
OPTIONAL MATCH (d1:Document)-[:DESCRIBES]->(e1)
OPTIONAL MATCH (d2:Document)-[:DESCRIBES]->(e2)
RETURN p.name AS property, coalesce(m1.name, m2.name) AS material,
       f1.text AS finding_a, d1.title AS source_a, f1.id AS finding_a_id,
       f2.text AS finding_b, d2.title AS source_b, f2.id AS finding_b_id,
       'по показателю' AS kind
LIMIT $limit
"""

# Потенциальные: связь вывод->показатель у LLM редкая, поэтому сопоставляем
# противоположные выводы через эксперименты, меряющие одно свойство на одном
# материале. Кандидаты — на подтверждение экспертом (human-in-the-loop).
CONTRADICTIONS_APPROX_CY = """
MATCH (m:Material)<-[:USES_MATERIAL]-(e1:Experiment)
      -[:HAS_FINDING]->(f1:Finding {effect_direction: 'increase'}),
      (m)<-[:USES_MATERIAL]-(e2:Experiment)
      -[:HAS_FINDING]->(f2:Finding {effect_direction: 'decrease'}),
      (e1)-[:MEASURES]->(p:Property)<-[:MEASURES]-(e2)
WHERE e1 <> e2
  AND COUNT { (e1)-[:USES_MATERIAL]->() } <= 5
  AND COUNT { (e2)-[:USES_MATERIAL]->() } <= 5
OPTIONAL MATCH (d1:Document)-[:DESCRIBES]->(e1)
OPTIONAL MATCH (d2:Document)-[:DESCRIBES]->(e2)
RETURN DISTINCT p.name AS property, m.name AS material,
       f1.text AS finding_a, d1.title AS source_a, f1.id AS finding_a_id,
       f2.text AS finding_b, d2.title AS source_b, f2.id AS finding_b_id,
       'потенциальное' AS kind
LIMIT $limit
"""

# --- Матрица пробелов: топ-материалы x топ-свойства (на реальном корпусе
# полная матрица 576x224 нечитаема), 0 экспериментов = пробел ---
GAP_MATRIX_CY = """
MATCH (m:Material)<-[:USES_MATERIAL]-(e:Experiment)
WITH m, count(DISTINCT e) AS deg ORDER BY deg DESC LIMIT 15
WITH collect(m) AS mats
MATCH (p:Property)--()
WITH mats, p, count(*) AS pdeg ORDER BY pdeg DESC LIMIT 12
WITH mats, collect(p) AS props
UNWIND mats AS m
UNWIND props AS p
OPTIONAL MATCH (m)<-[:USES_MATERIAL]-(e:Experiment)
WHERE (e)-[:MEASURES]->(p) OR (e)-[:HAS_FINDING]->(:Finding)-[:AFFECTS]->(p)
RETURN m.name AS material, p.name AS property, count(DISTINCT e) AS n_experiments
ORDER BY material, property
"""

# --- Матрица пробелов: топ-материалы x топ-режимы («материал-режим не изучен») ---
GAP_MATRIX_MODE_CY = """
MATCH (m:Material)<-[:USES_MATERIAL]-(e:Experiment)
WITH m, count(DISTINCT e) AS deg ORDER BY deg DESC LIMIT 15
WITH collect(m) AS mats
MATCH (mo:Mode)<-[:UNDER_MODE]-(:Experiment)
WITH mats, mo, count(*) AS modeg ORDER BY modeg DESC LIMIT 12
WITH mats, collect(mo) AS modes
UNWIND mats AS m
UNWIND modes AS mo
OPTIONAL MATCH (m)<-[:USES_MATERIAL]-(e:Experiment)-[:UNDER_MODE]->(mo)
RETURN m.name AS material, mo.label AS mode, count(DISTINCT e) AS n_experiments
ORDER BY material, mode
"""

# --- Технологии (режимы), описанные только в отечественной или только
# в зарубежной практике — по geography связанных экспериментов/документов ---
MODE_GEOGRAPHY_CY = """
MATCH (mo:Mode)<-[:UNDER_MODE]-(e:Experiment)
OPTIONAL MATCH (d:Document)-[:DESCRIBES]->(e)
WITH mo, collect(DISTINCT toLower(coalesce(e.geography, d.geography, ''))) AS geos
WITH mo,
     any(g IN geos WHERE g CONTAINS 'рф' OR g CONTAINS 'росси' OR g CONTAINS 'отечествен') AS has_ru,
     any(g IN geos WHERE g CONTAINS 'зарубеж' OR g CONTAINS 'иностран') AS has_foreign
RETURN mo.label AS mode, has_ru AS has_ru, has_foreign AS has_foreign
ORDER BY mode
"""

# --- Аналитика для дашборда ---
STATS_NODES_CY = "MATCH (n) RETURN labels(n)[0] AS label, count(*) AS n ORDER BY n DESC"
STATS_RELS_CY = "MATCH ()-[r]->() RETURN count(r) AS n"
STATS_DOCS_BY_TYPE_CY = """
MATCH (d:Document) RETURN coalesce(d.doc_type, 'без типа') AS doc_type, count(*) AS n
ORDER BY n DESC LIMIT 10
"""
STATS_DOCS_BY_YEAR_CY = """
MATCH (d:Document) WHERE d.year IS NOT NULL
RETURN d.year AS year, count(*) AS n ORDER BY year
"""
STATS_TOP_MATERIALS_CY = """
MATCH (m:Material)<-[:USES_MATERIAL]-(e:Experiment)
RETURN m.name AS name, count(DISTINCT e) AS n ORDER BY n DESC LIMIT 12
"""
STATS_TOP_LABS_CY = """
MATCH (lab:Lab)<-[:MEMBER_OF]-(:Person)<-[:AUTHORED_BY]-(d:Document)
RETURN lab.name AS name, count(DISTINCT d) AS n ORDER BY n DESC LIMIT 10
"""

# --- Таймлайн (история решений) по материалу ---
TIMELINE_CY = """
MATCH (m:Material {id: $material_id})<-[:USES_MATERIAL]-(e:Experiment)
OPTIONAL MATCH (e)-[:UNDER_MODE]->(mo:Mode)
OPTIONAL MATCH (e)-[:HAS_FINDING]->(f:Finding)-[:AFFECTS]->(p:Property)
OPTIONAL MATCH (e)-[:CONDUCTED_BY]->(lab:Lab)
RETURN e.date AS date, e.title AS experiment, mo.label AS mode, lab.name AS lab,
       collect(DISTINCT p.name + ': ' + coalesce(f.magnitude, f.effect_direction)) AS effects
ORDER BY coalesce(e.date, '')
"""

# --- Подграф вокруг сущности (для визуализации) ---
SUBGRAPH_CY = """
MATCH p = (n {id: $entity_id})-[*1..2]-(m)
WITH p LIMIT 300
UNWIND nodes(p) AS nd
UNWIND relationships(p) AS rl
RETURN
  collect(DISTINCT {
    id: nd.id,
    label: labels(nd)[0],
    name: coalesce(nd.name, nd.title, nd.label, left(coalesce(nd.text, nd.id), 60)),
    path: nd.source_path
  }) AS nodes,
  collect(DISTINCT {source: startNode(rl).id, target: endNode(rl).id, type: type(rl)}) AS edges
"""

# --- Справочник имён для entity linking ---
NAMES_CY = """
MATCH (n)
WHERE any(l IN labels(n) WHERE l IN ['Material','Property','Mode','Equipment','Person','Lab'])
RETURN n.id AS id, labels(n)[0] AS label,
       coalesce(n.name, n.label) AS name,
       coalesce(n.aliases, []) AS aliases
"""

# --- Все числовые условия графа (для сопоставления диапазонов из вопроса) ---
ALL_CONDITIONS_CY = """
MATCH (c:Condition)<-[:UNDER_CONDITION]-(e:Experiment)
OPTIONAL MATCH (e)-[:USES_MATERIAL]->(m:Material)
OPTIONAL MATCH (d:Document)-[:DESCRIBES]->(e)
RETURN c.id AS condition_id, c.name AS name, c.operator AS operator,
       c.value AS value, c.value_max AS value_max, c.unit AS unit, c.raw AS raw,
       e.id AS experiment_id, e.title AS experiment, m.name AS material,
       collect(DISTINCT {id: d.id, title: d.title, path: d.source_path}) AS documents
LIMIT 2000
"""

# --- Справочник имён условий (для UI-формы точного числового поиска) ---
CONDITION_NAMES_CY = """
MATCH (c:Condition)
RETURN c.name AS name, c.unit AS unit, count(*) AS n
ORDER BY n DESC LIMIT 60
"""

# --- Эксперты и лаборатории, связанные с сущностью (обычно материалом) ---
EXPERTS_CY = """
MATCH (m {id: $entity_id})<-[:USES_MATERIAL]-(e:Experiment)<-[:DESCRIBES]-(d:Document)
             -[:AUTHORED_BY]->(p:Person)
OPTIONAL MATCH (p)-[:MEMBER_OF]->(lab:Lab)
RETURN DISTINCT p.name AS person, p.role AS role, lab.name AS lab
LIMIT 20
"""

# --- Тексты документов для эвристики доменов (Аналитика) ---
STATS_DOC_TEXT_CY = """
MATCH (d:Document)
OPTIONAL MATCH (d)-[:TAGGED]->(t:Tag)
WITH d, collect(t.name) AS tags
RETURN coalesce(d.title, '') AS title, coalesce(d.doc_type, '') AS doc_type, tags
"""

# --- Активность лабораторий по годам (через авторов документов) ---
STATS_LAB_ACTIVITY_CY = """
MATCH (lab:Lab)<-[:MEMBER_OF]-(:Person)<-[:AUTHORED_BY]-(d:Document)
WHERE d.year IS NOT NULL
RETURN lab.name AS lab, d.year AS year, count(DISTINCT d) AS n
ORDER BY lab, year
"""

FULLTEXT_CY = """
CALL db.index.fulltext.queryNodes('entity_names', $q) YIELD node, score
RETURN node.id AS id, labels(node)[0] AS label,
       coalesce(node.name, node.title, node.label) AS name, score
LIMIT $limit
"""


class GraphQueries:
    def __init__(self, store: GraphStore | None = None):
        self.store = store or GraphStore()

    def _run(self, cypher: str, **params) -> list[dict]:
        with self.store.driver.session() as s:
            return [r.data() for r in s.run(cypher, **params)]

    def find_effects(self, material_id=None, property_id=None, mode_hint=None,
                     geography=None, limit=25):
        return self._run(
            EFFECTS_CY,
            material_id=material_id,
            property_id=property_id,
            mode_hint=mode_hint,
            geography=geography,
            limit=limit,
        )

    def contradictions(self, limit=25):
        """Явные CONTRADICTS + автодетект по AFFECTS + потенциальные через MEASURES."""
        explicit = self._run(
            """MATCH (f1:Finding)-[:CONTRADICTS]-(f2:Finding)-[:AFFECTS]->(p:Property)
               OPTIONAL MATCH (d1:Document)-[:DESCRIBES]->(:Experiment)-[:HAS_FINDING]->(f1)
               OPTIONAL MATCH (d2:Document)-[:DESCRIBES]->(:Experiment)-[:HAS_FINDING]->(f2)
               RETURN p.name AS property, null AS material,
                      f1.text AS finding_a, d1.title AS source_a, f1.id AS finding_a_id,
                      f2.text AS finding_b, d2.title AS source_b, f2.id AS finding_b_id,
                      'явное' AS kind
               LIMIT $limit""",
            limit=limit,
        )
        auto = self._run(CONTRADICTIONS_CY, limit=limit)
        approx = self._run(CONTRADICTIONS_APPROX_CY, limit=limit)
        seen, out = set(), []
        for r in explicit + auto + approx:
            key = (r.get("finding_a"), r.get("finding_b"))
            if key not in seen and (key[1], key[0]) not in seen:
                seen.add(key)
                out.append(r)
        return out[:limit]

    def gap_matrix(self):
        return self._run(GAP_MATRIX_CY)

    def gap_matrix_mode(self):
        return self._run(GAP_MATRIX_MODE_CY)

    def mode_geography(self):
        """Классифицирует технологии (Mode) по покрытию источников:
        только РФ / только зарубеж / и то, и другое / география не извлечена."""
        rows = self._run(MODE_GEOGRAPHY_CY)
        out = []
        for r in rows:
            has_ru, has_foreign = r.get("has_ru"), r.get("has_foreign")
            if has_ru and has_foreign:
                coverage = "РФ и зарубеж"
            elif has_ru:
                coverage = "только РФ"
            elif has_foreign:
                coverage = "только зарубеж"
            else:
                coverage = "география не извлечена"
            out.append({"mode": r.get("mode"), "coverage": coverage})
        return out

    def risk_zones(self, low_coverage_max: int = 3, limit: int = 15):
        """Темы с малым числом источников (1..low_coverage_max экспериментов)
        + темы с противоречиями — объединённый рейтинг для дашборда руководителя."""
        from collections import Counter

        low = [
            {"material": r["material"], "property": r["property"],
             "reason": f"мало источников ({r['n_experiments']})"}
            for r in self.gap_matrix() if 0 < r["n_experiments"] <= low_coverage_max
        ]
        cnt = Counter((c.get("property"), c.get("material")) for c in self.contradictions(limit=200))
        contr_rows = [
            {"material": mat, "property": prop, "reason": f"{n} противоречащих вывод(ов)"}
            for (prop, mat), n in cnt.items()
        ]
        return (low + contr_rows)[:limit]

    def condition_names(self):
        return self._run(CONDITION_NAMES_CY)

    def experts_by_entity(self, entity_id: str):
        return self._run(EXPERTS_CY, entity_id=entity_id)

    def stats(self):
        from ..analytics import domain_counts

        return {
            "nodes": self._run(STATS_NODES_CY),
            "relations": self._run(STATS_RELS_CY)[0]["n"],
            "docs_by_type": self._run(STATS_DOCS_BY_TYPE_CY),
            "docs_by_year": self._run(STATS_DOCS_BY_YEAR_CY),
            "top_materials": self._run(STATS_TOP_MATERIALS_CY),
            "top_labs": self._run(STATS_TOP_LABS_CY),
            "domains": domain_counts(self._run(STATS_DOC_TEXT_CY)),
            "lab_activity": self._run(STATS_LAB_ACTIVITY_CY),
            "risk_zones": self.risk_zones(),
        }

    def timeline(self, material_id: str):
        return self._run(TIMELINE_CY, material_id=material_id)

    def subgraph(self, entity_id: str):
        rows = self._run(SUBGRAPH_CY, entity_id=entity_id)
        return rows[0] if rows else {"nodes": [], "edges": []}

    def entity_names(self):
        return self._run(NAMES_CY)

    def fulltext(self, q: str, limit: int = 10):
        return self._run(FULLTEXT_CY, q=q, limit=limit)

    def all_conditions(self):
        return self._run(ALL_CONDITIONS_CY)
