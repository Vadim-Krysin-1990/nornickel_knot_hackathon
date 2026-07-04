"""Загрузка ExtractionResult в Neo4j. Идемпотентно (MERGE по id)."""
from __future__ import annotations

import json

from neo4j import GraphDatabase

from ..config import settings
from ..ontology.schema import ENTITY_LABELS, RELATION_TYPES, ExtractionResult

FULLTEXT_INDEX = (
    "CREATE FULLTEXT INDEX entity_names IF NOT EXISTS "
    "FOR (n:Material|Property|Mode|Equipment|Person|Lab|Experiment|Document|Tag) "
    "ON EACH [n.name, n.label, n.title, n.aliases]"
)


def _sanitize(props: dict) -> dict:
    """Neo4j не принимает вложенные dict'ы — сериализуем их в JSON-строки."""
    out = {}
    for k, v in props.items():
        if isinstance(v, dict):
            out[k] = json.dumps(v, ensure_ascii=False)
        elif isinstance(v, list) and v and isinstance(v[0], (dict, list)):
            out[k] = json.dumps(v, ensure_ascii=False)
        else:
            out[k] = v
    return out


class GraphStore:
    def __init__(self):
        self.driver = GraphDatabase.driver(
            settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
        )

    def close(self):
        self.driver.close()

    def init_schema(self):
        with self.driver.session() as s:
            for label in set(ENTITY_LABELS.values()):
                s.run(
                    f"CREATE CONSTRAINT IF NOT EXISTS FOR (n:{label}) REQUIRE n.id IS UNIQUE"
                )
            s.run(FULLTEXT_INDEX)

    def load(self, res: ExtractionResult):
        with self.driver.session() as s:
            for field, label in ENTITY_LABELS.items():
                for ent in getattr(res, field):
                    props = _sanitize(ent.model_dump(exclude_none=True, mode="json"))
                    # loaded_at — «дата актуализации»: когда факт последний раз
                    # подтверждён/обновлён в базе (модель верификации знаний)
                    s.run(
                        f"MERGE (n:{label} {{id: $id}}) "
                        f"SET n += $props, n.loaded_at = toString(datetime())",
                        id=ent.id,
                        props=props,
                    )
            for rel in res.relations:
                if rel.type not in RELATION_TYPES:
                    continue
                s.run(
                    f"MATCH (a {{id: $src}}) MATCH (b {{id: $dst}}) "
                    f"MERGE (a)-[r:{rel.type}]->(b) SET r += $props",
                    src=rel.source,
                    dst=rel.target,
                    props=_sanitize(rel.props),
                )

    def wipe(self):
        with self.driver.session() as s:
            s.run("MATCH (n) DETACH DELETE n")
