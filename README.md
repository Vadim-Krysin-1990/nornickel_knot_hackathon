🧶 Научный клубок — единая карта знаний R&D
Nornickel AI Science Hack 2026 · Трек 02 «Научный клубок»

GraphRAG-система: knowledge graph (Neo4j) + семантический поиск (Qdrant) по корпусу научно-технических документов горно-металлургической отрасли (статьи, обзоры, доклады Института Гипроникель, материалы конференций, отраслевые журналы). Связывает материалы, процессы, условия, оборудование, выводы, авторов и лаборатории в единую сеть знаний.

На реальном корпусе кейса: 329 документов первой очереди → ~3 500 узлов (681 материал, 627 выводов, 468 числовых условий, 356 экспертов) и ~6 200 связей в графе + семантический индекс полных текстов. LLM — Yandex AI Studio (предоставлен организаторами); архитектура LLM-агностична.

Отвечает на вопросы вида:

«Какие технические решения циркуляции католита при электроэкстракции никеля описаны в практике?»
«Какие методы обессоливания воды подходят при сульфатах 200–300 мг/л?»
«Что известно о распределении Au, Ag и МПГ между штейном и шлаком?»
«Где в данных есть противоречия?» / «Что не исследовано?» (пробелы)
Архитектура
 корпус документов (pdf/docx/docm/doc/pptx, ru+en)
        │  parsers + чистка Word-мусора + метаданные из путей (категория/год)
        ▼
  LLM-экстракция (Yandex AI Studio / Ollama / любой OpenAI-совместимый API)
        │  строгий JSON → Pydantic-онтология с нормализацией (направления эффектов,
        │  числа из строк, гарантированный узел исследования на документ)
        ▼                                        ▼
   Qdrant (чанки, multilingual-e5)          Neo4j (граф знаний)
        │                                        │
        └────────────► GraphRAG ◄────────────────┘
     интент → entity linking (rapidfuzz, алиасы ru/en) → Cypher + вектор → синтез
                                │
                     FastAPI (:8000) → Streamlit (:8501)
        чат · подграф · матрица пробелов · противоречия
Онтология
11 типов узлов: Material, Property, Mode(процесс), Condition(числовые условия), Equipment, Person, Lab, Experiment, Finding, Document, Tag. 15 типов связей, ключевая цепочка:

(Material)<-[:USES_MATERIAL]-(Experiment)-[:UNDER_MODE]->(Mode)
(Experiment)-[:UNDER_CONDITION]->(Condition {operator, value, unit})
(Experiment)-[:HAS_FINDING]->(Finding)-[:AFFECTS {direction}]->(Property)
(Document)-[:DESCRIBES]->(Experiment); (Finding)-[:CONTRADICTS]->(Finding)
Под требования трека:

Числовые условия и диапазоны — Condition («сульфаты ≤300 мг/л» → operator/value/unit)
География — РФ / зарубежная практика на документах и экспериментах, фильтр в запросах
Верификация — источник у каждого факта (кликабельный provenance), confidence выводов, число подтверждающих документов
Противоречия — явные CONTRADICTS + автодетект выводов с противоположным эффектом
Пробелы — матрица Материал × Свойство, нули = неисследованные комбинации
Мультиязычность — русские и английские термины в алиасах («электроэкстракция» = «electrowinning»)
Быстрый старт
cp .env.example .env            # прописать LLM_API_KEY (Yandex AI Studio / Ollama)
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
apt install -y catdoc antiword  # для старых .doc

make up                         # Neo4j (7474/7687) + Qdrant (6333)
make synth && make load-fast    # демо на синтетике за секунды, без LLM

make api                        # терминал 1
make ui                         # терминал 2 -> http://localhost:8501
Без LLM-ключа всё работает — fallback-ответы таблицей фактов из графа.

Загрузка реального корпуса
# манифест без загрузки (что и в каком порядке пойдёт)
python scripts/load_real.py --data-dir data/real --dry-run

# первая очередь (статьи/обзоры/доклады): граф + вектора
python scripts/load_real.py --data-dir data/real --priority 1

# перегнать только упавшие; вторая очередь только в векторный индекс
python scripts/load_real.py --data-dir data/real --only-errors
python scripts/load_real.py --data-dir data/real --priority 2 --no-extract

curl -X POST localhost:8000/relink   # обновить справочник entity linking
python scripts/graph_stats.py        # диагностика графа
Очереди: P1 — Статьи/Обзоры/Доклады (внутренние документы: авторы, лаборатории, эксперименты), P2 — материалы конференций, P3 — журнальные подшивки. Сканы без текстового слоя уходят в OCR-очередь (load_errors.csv), план OCR — docs/ocr_plan.md.

API
POST /ask — вопрос на естественном языке → ответ + факты + источники · GET /gaps — матрица пробелов · GET /contradictions — противоречия · GET /subgraph/{id} — подграф для визуализации · GET /timeline/{id} — история работ · GET /search?q= — fulltext по сущностям · POST /relink — обновить линковку

Стек
Neo4j 5 + Qdrant (Docker Compose) · Python 3.10 · FastAPI · Streamlit + pyvis + plotly · sentence-transformers (multilingual-e5) · rapidfuzz · LLM через любой OpenAI-совместимый API (Yandex AI Studio, OpenRouter, vLLM) или нативный Ollama — автодетект протокола.

Open Source: используемые компоненты и лицензии
Согласно п. 7.4–7.5 Положения хакатона. Все компоненты используются на условиях своих открытых лицензий с сохранением авторства:

Компонент	Правообладатель	Лицензия
Neo4j Community 5	Neo4j, Inc.	GPLv3
Qdrant / qdrant-client	Qdrant Solutions GmbH	Apache 2.0
PyMuPDF	Artifex Software, Inc.	AGPL-3.0
FastAPI, pydantic, plotly, rapidfuzz, python-docx, python-pptx, openpyxl	соотв. авторы	MIT
Streamlit, sentence-transformers, requests, openai-python, neo4j-driver	соотв. авторы	Apache 2.0
uvicorn, pandas, pyvis	соотв. авторы	BSD-3-Clause
Модель intfloat/multilingual-e5-small	Microsoft (intfloat)	MIT
Gemma 3 (этап разработки)	Google	Gemma Terms of Use (коммерческое использование разрешено)
Исходный код проекта открыт в этом репозитории. Реальные данные кейса (data/real/) в репозиторий не входят.

Структура
src/ontology/schema.py   онтология + валидаторы-нормализаторы (ядро)
src/ingest/              парсеры pdf/docx/docm/doc/pptx + чанкер
src/extract/             LLM-экстракция: промпт + гарантия связности
src/graph/               Neo4j: загрузка (MERGE, идемпотентно) + Cypher-запросы
src/search/              эмбеддинги + Qdrant
src/qa/                  интент → линковка → GraphRAG-ответ с источниками
src/api/main.py          FastAPI
ui/app.py                Streamlit: чат / граф / пробелы / противоречия
scripts/                 load_real (корпус), graph_stats, backfill, синтетика
docs/                    презентация, планы (день Х, OCR)
