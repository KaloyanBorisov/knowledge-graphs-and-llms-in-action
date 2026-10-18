"""
graph_store.py - persistence of raw LLM output ("staging layer") in Neo4j.

Aspect: *writing/cleaning the intermediate graph*.

Staging graph created here (kept separate from the final KG built in kg_builder.py):

    (:Page:GPTProcessed) -[:MENTIONS_ENTITY {runs}]-> (:Entity {label, name, id, ...})
    (:Entity) -[:RELATED_TO_ENTITY {type, runs, ...}]-> (:Entity)
    (:Entity {name: <title>})  <-[:RELATED_TO_ENTITY {type:"HAS_TITLE"}]- (:Entity)

`:GPTProcessed` is the marker that stops a page being sent to the LLM again.
"""
import logging

from pipeline_logging import run_query

logger = logging.getLogger(__name__)


class GraphStoreMixin:
    """Mixin for `FullKG`; needs `self._driver` and `self._database` (BaseImporter)."""

    def store_to_neo4j(self, doc_id: int, entities: list, relations: list, run: str):
        """
        Persist the extraction result of ONE page.

        :param doc_id: Neo4j internal id of the :Page node (`id(p)`, not the `Page.id` property)
        :param entities: parsed entity dicts (see LLMExtractionMixin.parse_gpt_output)
        :param relations: parsed relation dicts, each with `source` / `target` entity ids
        :param run: name of the extraction run, appended to the `runs` list of every edge
        """
        # (1) Mark the page as processed, keep the raw entity JSON on it for traceability
        #     and create one :Entity node per extracted entity, linked from the page.
        #     `e += ent` copies all LLM-provided properties onto the node.
        QUERY_WRITE_ENTS = """
        MATCH (n)
        WHERE id(n) = $id
        SET n:GPTProcessed,
        n.GPT_metadata_entities = '{"GPTMetadataEntities":' + apoc.convert.toJson($entities) + "}",
        n.prompt_version = "1"
        WITH n

        UNWIND $entities AS ent

        CREATE (e:Entity)
        SET e += ent,
        e.all_properties = apoc.convert.toJson(ent)

        WITH n, e

        MERGE (n)-[r:MENTIONS_ENTITY]->(e)
        ON CREATE SET r.runs = [$run]
        ON MATCH SET r.runs = apoc.coll.toSet(r.runs + [$run])

        RETURN count(*) AS count
        """

        # (3) Relations connect two entities that were both mentioned on THIS page
        #     (matching `rel.source`/`rel.target` against the entity `id` the LLM assigned,
        #     which is only unique within a page).
        QUERY_WRITE_RELS = """
        MATCH (n)
        WHERE id(n) = $id
        SET n:GPTProcessed,
        n.GPT_metadata_relations = '{"GPTMetadataRelations":' + apoc.convert.toJson($relations) + "}",
        n.prompt_version = "1"
        WITH n

        UNWIND $relations AS rel

        MATCH (n)-[:MENTIONS_ENTITY]->(e1:Entity {id: rel.source})
        MATCH (n)-[:MENTIONS_ENTITY]->(e2:Entity {id: rel.target})

        MERGE (e1)-[r:RELATED_TO_ENTITY {type: rel.type}]->(e2)
        ON CREATE SET r.runs = [$run]
        ON MATCH SET r.runs = apoc.coll.toSet(r.runs + [$run])
        SET r += rel, r.all_properties = apoc.convert.toJson(rel)

        RETURN count(*) AS count
        """

        # (2) Persons may carry a `titles` list (e.g. ["Professor of Physics"]). Turn each
        #     title into its own Entity and link it with a HAS_TITLE relation.
        #     Runs between (1) and (3) so title entities exist for the page.
        QUERY_TITLES = """
        MATCH (n)-[:MENTIONS_ENTITY]->(e)
        WHERE id(n) = $id AND e.titles IS NOT Null

        UNWIND e.titles AS tit

        CREATE (t:Entity {name: tit})
        MERGE (n)-[:MENTIONS_ENTITY]->(t)
        MERGE (e)-[:RELATED_TO_ENTITY {type: "HAS_TITLE"}]->(t)
        """

        # Order matters: entities -> titles -> relations.
        logger.debug("Storing page node id=%s: %d entities, %d relations (%s)", doc_id, len(entities),
                     len(relations), run)
        with self._driver.session(database=self._database) as session:
            run_query(session, f"Store entities of page node {doc_id}", QUERY_WRITE_ENTS,
                      id=doc_id, entities=entities, run=run)
            run_query(session, f"Store titles of page node {doc_id}", QUERY_TITLES,
                      id=doc_id, entities=entities)
            records = run_query(session, f"Store relations of page node {doc_id}", QUERY_WRITE_RELS,
                                id=doc_id, relations=relations, run=run)
            # Each relation needs BOTH endpoint entities on the page; if the LLM referenced an
            # unknown id the MATCH finds nothing and the relation is silently dropped.
            stored = records[0]['count'] if records else 0
            if stored < len(relations):
                logger.warning("Page node %s: only %d of %d relations could be stored "
                               "(source/target entity id not found on the page)", doc_id, stored, len(relations))

    def cleanse_stability_test(self, keep_run: str):
        """
        Utility for comparing repeated extraction runs ("stability test").
        Keeps only what `keep_run` produced:
          - deletes entities mentioned by a processed page that were NOT created in `keep_run`
          - deletes entity-entity relations NOT produced in `keep_run`
        NOT called by the default pipeline.
        """
        CLEANSING_QUERIES = ["""MATCH (p:GPTProcessed)-[r:MENTIONS_ENTITY]->(e)
        WHERE NOT $keep_run IN r.runs
        DETACH DELETE e
        """,
                             """MATCH (p:GPTProcessed)-[:MENTIONS_ENTITY]->(e)-[r:RELATED_TO_ENTITY]->(e2)
                             WHERE NOT $keep_run IN r.runs
                             DELETE r
                             """]
        logger.info("Cleansing the staging graph, keeping only run '%s'", keep_run)
        with self._driver.session(database=self._database) as session:
            for i, query in enumerate(CLEANSING_QUERIES, start=1):
                run_query(session, f"Cleansing query {i}/{len(CLEANSING_QUERIES)}", query, keep_run=keep_run)
