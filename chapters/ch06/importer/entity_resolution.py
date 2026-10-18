"""
entity_resolution.py - STAGE 3b: entity resolution (ER) / de-duplication.

Aspect: *deciding which :Entity nodes denote the same real-world thing*.
Resolution is done by OVERWRITING `name_normalized`, so that the MERGE in
kg_builder.create_kg later collapses all variants into one node.

Persons are the hard case in the diaries ("George E. Hale", "G. E. Hale", "Hale"):
    1. same page            surname -> full name           (very high confidence)
    2. previous page        surname -> full name           (diary entries span pages)
    3. META_SIMILAR         link similar Occupations / Organizations (evidence helper)
    4. META_RESOLVED_PER    surname + shared org/occupation/title as extra evidence
                            (edge only - the rename is intentionally commented out)
    5. META_PERSONS_SIMILAR initials-aware name match -> WCC clusters -> longest name wins
"""
import logging

from pipeline_logging import run_query

logger = logging.getLogger(__name__)


class EntityResolutionMixin:
    """Mixin for `FullKG`; needs `self._driver`, `self._database` and the GDS plugin."""

    def resolve_entities(self):
        ### ER of Persons
        #   - update properties `name_normalized` so that in the KG creation step, the resolved entities get merged

        # ---- Step 1: surname -> full name on the SAME page ------------------------
        # e2 ("Hale") and e1 ("George E. Hale") are both mentioned by page p, and the
        # normalised full name ends with " <surname>". size(...) > 2 skips 1-2 letter
        # names such as initials/"WW" that would match far too much.
        QUERY_RESOLVE_SAME_PAGE = """
        MATCH (e2:Entity {label: "Person"})<-[:MENTIONS_ENTITY]-(p:Page)-[:MENTIONS_ENTITY]->(e1:Entity {label: "Person"})
        WHERE e1.name_normalized ENDS WITH " " + e2.name_normalized AND size(e1.name) > 2 AND size(e2.name) > 2
        SET e2.name_normalized = e1.name_normalized // set new name to full name
        """

        # ---- Step 2: surname -> full name from the PREVIOUS page ---------------------
        # Same idea, but e1 lives on page n-1 of the same File and e2 on page n
        # (e.g. "Lewis" on page 17 -> "Ivey F. Lewis" on page 16).
        QUERY_RESOLVE_PREVIOUS_PAGE = """
        MATCH (f:File)-[:CONTAINS_PAGE]->(p1:Page)-[:MENTIONS_ENTITY]->(e1:Entity {label: "Person"})
        MATCH (f)-[:CONTAINS_PAGE]->(p2:Page)-[:MENTIONS_ENTITY]->(e2:Entity {label: "Person"})
        WHERE p1.page_idx = p2.page_idx - 1 AND e1.name_normalized ENDS WITH " " + e2.name_normalized AND size(e1.name) > 2 AND size(e2.name) > 2
        SET e2.name_normalized = e1.name_normalized // set new name to full name from previous page
        """

        with self._driver.session(database=self._database) as session:
            run_query(session, "ER step 1: resolve surnames on the same page", QUERY_RESOLVE_SAME_PAGE)
            run_query(session, "ER step 2: resolve surnames from the previous page", QUERY_RESOLVE_PREVIOUS_PAGE)

        # leverage outputs of RE, examples:
        #   - "I. B. Conant" (page 79) - WORKS_FOR -> "Harvard University" <- WORKS_FOR - "Conant" (page 52)
        #   - "A. Bearden" (page 69) - WORKS_FOR -> "Johns Hopkins" <- WORKS_FOR - "J. A. Bearden" (page 68)
        #       and HAS_TITLE relation to "Associate Professor of Physics"
        #   - "D. H. Andrews" (page  67) - WORKS_ON -> "specific heats of organic compounds" <- WORKS_ON - "Andrews" (page 79)

        # ---- Step 3: META_SIMILAR links between near-duplicate Occupations/Orgs -------
        # "nuclear physics research" CONTAINS "nuclear physics" -> link them, so step 4
        # can treat two slightly different org/occupation names as "the same thing".
        # Overly generic names are excluded or everything would link to them.
        QUERY_SIMILAR_OCC = """
        MATCH (e1:Entity {label: "Occupation"}), (e2:Entity {label: "Occupation"})
        WHERE e1 <> e2 AND e1.name_normalized CONTAINS e2.name_normalized AND NOT e2.name_normalized IN ["research"]
        MERGE (e1)-[:META_SIMILAR]->(e2)
        """
        QUERY_SIMILAR_ORG = """
        MATCH (e1:Entity {label: "Organization"}), (e2:Entity {label: "Organization"})
        WHERE e1 <> e2 AND toLower(e1.name) CONTAINS toLower(e2.name) AND NOT toLower(e2.name) IN ["university", "foundation"]
        MERGE (e1)-[:META_SIMILAR]->(e2)
        """

        with self._driver.session(database=self._database) as session:
            run_query(session, "ER step 3a: link similar Occupations", QUERY_SIMILAR_OCC)
            run_query(session, "ER step 3b: link similar Organizations", QUERY_SIMILAR_ORG)

        # ---- Step 4: META_RESOLVED_PER (surname + shared context) -----------------
        # Prepare for resolution of surnames - the same surname alone is not enough to resolve, we need additional evidence.
        # Evidence = both persons are linked by WORKS_FOR / WORKS_ON / HAS_TITLE to the
        # same (or META_SIMILAR) organization / occupation / title.
        # NOTE: it only creates the META_RESOLVED_PER edge; applying the rename is disabled
        # (commented-out SET at the end), so this is currently an annotation, not a merge.
        QUERY_RESOLVE_PER_SURNAMES = """
            WITH ["WORKS_FOR", "WORKS_ON", "HAS_TITLE"] AS er_relations
            MATCH (e1:Entity {label: "Person"}), (e2:Entity {label: "Person"})
            WHERE e1.name_normalized ENDS WITH " " + e2.name_normalized AND size(e1.name) > 2 AND size(e2.name) > 2
            WITH er_relations, e1, e2
            MATCH path=(e1)-[r1:RELATED_TO_ENTITY]->()-[:META_SIMILAR]-()<-[r2:RELATED_TO_ENTITY]-(e2)
            WHERE r1.type IN er_relations AND r2.type IN er_relations
            MERGE (e1)-[:META_RESOLVED_PER]-(e2)
            ////////SET e2.name_normalized = e1.name_normalized
            """

        # ---- Step 5: initials-aware similarity -> META_PERSONS_SIMILAR ---------------
        # Prepare for resolution of Persons - consider specifics of person names ("James T. Kirk" <=> "J. T. Kirk" <=> "James Kirk" <=> "J. Kirk")
        #   - for more stringent approach, replace the 1st MATCH with the commented MATCH and uncomment the additional conditions in WHERE clause
        # Logic: same last name; both have at least first+last; compare the "first names"
        # (everything but the last token):
        #   * equal count  -> each pair must share the initial letter and at least one side
        #                     must be just an initial ("J" or "J.")
        #   * counts 1 vs 2 -> a middle name is missing on one side; compare first token only
        QUERY_RESOLVE_PER_SIM = """MATCH (e1:Entity {label: "Person"}), (e2:Entity {label: "Person"})
        //MATCH (e1:Entity {label: "Person"})-[r1:RELATED_TO_ENTITY]->()-[:META_SIMILAR]-()<-[r2:RELATED_TO_ENTITY]-(e2:Entity {label: "Person"})
        WHERE e1.name_normalized ENDS WITH " " + split(e2.name_normalized, " ")[-1] AND size(split(e1.name_normalized, " ")) > 1 AND size(split(e2.name_normalized, " ")) > 1
              //AND r1.type IN ["WORKS_FOR", "WORKS_ON"] AND r2.type IN ["WORKS_FOR", "WORKS_ON"]

        WITH e1, e2, split(e1.name_normalized, " ")[0..-1] AS firsts1, split(e2.name_normalized, " ")[0..-1] AS firsts2
        WITH e1, e2, (CASE
          WHEN size(firsts1) = size(firsts2) THEN ALL(iii IN range(0, size(firsts1) - 1) WHERE substring(firsts1[iii], 0, 1) = substring(firsts2[iii], 0, 1) AND (size(firsts1[iii]) = 1 OR size(firsts2[iii]) = 1 OR (size(firsts1[iii]) = 2 AND substring(firsts1[iii], size(firsts1[iii]) - 1, size(firsts1[iii])) = ".") OR (size(firsts2[iii]) = 2 AND substring(firsts2[iii], size(firsts2[iii]) - 1, size(firsts2[iii])) = ".")))
          WHEN (size(firsts1) = 1 AND size(firsts2) = 2) OR (size(firsts1) = 2 AND size(firsts2) = 1) THEN substring(firsts1[0], 0, 1) = substring(firsts2[0], 0, 1) AND (size(firsts1[0]) = 1 OR size(firsts2[0]) = 1 OR (size(firsts1[0]) = 2 AND substring(firsts1[0], size(firsts1[0]) - 1, size(firsts1[0])) = ".") OR (size(firsts2[0]) = 2 AND substring(firsts2[0], size(firsts2[0]) - 1, size(firsts2[0])) = ".")) // when middle name is skipped for one person
          ELSE false END) AS are_similar
        WHERE are_similar = True

        MERGE (e1)-[:META_PERSONS_SIMILAR]-(e2)
        """

        # Project the META_PERSONS_SIMILAR edges into an in-memory GDS graph named 'graph'
        # (undirected) so that Weakly Connected Components can group transitive matches
        # ("J. Kirk" ~ "James T. Kirk" ~ "J. T. Kirk" -> one cluster).
        QUERY_PER_SIM_GRAPH = """MATCH (e1:Entity {label: "Person"})-[r:META_PERSONS_SIMILAR]->(e2)
        WITH gds.graph.project('graph', e1, e2,
          {
            sourceNodeLabels: labels(e1),
            targetNodeLabels: labels(e2),
            relationshipType: type(r)
          },
          {undirectedRelationshipTypes: ['*']}
        ) AS g
        RETURN g.graphName AS graph, g.nodeCount AS nodes, g.relationshipCount AS rels
        """

        # For every WCC cluster pick the LONGEST name (= the most complete one) and write
        # it into name_normalized of all members of the cluster.
        QUERY_RESOLVE_PER = """MATCH (p:Entity)
        WHERE p.resolution_wcc IS NOT Null
        WITH p.resolution_wcc AS wcc, p.name_normalized AS name
        ORDER BY size(name) DESC
        WITH wcc, collect(name)[0] AS wcc_name
        MATCH (p:Entity)
        WHERE p.resolution_wcc = wcc
        SET p.name_normalized = wcc_name"""

        with self._driver.session(database=self._database) as session:
            run_query(session, "ER step 4: surname + shared context evidence", QUERY_RESOLVE_PER_SURNAMES)
            run_query(session, "ER step 5a: initials-aware person similarity", QUERY_RESOLVE_PER_SIM)
            projection = run_query(session, "ER step 5b: project similarity graph", QUERY_PER_SIM_GRAPH,
                                   show_result=True)
            if not projection:
                logger.warning("No META_PERSONS_SIMILAR edges found - GDS projection is empty, "
                               "the next GDS calls will probably fail")
            # write each node's component id into `resolution_wcc`
            run_query(session, "ER step 5c: WCC clustering",
                      "CALL gds.wcc.write('graph', { writeProperty: 'resolution_wcc' }) YIELD nodePropertiesWritten, componentCount",
                      show_result=True)
            # free the in-memory projection (the name 'graph' is reused by graph_analytics)
            run_query(session, "ER step 5d: drop projection", "CALL gds.graph.drop('graph') YIELD graphName")
            run_query(session, "ER step 5e: longest name wins per cluster", QUERY_RESOLVE_PER)
