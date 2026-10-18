"""
pipeline_logging.py - logging setup and helpers shared by every module of the pipeline.

Aspect: *observability*. Designed for running in a container:
  * everything goes to STDOUT (what `docker logs` / `docker compose logs` show),
  * one line per event: "<timestamp> <LEVEL> <logger name>: <message>",
  * verbosity is set with the LOG_LEVEL env variable (DEBUG, INFO (default), WARNING, ERROR).

What each level is used for:
    DEBUG    raw LLM answers, parsed entities, full Cypher parameters sizes
    INFO     stage start/end + duration, progress per page, Neo4j write counters, graph totals
    WARNING  recoverable problems: unparsable LLM output, missing API key, empty results
    ERROR    fatal problems; the traceback is logged and the process exits with code 1
"""
import logging
import os
import sys
import time
from contextlib import contextmanager

LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"

# Neo4j write counters worth reporting (name of the attribute in summary.counters).
_COUNTERS = ["nodes_created", "nodes_deleted", "relationships_created", "relationships_deleted",
             "properties_set", "labels_added", "labels_removed", "indexes_added", "constraints_added"]

logger = logging.getLogger(__name__)


def setup_logging():
    """Configure the root logger once (call it first thing in the entry point)."""
    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, None)
    if not isinstance(level, int):
        level = logging.INFO
        bad_level = level_name
    else:
        bad_level = None

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    root = logging.getLogger()
    root.handlers[:] = [handler]  # replace any handler installed by a library
    root.setLevel(level)

    # Chatty third-party loggers: only show them when the user asks for DEBUG.
    third_party_level = logging.DEBUG if level <= logging.DEBUG else logging.WARNING
    for name in ("neo4j", "httpx", "httpcore", "openai", "urllib3"):
        logging.getLogger(name).setLevel(third_party_level)

    if bad_level:
        logger.warning("Unknown LOG_LEVEL '%s', using INFO", bad_level)
    logger.info("Logging initialised, level=%s", logging.getLevelName(level))


@contextmanager
def log_stage(name: str):
    """Log the start, the end (with duration) or the failure of a pipeline stage."""
    stage_logger = logging.getLogger("pipeline")
    stage_logger.info(">>> START  %s", name)
    t_start = time.time()
    try:
        yield
    except Exception:
        stage_logger.error("!!! FAILED %s after %.1f sec", name, time.time() - t_start)
        raise
    stage_logger.info("<<< END    %s (%.1f sec)", name, time.time() - t_start)


def run_query(session, description: str, query: str, show_result: bool = False, **params):
    """
    Run one Cypher statement, log what it did and return its records (list of dicts).

    Logged at INFO: the description, the duration and the Neo4j counters that are non-zero
    (e.g. "nodes_created=12 relationships_created=30"). `show_result=True` also logs the
    first returned record - useful for GDS procedures that return statistics.
    """
    logger.debug("Running: %s", description)
    t_start = time.time()
    result = session.run(query, **params)
    records = result.data()  # fetch everything; also lets us call consume() safely
    summary = result.consume()
    elapsed = time.time() - t_start

    counters = summary.counters
    changes = " ".join(f"{c}={getattr(counters, c)}" for c in _COUNTERS if getattr(counters, c, 0))
    logger.info("%s - %.2f sec%s%s", description, elapsed,
                f" - {changes}" if changes else "",
                f" - {len(records)} row(s)" if records else "")
    if show_result and records:
        logger.info("%s - result: %s", description, records[0])
    return records


def log_graph_summary(driver, database: str, title: str):
    """
    Log how many nodes per label and relationships per type exist right now.
    Never raises: a failing summary must not break the pipeline.
    """
    try:
        with driver.session(database=database) as session:
            nodes = session.run("MATCH (n) UNWIND labels(n) AS label "
                                "RETURN label, count(*) AS cnt ORDER BY label").data()
            rels = session.run("MATCH ()-[r]->() RETURN type(r) AS type, count(*) AS cnt "
                               "ORDER BY type").data()
        logger.info("Graph summary [%s] nodes: %s", title,
                    ", ".join(f"{r['label']}={r['cnt']}" for r in nodes) or "(none)")
        logger.info("Graph summary [%s] relationships: %s", title,
                    ", ".join(f"{r['type']}={r['cnt']}" for r in rels) or "(none)")
    except Exception as e:  # noqa: BLE001 - diagnostics only
        logger.warning("Could not compute graph summary [%s]: %s", title, e)
