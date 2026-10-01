FROM python:3.10-slim
WORKDIR /app
COPY chapters/ch03/requirements.lock chapters/ch03/requirements.lock
RUN pip install --no-cache-dir -r chapters/ch03/requirements.lock
COPY util util
# Credential-free config: uri/user/password come from NEO4J_* env vars at run time
RUN printf '[neo4j]\nencrypted = 0\n' > config.ini
COPY chapters/ch03/importer chapters/ch03/importer
ENV PYTHONPATH=/app
CMD ["python", "chapters/ch03/importer/import_hpo.py"]
