# Build context is the repository root (see docker-compose.yml) so util/ and config.ini are available.
FROM python:3.11-slim
WORKDIR /app
COPY chapters/ch06/requirements.lock .
# tqdm is used by util/base_importer.py; openai 1.12 breaks with httpx >= 0.28 (removed the `proxies` argument)
RUN pip install --no-cache-dir -r requirements.lock tqdm==4.66.1 "httpx<0.28"
COPY util util
COPY config.ini config.ini
COPY chapters/ch06 chapters/ch06
# the importer imports util.* and uses paths relative to the importer folder (../../../data)
ENV PYTHONPATH=/app
# logs must reach `docker logs` immediately
ENV PYTHONUNBUFFERED=1
WORKDIR /app/chapters/ch06/importer
# data/ is bind-mounted at /app/data (diaries JSON, prompt files, LLM cache);
# Neo4j settings come from NEO4J_* env vars, LLM settings from OPENAI_* and LOG_LEVEL
CMD ["python", "ingest_and_process.py"]
