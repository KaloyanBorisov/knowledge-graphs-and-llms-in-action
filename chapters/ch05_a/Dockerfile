# Build context is the repository root (see docker-compose.yml) so util/ and config.ini are available.
# spaCy 3.6 (pinned in requirements.lock) has no wheels for Python 3.12+.
FROM python:3.11-slim
WORKDIR /app
COPY chapters/ch05_a/requirements.lock .
# spaCy 3.6 / thinc 8.1 are binary-incompatible with numpy 2
RUN pip install --no-cache-dir -r requirements.lock "numpy<2" \
    && pip install --no-cache-dir https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.6.0/en_core_web_sm-3.6.0-py3-none-any.whl
COPY util util
COPY config.ini config.ini
COPY chapters/ch05_a chapters/ch05_a
# the importers use paths relative to the chapter folder (../../data) and import util.*
ENV PYTHONPATH=/app
WORKDIR /app/chapters/ch05_a
# data/ is bind-mounted at /app/data (BBC articles + Wikidata caches); Neo4j settings come from NEO4J_* env vars
CMD ["sh", "-c", "python importer/step1__import_bbc.py && python importer/step2__enrich_organizations.py && python importer/step3__enrich_by_ownerships.py"]
