FROM python:3.10-slim
WORKDIR /app
COPY chapters/ch04/requirements.lock chapters/ch04/requirements.lock
RUN pip install --no-cache-dir -r chapters/ch04/requirements.lock
COPY util util
# Credential-free config: uri/user/password come from NEO4J_* env vars at run time
RUN printf '[neo4j]\nencrypted = 0\n' > config.ini
COPY chapters/ch04/importer chapters/ch04/importer
COPY chapters/ch04/analysis chapters/ch04/analysis
ENV PYTHONPATH=/app MPLBACKEND=Agg
CMD ["python", "chapters/ch04/importer/import_seed.py"]
