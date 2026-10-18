"""
entity_normalization.py - STAGE 3a: cheap, rule-based cleaning of entity names.

Aspect: *normalisation* (deterministic string clean-up, no cross-entity comparison).
Writes the property `name_normalized` on :Entity nodes. That property is the key
that entity_resolution.py refines and kg_builder.py finally MERGEs on.
"""
import logging

from kg_schema import REMOVE_TITLES
from pipeline_logging import run_query

logger = logging.getLogger(__name__)


class EntityNormalizationMixin:
    """Mixin for `FullKG`; needs `self._driver` and `self._database`."""

    def normalize_entities(self):
        # Persons: the LLM sometimes treats a title as part of the name ("Dr. Hale").
        # If the lower-cased name starts with a known title, drop the first word;
        # otherwise keep the name unchanged. Result -> e.name_normalized.
        QUERY_NORM_PERSONS = """
            MATCH (e:Entity {label: "Person"})
            WITH e, CASE WHEN ANY(title IN $remove_titles WHERE toLower(e.name) STARTS WITH title)
                THEN apoc.text.join(split(e.name, " ")[1..], " ")
                ELSE e.name END AS name
            SET e.name_normalized = name
            """

        # Occupations: they represent research disciplines, technologies etc.
        # ("Nuclear Physics" vs "nuclear physics") - case is irrelevant, so lowercase.
        QUERY_NORM_OCCUPATIONS = """MATCH (e:Entity {label: "Occupation"})
            SET e.name_normalized = toLower(e.name)
            """

        with self._driver.session(database=self._database) as session:
            run_query(session, "Normalising Person names", QUERY_NORM_PERSONS, remove_titles=REMOVE_TITLES)
            run_query(session, "Normalising Occupations", QUERY_NORM_OCCUPATIONS)
