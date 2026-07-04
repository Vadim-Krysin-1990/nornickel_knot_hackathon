"""API «Научного клубка»: чат, пробелы, подграф, таймлайн, библиотека документов."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .. import audit
from ..config import settings
from ..qa.answer import Pipeline
from ..qa.numeric import filter_conditions

pipeline: Pipeline | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global pipeline
    pipeline = Pipeline()
    yield
    pipeline.gq.store.close()


app = FastAPI(title="Научный клубок — Nornickel AI Science Hack", lifespan=lifespan)

DATA_REAL_DIR = Path(settings.data_real_dir)
if DATA_REAL_DIR.is_dir():
    app.mount("/files", StaticFiles(directory=str(DATA_REAL_DIR)), name="files")


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None


class AskIn(BaseModel):
    question: str
    geography: str | None = None  # "РФ" | "зарубеж" | None — явный фильтр поверх интента


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/ask")
def ask(body: AskIn, request: Request):
    audit.log_action("ask", {
        "question": body.question, "geography": body.geography, "ip": _ip(request),
    })
    return pipeline.ask(body.question, geography=body.geography)


@app.get("/gaps")
def gaps(request: Request):
    audit.log_action("gaps", {"ip": _ip(request)})
    return pipeline.gq.gap_matrix()


@app.get("/gaps/mode")
def gaps_mode(request: Request):
    audit.log_action("gaps_mode", {"ip": _ip(request)})
    return pipeline.gq.gap_matrix_mode()


@app.get("/mode-geography")
def mode_geography(request: Request):
    audit.log_action("mode_geography", {"ip": _ip(request)})
    return pipeline.gq.mode_geography()


@app.get("/contradictions")
def contradictions(request: Request):
    audit.log_action("contradictions", {"ip": _ip(request)})
    return pipeline.gq.contradictions()


@app.get("/stats")
def stats(request: Request):
    audit.log_action("stats", {"ip": _ip(request)})
    return pipeline.gq.stats()


@app.get("/subgraph/{entity_id}")
def subgraph(entity_id: str, request: Request):
    audit.log_action("subgraph", {"entity_id": entity_id, "ip": _ip(request)})
    return pipeline.gq.subgraph(entity_id)


@app.get("/timeline/{material_id}")
def timeline(material_id: str, request: Request):
    audit.log_action("timeline", {"material_id": material_id, "ip": _ip(request)})
    return pipeline.gq.timeline(material_id)


@app.get("/experts/{entity_id}")
def experts(entity_id: str, request: Request):
    """Эксперты и лаборатории, связанные с сущностью (обычно материалом)."""
    audit.log_action("experts", {"entity_id": entity_id, "ip": _ip(request)})
    return pipeline.gq.experts_by_entity(entity_id)


@app.get("/search")
def fulltext(q: str, request: Request, limit: int = 10):
    audit.log_action("search", {"q": q, "ip": _ip(request)})
    return pipeline.gq.fulltext(q, limit=limit)


@app.get("/condition-names")
def condition_names(request: Request):
    audit.log_action("condition_names", {"ip": _ip(request)})
    return pipeline.gq.condition_names()


@app.get("/conditions")
def conditions_search(name: str, operator: str, value: float, request: Request,
                       value_max: float | None = None, unit: str | None = None):
    """Точный поиск по числовому условию — без интерпретации LLM, форма в UI."""
    audit.log_action("conditions_search", {
        "name": name, "operator": operator, "value": value, "ip": _ip(request),
    })
    rows = pipeline.gq.all_conditions()
    return filter_conditions(rows, name, operator, value, value_max, unit)


@app.get("/library")
def library(request: Request):
    """Все документы корпуса, сгруппированные по папкам — для вкладки «Библиотека»."""
    audit.log_action("library", {"ip": _ip(request)})
    if not DATA_REAL_DIR.is_dir():
        return {}
    out: dict[str, list[dict]] = {}
    for p in sorted(DATA_REAL_DIR.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(DATA_REAL_DIR)
        category = rel.parts[0] if len(rel.parts) > 1 else "(корень)"
        out.setdefault(category, []).append({
            "name": p.name,
            "path": str(rel).replace("\\", "/"),
            "size_kb": p.stat().st_size // 1024,
            "ext": p.suffix.lower(),
        })
    return out


@app.get("/audit")
def audit_log(limit: int = 50):
    """Журнал действий: кто (IP), что и когда запрашивал."""
    return audit.recent(limit)


@app.post("/relink")
def relink():
    """Перечитать справочник имён после дозагрузки данных."""
    pipeline.linker.refresh()
    return {"status": "refreshed"}
