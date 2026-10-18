PIP=../../venv/bin/pip
PYTHON=../../venv/bin/python

# OPENAI_KEY, OPENAI_BASE_URL and OPENAI_MODEL are read from .env (git-ignored, see .env.example)
-include .env
OPENAI_BASE_URL ?= https://api.openai.com/v1
OPENAI_MODEL ?= gpt-4o-mini
LOG_LEVEL ?= INFO
export OPENAI_KEY OPENAI_BASE_URL OPENAI_MODEL LOG_LEVEL


init:
	$(PIP) install -r requirements.lock

import:
	PYTHONPATH=../../ $(PYTHON) importer/ingest_and_process.py


# --- Docker ---
# Starts Neo4j and, once it is healthy, the importer container (runs the pipeline once and stays as "exited")
docker-up:
	docker compose up -d --build

# Re-run the pipeline in a fresh importer container
docker-import:
	docker compose up -d --build --force-recreate importer

docker-logs:
	docker logs -f ch06-importer

docker-logs-neo4j:
	docker logs -f ch06-neo4j

docker-down:
	docker compose down
