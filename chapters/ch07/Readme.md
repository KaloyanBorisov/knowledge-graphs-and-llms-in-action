## Named Entity Disambiguation

### Getting started
The construction of the Knowledge Graph requires to download multiple ontologies from the Unified Medical Language System (UMLS) platform. For the access to these files, you need to sign in in the following page: https://uts.nlm.nih.gov/uts/login using one of the proposed identity providers, including Google or Microsoft. After the authentication step, you can get your API key by clicking the link "*Get Your API Key*" and copy it in the `Makefile`. Further information on the programmatic access is available here: https://documentation.uts.nlm.nih.gov/automating-downloads.html.


#### Install requirements
This chapter's `Makefile` assumes you have a virtual environemnt folder called `venv` 
at the reopository root folder. You can edit the`Makefile` and redefine the `PIP` variable
at the first line to match your configuration.
```shell
make init
```

#### Download the datasets
Run this command to create a `dataset` folder at the repository root folder containing 
the raw data required: the SNOMED and UMLS ontologies and the OCR'd JSON pages (a ~2 GB download that
unpacks to ~6 GB in `dataset/ocred_documents/`).
```shell
make download
```
This is `make download-ontologies` (SNOMED, UMLS) plus `make download-ocr` (the OCR'd pages), which you can run separately.

#### Import the datasets
Run this command to execute the importer code for each dataset.
```shell
make import
```

### Run everything with Docker
If you're having trouble installing libraries related to scispacy, or you just want a
ready-made environment, `docker-compose.yml` starts Neo4j, runs the scripts and serves the notebook.
Neo4j Enterprise (evaluation licence) is used because the chapter needs a separate `ned` database.

1. Create the config file and set your UMLS API key in `APIKEY`:
```bash
cp .env.example .env
```
2. Download the SNOMED and UMLS files and the OCR'd JSON pages (~2 GB, unpacks to ~6 GB in `dataset/ocred_documents/`) into the `dataset` folder at the repository root (once):
```bash
docker compose build pipeline && docker compose run --rm download
```
3. Start Neo4j and run the pipeline (import, then disambiguation). It runs once and takes a long time:
```bash
docker compose up -d --build
docker logs -f ch07-pipeline
```
The first disambiguation run also downloads about 1 GB of scispacy UMLS linker data (kept in a Docker volume).
Resource notes: Neo4j is configured with a 10 GB heap, so the machine needs roughly 16 GB of RAM. Disambiguation processes
the pages in batches of 10 (the book uses 50): larger batches exceed Neo4j's transaction memory on the full dataset. On the
27,609 pages it takes about 1.5 hours. Progress bars are written as lines, so `docker logs -f ch07-pipeline` shows them.
4. Open the notebook at http://localhost:8888 :
```bash
docker compose --profile notebook up -d notebook
```
Neo4j Browser is at http://localhost:7474 (login `neo4j` / `password`). To run the pipeline again use
`docker compose up -d --force-recreate pipeline`, and `docker compose --profile notebook down` stops everything.
The same steps are available as `make docker-download`, `docker-up`, `docker-logs`, `docker-notebook` and `docker-down`.
