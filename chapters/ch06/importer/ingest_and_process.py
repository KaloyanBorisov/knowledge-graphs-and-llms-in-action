"""
ingest_and_process.py - entry point of the chapter-6 pipeline (run via `make import`).

The implementation is split by aspect into the modules below; see CALL_DIAGRAM.html
for the full call graph.

    diaries_ingest.py        STAGE 1  DiariesImporter: schema + File/Page nodes
    full_kg.py               STAGES 2-3  FullKG: orchestrates the mixins
      llm_extraction.py        LLM prompting, caching, parsing, retries
      graph_store.py           writes raw entities/relations
      entity_normalization.py  name clean-up
      entity_resolution.py     person de-duplication
      kg_builder.py            final KG creation
    graph_analytics.py       STAGE 4  GDS centralities / communities
    kg_schema.py             static config (title list, renames, allowed schema)

Environment variables: OPENAI_KEY, OPENAI_BASE_URL, OPENAI_MODEL (default gpt-4o-mini),
LOG_LEVEL (DEBUG, INFO (default), WARNING, ERROR). Logs go to stdout (see pipeline_logging.py).
"""
import logging
import os
import sys
import time
from pathlib import Path

from diaries_ingest import DiariesImporter
from full_kg import FullKG
from pipeline_logging import setup_logging, log_stage, log_graph_summary

logger = logging.getLogger("pipeline")


def main():
    t_start = time.time()
    logger.info("Pipeline started, args=%s, cwd=%s", sys.argv[1:], os.getcwd())

    # ---------------- STAGE 1: ingest raw diary pages ----------------
    with log_stage("STAGE 1: ingest diary pages"):
        importing = DiariesImporter(argv=sys.argv[1:])
        base_path = importing.source_dataset_path

        if not base_path:
            logger.warning("Source path directory is mandatory. Setting it to default.")
            base_path = "../../../data/"
        base_path = Path(base_path)

        if not base_path.is_dir():
            logger.error("%s isn't a directory", base_path)
            sys.exit(1)

        diary_file = base_path / "ch8_rac_ww_1939.json"

        if not diary_file.is_file():
            logger.error("%s doesn't exist in %s", diary_file, base_path)
            sys.exit(1)

        importing.ingest_diaries(diary_file)
    log_graph_summary(importing._driver, importing._database, "after ingest")

    # ---------------- STAGES 2-3: LLM extraction + KG build ----------------
    kg = FullKG(argv=sys.argv[1:])

    base_path = kg.source_dataset_path
    if not base_path:
        logger.warning("Source path directory is mandatory. Setting it to default.")
        base_path = "../../../data/"
    base_path = Path(base_path)

    # The prompt files are looked up in the same directory as the dataset.
    prompt_path = kg.source_dataset_path
    if not prompt_path:
        logger.warning("Prompt path directory is mandatory. Setting it to default.")
        prompt_path = "../../../data/"
    prompt_path = Path(prompt_path)

    kg.openai_key = os.environ.get("OPENAI_KEY")
    kg.openai_url = os.environ.get("OPENAI_BASE_URL")
    kg.openai_model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

    # set up a cache folder for LLM responses
    kg.cache_folder = Path("../../../data/cache_llm")
    kg.cache_folder.mkdir(exist_ok=True)
    logger.info("LLM response cache: %s (%d cached answers)", kg.cache_folder.resolve(),
                len(list(kg.cache_folder.glob("*.json"))))

    # build a KG layer (normalise & resolve entities); logs its own sub-stages
    kg.build_kg(prompt_path)

    # ---------------- STAGE 4: graph algorithms ----------------
    with log_stage("STAGE 4: graph algorithms"):
        kg.run_gds()
    log_graph_summary(kg._driver, kg._database, "final")

    logger.info("Pipeline finished successfully in %.1f sec", time.time() - t_start)


if __name__ == "__main__":
    setup_logging()
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        # Full traceback in the container log, non-zero exit code for the orchestrator.
        logger.exception("Pipeline failed")
        sys.exit(1)
