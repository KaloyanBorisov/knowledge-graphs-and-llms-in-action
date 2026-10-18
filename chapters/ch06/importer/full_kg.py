"""
full_kg.py - composition root of the KG-building pipeline.

`FullKG` owns no logic of its own except the ORDER of the stages; each aspect lives
in a mixin module:

    LLMExtractionMixin         llm_extraction.py        STAGE 2   pages  -> LLM -> entities/relations
    GraphStoreMixin            graph_store.py           (STAGE 2) persist raw LLM output
    EntityNormalizationMixin   entity_normalization.py  STAGE 3a  clean names
    EntityResolutionMixin      entity_resolution.py     STAGE 3b  merge duplicate persons
    KGBuilderMixin             kg_builder.py            STAGE 3c  create clean KG
    GraphAnalyticsMixin        graph_analytics.py       STAGE 4   GDS scores & communities

All mixins share `self._driver` / `self._database` inherited from BaseImporter.
"""
from pathlib import Path

from util.base_importer import BaseImporter

from entity_normalization import EntityNormalizationMixin
from entity_resolution import EntityResolutionMixin
from graph_analytics import GraphAnalyticsMixin
from graph_store import GraphStoreMixin
from kg_builder import KGBuilderMixin
from llm_extraction import LLMExtractionMixin
from pipeline_logging import log_stage, log_graph_summary


class FullKG(LLMExtractionMixin, GraphStoreMixin, EntityNormalizationMixin, EntityResolutionMixin,
             KGBuilderMixin, GraphAnalyticsMixin, BaseImporter):
    def __init__(self, argv):
        super().__init__(command=__file__, argv=argv)
        # Folder for cached LLM answers (None disables caching). Set by the entry point.
        self.cache_folder: Path = None
        # self._database = "rac"   # uncomment to use a non-default database
        # LLM settings - overwritten by the entry point from OPENAI_* env variables.
        self.openai_model = "gpt-4o-mini"
        self.openai_key = None
        self.openai_url = None
        # Counters filled by LLMExtractionMixin and reported at the end of STAGE 2.
        self.llm_stats = {'cache_hits': 0, 'api_calls': 0, 'prompt_tokens': 0, 'completion_tokens': 0}

    def build_kg(self, prompt_path: Path):
        """Run STAGE 2 and STAGE 3 end to end (STAGE 4 is `run_gds`, called separately)."""
        # Select pages that were not sent to the LLM yet; `:GPTProcessed` is set by
        # GraphStoreMixin.store_to_neo4j. Ordered by page_idx, capped by $limit.
        QUERY_READ = """
            MATCH (p:Page)
            WHERE NOT p:GPTProcessed
            RETURN id(p) AS id,p.id as key, p.text AS text
            ORDER BY p.page_idx
            LIMIT $limit
            """
        # STAGE 2: LLM extraction (+ store raw entities/relations)
        with log_stage("STAGE 2: LLM extraction"):
            prompt_segments = self.read_prompt(prompt_path)
            self.process_diaries_gpt(QUERY_READ, prompt_segments, n_docs=100)
        log_graph_summary(self._driver, self._database, "after LLM extraction")

        # STAGE 3a: normalise entities
        with log_stage("STAGE 3a: normalise entities"):
            self.normalize_entities()

        # STAGE 3b: resolve entities such as person names
        with log_stage("STAGE 3b: resolve entities"):
            self.resolve_entities()

        # STAGE 3c: create a final clean KG
        with log_stage("STAGE 3c: create KG"):
            self.create_kg()
        log_graph_summary(self._driver, self._database, "after KG creation")
