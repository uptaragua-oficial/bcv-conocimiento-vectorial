# ============================================================
# BCV · Plataforma de Conocimiento Vectorial — MVP jurídico
# ============================================================
export PYTHONPATH := .pylibs:.
PY ?= python

.PHONY: help setup up down logs schema pipeline ingest extract chunk ner index evaluate api test clean

help:
	@echo "Objetivos disponibles:"
	@echo "  make setup     Instala dependencias de Python en .pylibs"
	@echo "  make up        Levanta Weaviate (docker compose up -d)"
	@echo "  make down      Detiene Weaviate"
	@echo "  make schema    Muestra el esquema de la colección"
	@echo "  make pipeline  Ejecuta F2→F9"
	@echo "  make api       Levanta la API en :8000"
	@echo "  make test      Ejecuta las pruebas"

setup:
	pip install --target .pylibs --index-url https://download.pytorch.org/whl/cpu torch
	pip install --target .pylibs -r requirements.txt

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f weaviate

schema:
	$(PY) -m src.schema

ingest:
	$(PY) -m src.ingest

extract:
	$(PY) -m src.extract

chunk:
	$(PY) -m src.chunking

ner:
	$(PY) -m src.ner

index:
	$(PY) -m src.index --recreate

evaluate:
	$(PY) -m src.evaluate

pipeline: ingest extract chunk ner index evaluate

api:
	$(PY) -m uvicorn src.api:app --host 0.0.0.0 --port 8000

test:
	$(PY) -m pytest -q tests

clean:
	rm -rf data/processed/* data/index/*.json data/index/*.jsonl
