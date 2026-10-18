"""
diaries_ingest.py - STAGE 1: load the raw diary pages into Neo4j.

Aspect: *data loading + DB schema setup*. No LLM, no entity logic.

Resulting graph:
    (:File {name}) -[:CONTAINS_PAGE]-> (:Page {id, page_idx, text})

Input file format (JSON list):
    [{"id": "<file>_<n>", "page_idx": <int>, "text": "<page text>"}, ...]
"""
import json
import logging

from neo4j.exceptions import ClientError as Neo4jClientError, Neo4jError

from util.base_importer import BaseImporter

from pipeline_logging import run_query

logger = logging.getLogger(__name__)


class DiariesImporter(BaseImporter):
    def __init__(self, argv):
        # `command=__file__` + argv are handed to GraphDBBase, which parses CLI options
        # (DB URI, credentials, source dataset path ...).
        super().__init__(command=__file__, argv=argv)
        # self._database = "rac"   # uncomment to write into a non-default database
        # Create constraints/indexes up-front so MERGEs below and in later stages are fast
        # and uniqueness is guaranteed.
        self.create_indices()

    def create_indices(self):
        """Create all constraints and indexes used by the whole pipeline (idempotent)."""
        with self._driver.session(database=self._database) as session:
            # One schema statement per line; they are split on ";" below because a
            # session.run() call accepts only a single statement.
            #  - NODE KEY constraints  = uniqueness + existence, also create a backing index.
            #  - TEXT indexes          = speed up CONTAINS / ENDS WITH / STARTS WITH, which the
            #                            entity-resolution stage uses heavily.
            #  - `name_normalized` is the property set by entity_normalization /
            #    entity_resolution; the final KG nodes are keyed on it.
            query = """
                CREATE CONSTRAINT IF NOT EXISTS FOR (n:File) REQUIRE n.name IS NODE KEY;
                CREATE CONSTRAINT IF NOT EXISTS FOR (n:Page) REQUIRE n.id IS NODE KEY;
                CREATE TEXT INDEX node_entity_name IF NOT EXISTS FOR (n:Entity) ON (n.name);
                CREATE CONSTRAINT IF NOT EXISTS FOR (n:Person) REQUIRE n.name_normalized IS NODE KEY;
                CREATE CONSTRAINT IF NOT EXISTS FOR (n:Organization) REQUIRE n.name_normalized IS NODE KEY;
                CREATE CONSTRAINT IF NOT EXISTS FOR (n:Occupation) REQUIRE n.name_normalized IS NODE KEY;
                CREATE CONSTRAINT IF NOT EXISTS FOR (n:Title) REQUIRE n.name_normalized IS NODE KEY;
                CREATE TEXT INDEX IF NOT EXISTS FOR (n:Person) ON (n.name_normalized);
                CREATE TEXT INDEX IF NOT EXISTS FOR (n:Organization) ON (n.name_normalized);
                CREATE TEXT INDEX IF NOT EXISTS FOR (n:Occupation) ON (n.name_normalized);
                CREATE TEXT INDEX IF NOT EXISTS FOR (n:Title) ON (n.name_normalized);
                CREATE TEXT INDEX rel_text_entities IF NOT EXISTS FOR ()-[r:RELATED_TO_ENTITY]-() ON (r.type)"""
            statements = [q.strip() for q in query.split(";") if q.strip()]
            logger.info("Creating %d constraints/indexes in database '%s'", len(statements), self._database)
            for q in statements:
                description = "Schema: " + " ".join(q.split())[:80]
                try:
                    run_query(session, description, q)
                except Neo4jClientError as e:
                    # An equivalent rule already exists (e.g. an index created earlier under
                    # a different name) - harmless, so ignore it; re-raise anything else.
                    if e.code == "Neo.ClientError.Schema.EquivalentSchemaRuleAlreadyExists":
                        logger.debug("Schema rule already exists, skipped: %s", description)
                        continue
                    raise
                except Neo4jError as e:
                    # NODE KEY constraints exist only in Neo4j Enterprise. On Community Edition
                    # (e.g. the neo4j service in docker-compose.yml) fall back to a plain
                    # uniqueness constraint, which is all the MERGEs in this pipeline need.
                    if "NODE KEY" not in q:
                        raise
                    logger.warning("NODE KEY constraint not supported here (%s); "
                                   "falling back to IS UNIQUE", e.message.splitlines()[0])
                    run_query(session, description + " (fallback)", q.replace("IS NODE KEY", "IS UNIQUE"))

    @staticmethod
    def count_diaries(diaries_file):
        """Number of pages in the JSON file (used only for the progress bar)."""
        return len(json.load(diaries_file.open()))

    @staticmethod
    def get_diaries(diaries_file):
        """Yield every page dict, enriched with the name of the diary file it belongs to."""
        for diary in json.load(diaries_file.open()):
            # Page ids look like "<file name>_<page no>": drop the last "_"-part to get
            # the file name, e.g. "RAC_FA_1_2_3" -> "RAC_FA_1_2".
            diary["file_name"] = "_".join(diary['id'].split("_")[:-1])
            yield diary

    def ingest_diaries(self, diaries_file):
        """Write File and Page nodes (and the CONTAINS_PAGE links) in batches."""
        # `batch_store` (BaseImporter) groups rows into the $batch parameter, so the query
        # must start with UNWIND $batch.
        import_diaries = """
                UNWIND $batch as item
                MERGE (f:File {name: item.file_name})
                MERGE (p:Page {id: item.id})
                SET p.page_idx = item.page_idx, p.text = item.text

                WITH f, p

                MERGE (f)-[:CONTAINS_PAGE]->(p)
                """
        size = self.count_diaries(diaries_file)
        logger.info("Ingesting %d pages from %s (batch size %d)", size, diaries_file, self.batch_size)
        self.batch_store(import_diaries, self.get_diaries(diaries_file), size=size)
        logger.info("Finished ingesting %d pages", size)
