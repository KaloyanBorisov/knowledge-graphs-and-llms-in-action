"""
kg_builder.py - STAGE 3c: build the final, clean knowledge graph.

Aspect: *projection of the staging graph onto the target schema*.
Reads  : (:Page)-[:MENTIONS_ENTITY]->(:Entity)-[:RELATED_TO_ENTITY]->(:Entity)   (raw, noisy)
Writes : (:Person|:Organization|:Occupation|:Title) nodes keyed by name_normalized,
         connected by the relationship types listed in kg_schema.SCHEMA.
Also keeps lineage links raw Entity -[:MAPPED_TO_<LABEL>]-> clean node.
"""
import logging

from kg_schema import RENAME_ENTS, RENAME_RELS, SCHEMA
from pipeline_logging import run_query

logger = logging.getLogger(__name__)


class KGBuilderMixin:
    """Mixin for `FullKG`; needs `self._driver` and `self._database`."""

    def create_kg(self):
        # ---- 1. Reset the KG: it is derived data and fully rebuilt on each run --------
        # The staging graph (Page / Entity) is NOT touched, so this is cheap and safe.
        QUERY_DELETE_KG = """MATCH (n)
        WHERE n:Person OR n:Organization OR n:Occupation OR n:Title
        DETACH DELETE n
        """
        with self._driver.session(database=self._database) as session:
            run_query(session, "Deleting the previous KG", QUERY_DELETE_KG)

        # ---- 2. Create nodes + relationships ------------------------------------------
        # Flow of the query:
        #   a) take every raw relation (e1)-[r]->(e2) with the page that mentions e1
        #   b) rename labels / relation types via the $rename_* maps (unknown -> unchanged)
        #   c) UNWIND $schema and keep only rows matching an allowed (label, type, label) triple
        #   d) MERGE clean node n1 / n2 by lower-cased name_normalized, counting occurrences
        #      and copying `titles` / `type` attributes
        #   e) link raw entity -> clean node (MAPPED_TO_<LABEL>) for traceability
        #   f) MERGE the clean relationship n1-[relation]->n2, counting how many raw
        #      relations support it (`count`, `orig_ids`) and keeping sentiment/conversation_type
        QUERY_CREATE_KG = """
        MATCH (p:Page)-[:MENTIONS_ENTITY]->(e1:Entity)-[r:RELATED_TO_ENTITY]->(e2)
        WITH p, e1, r, e2,
        CASE WHEN $rename_ents[e1.label] is Null THEN e1.label ELSE $rename_ents[e1.label] END AS label1,
        CASE WHEN $rename_rels[r.type] is Null THEN r.type ELSE $rename_rels[r.type] END AS relation,
        CASE WHEN $rename_ents[e2.label] is Null THEN e2.label ELSE $rename_ents[e2.label] END AS label2

        UNWIND $schema AS kg_rel

        WITH p, e1, r, e2, label1, relation, label2, kg_rel
        WHERE label1 = kg_rel[0] AND label2 = kg_rel[2] AND relation = kg_rel[1]

        CALL apoc.merge.node([label1], {name_normalized: toLower(coalesce(e1.name_normalized, e1.name))}, {name: coalesce(e1.name_normalized, e1.name), count: 0}) YIELD node AS n1
        SET n1.count = n1.count + 1,
        n1.titles = CASE WHEN e1.titles IS NOT Null THEN e1.titles ELSE Null END,
        n1.type = CASE WHEN e1.type IS NOT Null THEN e1.type ELSE Null END
        WITH p, e1, r, e2, label1, relation, label2, n1
        CALL apoc.merge.relationship(e1, "MAPPED_TO_" + toUpper(label1), {}, {}, n1) YIELD rel
        WITH p, e1, r, e2, label1, relation, label2, n1

        CALL apoc.merge.node([label2], {name_normalized: toLower(coalesce(e2.name_normalized, e2.name))}, {name: coalesce(e2.name_normalized, e2.name), count: 0}) YIELD node AS n2
        SET n2.count = n2.count + 1,
        n2.titles = CASE WHEN e2.titles IS NOT Null THEN e2.titles ELSE Null END,
        n2.type = CASE WHEN e2.type IS NOT Null THEN e2.type ELSE Null END
        WITH p, e1, r, e2, label1, relation, label2, n1, n2
        CALL apoc.merge.relationship(e2, "MAPPED_TO_" + toUpper(label2), {}, {}, n2) YIELD rel
        WITH p, e1, r, e2, label1, relation, label2, n1, n2

        CALL apoc.merge.relationship(n1, relation, {}, {count: 0, orig_ids: []}, n2) YIELD rel
        SET rel.count = rel.count + 1, rel.orig_ids = rel.orig_ids + [id(r)],
        rel.sentiment = CASE WHEN r.sentiment IS NOT Null THEN r.sentiment ELSE Null END,
        rel.conversation_type = CASE WHEN r.conversation_type IS NOT Null THEN r.conversation_type ELSE Null END

        RETURN count(distinct rel) AS n_rels
        """

        with self._driver.session(database=self._database) as session:
            records = run_query(session, "Creating the KG nodes and relationships", QUERY_CREATE_KG,
                                rename_ents=RENAME_ENTS, rename_rels=RENAME_RELS, schema=SCHEMA)
            if records:
                logger.info("Created %d KG relations", records[0]['n_rels'])
            else:
                logger.warning("No KG relations created - did the LLM extraction produce any entities "
                               "matching the schema?")

        # ---- 3. Similarity edges between clean nodes -----------------------------------
        # "Johns Hopkins University" -SIMILAR_ORGANIZATION-> "Johns Hopkins" (substring),
        # with generic names excluded. Lets queries roll variants up to one organisation.
        QUERY_SIM_ORG = """
        MATCH (e1:Organization), (e2:Organization)
        WHERE e1<>e2 AND e1.name_normalized CONTAINS e2.name_normalized AND NOT e2.name_normalized IN ["university", "foundation"]
        MERGE (e1)-[:SIMILAR_ORGANIZATION]->(e2)
        """

        QUERY_SIM_OCC = """
        MATCH (e1:Occupation), (e2:Occupation)
        WHERE e1<>e2 AND e1.name_normalized CONTAINS e2.name_normalized AND NOT e2.name_normalized IN ["research"]
        MERGE (e1)-[:SIMILAR_OCCUPATION]->(e2)
        """

        with self._driver.session(database=self._database) as session:
            run_query(session, "Creating Organization similarities", QUERY_SIM_ORG)
            run_query(session, "Creating Occupation similarities", QUERY_SIM_OCC)
