.PHONY: init import analysis
PIP=../../venv/bin/pip
PYTHON=../../venv/bin/python

init:
	$(PIP) install -r requirements.lock

import:
	PYTHONPATH=../../ $(PYTHON) importer/import_seed.py

analysis:
	PYTHONPATH=../../ $(PYTHON) analysis/louvain_cluster_analysis.py
	PYTHONPATH=../../ $(PYTHON) analysis/multiomic_analysis.py


.PHONY: up down reset
up:
	docker compose up --build

down:
	docker compose down

reset:
	docker compose down -v
