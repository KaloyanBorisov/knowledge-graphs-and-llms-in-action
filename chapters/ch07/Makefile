PIP=../../venv/bin/pip
PYTHON=../../venv/bin/python

#APIKEY=PUT_YOUR_API_KEY_HERE

download: download-ontologies download-ocr

download-ontologies:
	mkdir -p ../../dataset/ontology/snomed/
	mkdir -p ../../dataset/ontology/umls/
	@curl "https://uts-ws.nlm.nih.gov/download?url=https://download.nlm.nih.gov/mlb/utsauth/USExt/SnomedCT_USEditionRF2_PRODUCTION_20220901T120000Z.zip&apiKey=$(APIKEY)" -o ../../dataset/ontology/snomed/SnomedCT_USEditionRF2_PRODUCTION_20220901T120000Z.zip
	@curl "https://uts-ws.nlm.nih.gov/download?url=https://download.nlm.nih.gov/umls/kss/2022AB/umls-2022AB-mrconso.zip&apiKey=$(APIKEY)" -o ../../dataset/ontology/umls/umls-2022AB-mrconso.zip
	curl "https://www.nlm.nih.gov/research/umls/knowledge_sources/semantic_network/SemGroups.txt" -o ../../dataset/ontology/umls/SemGroups.txt
	unzip ../../dataset/ontology/snomed/SnomedCT_USEditionRF2_PRODUCTION_20220901T120000Z.zip -d ../../dataset/ontology/snomed/
	unzip ../../dataset/ontology/umls/umls-2022AB-mrconso.zip -d ../../dataset/ontology/umls/
	mv ../../dataset/ontology/snomed/SnomedCT_USEditionRF2_PRODUCTION_20220901T120000Z/Full/Terminology/sct2_Relationship_Full_US1000124_20220901.txt ../../dataset/ontology/snomed/sct2_Relationship_Full_US1000124_20220901.txt
	mv ../../dataset/ontology/snomed/SnomedCT_USEditionRF2_PRODUCTION_20220901T120000Z/Full/Terminology/sct2_Description_Full-en_US1000124_20220901.txt ../../dataset/ontology/snomed/sct2_Description_Full-en_US1000124_20220901.txt
	mv ../../dataset/ontology/snomed/SnomedCT_USEditionRF2_PRODUCTION_20220901T120000Z/Full/Terminology/sct2_TextDefinition_Full-en_US1000124_20220901.txt ../../dataset/ontology/snomed/sct2_TextDefinition_Full-en_US1000124_20220901.txt

download-ocr:
	curl -L "https://drive.usercontent.google.com/download?id=19_FLk3cFXHINbQOP5ypWi15ixDgFXetR&confirm=xxx" -o ../../dataset/ocred_documents.zip
	mkdir -p ../../dataset/ocred_documents/
	unzip -q -j -o ../../dataset/ocred_documents.zip 'ocred_documents/*' -d ../../dataset/ocred_documents/
	find ../../dataset/ocred_documents/ -name '._*' -delete
	rm ../../dataset/ocred_documents.zip

init:
	$(PIP) install -r requirements.lock

import:
	PYTHONPATH=../../ $(PYTHON) importer/import_snomed_rels.py
	PYTHONPATH=../../ $(PYTHON) importer/import_snomed_names.py
	PYTHONPATH=../../ $(PYTHON) importer/propagate_snomed_categories.py
	PYTHONPATH=../../ $(PYTHON) importer/import_hpo.py
	PYTHONPATH=../../ $(PYTHON) importer/import_umls_concept_mapping.py
	PYTHONPATH=../../ $(PYTHON) importer/import_ocred_documents.py

disambiguate:
	PYTHONPATH=../../ $(PYTHON) disambiguation/disambiguator.py
	PYTHONPATH=../../ $(PYTHON) disambiguation/ontology_linking.py
	PYTHONPATH=../../ $(PYTHON) disambiguation/co_occurrence_generator.py

# --- Docker ---
# Starts Neo4j and, once it is healthy, the pipeline container (import + disambiguate, runs once)
docker-up:
	docker compose up -d --build

docker-download:
	docker compose build pipeline && docker compose run --rm download

docker-logs:
	docker logs -f ch07-pipeline

docker-notebook:
	docker compose --profile notebook up -d notebook

docker-down:
	docker compose --profile notebook down
