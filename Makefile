.PHONY: up down synth load load-fast load-llm api ui wipe

up:            ## поднять Neo4j + Qdrant
	docker compose up -d

down:
	docker compose down

synth:         ## сгенерировать синтетический корпус
	python scripts/generate_synthetic.py

load:          ## загрузить граф + эмбеддинги
	python scripts/load_all.py --wipe

load-fast:     ## только граф, без эмбеддингов (секунды)
	python scripts/load_all.py --wipe --no-embed

load-llm:      ## прогон с LLM-экстракцией (нужен ключ в .env)
	python scripts/load_all.py --wipe --use-llm

api:           ## FastAPI на :8000
	uvicorn src.api.main:app --reload --port 8000

ui:            ## Streamlit на :8501
	streamlit run ui/app.py
