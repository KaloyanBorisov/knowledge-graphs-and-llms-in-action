# Build context is the repository root (see docker-compose.yml) so util/ and config.ini are available.
FROM python:3.9-slim
# scispacy depends on nmslib/pysbd, which may need to be compiled; make/curl/unzip are used by `make download`
RUN apt-get update && apt-get install -y --no-install-recommends build-essential make curl unzip \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY chapters/ch07/requirements.lock .
# tqdm is used by util/base_importer.py; pandas + jupyterlab are for analysis/ch07.ipynb
RUN pip install --no-cache-dir -r requirements.lock "numpy<2" tqdm pandas jupyterlab
COPY util util
COPY config.ini config.ini
COPY chapters/ch07 chapters/ch07
# the scripts import util.* and use paths relative to the chapter folder (../../dataset)
ENV PYTHONPATH=/app
# logs must reach `docker logs` immediately
ENV PYTHONUNBUFFERED=1
# the scispacy UMLS linker downloads ~1 GB of data on first use; keep it in a volume
ENV SCISPACY_CACHE=/cache/scispacy
WORKDIR /app/chapters/ch07
# dataset/ is bind-mounted at /app/dataset; Neo4j settings come from the NEO4J_* env vars
CMD ["sh", "docker/run.sh"]
