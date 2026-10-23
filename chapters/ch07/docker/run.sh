#!/bin/sh
# Runs the whole chapter pipeline once: create the `ned` database, import the datasets, disambiguate.
set -e

python - <<'PY'
import time
from util.graphdb_base import GraphDBBase

gd = GraphDBBase()
with gd._driver.session(database="system") as session:
    session.run("CREATE DATABASE ned IF NOT EXISTS WAIT").consume()
print("database ned is ready")
PY

make import PYTHON=python
make disambiguate PYTHON=python
echo "pipeline finished"
