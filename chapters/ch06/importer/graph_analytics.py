"""
graph_analytics.py - STAGE 4: graph data science on the final KG (Neo4j GDS).

Aspect: *analysis* - nothing here changes the structure of the KG; it only WRITES
scores as node properties:
    Person.wcc                weakly-connected-component id
    Person.pagerank, .eigenvector, .betweenness   centrality of the social network
    Person.community          Louvain community
    Person.pr_influencers, .eigen_influencers     centrality with TALKED_ABOUT reversed

The social network = Person-Person edges TALKED_ABOUT | TALKED_WITH | WORKS_WITH,
treated as undirected, WITHOUT the diary author (Warren Weaver / "WW"), who is
connected to nearly everybody and would dominate every score.
"""
import logging

from pipeline_logging import run_query

logger = logging.getLogger(__name__)


class GraphAnalyticsMixin:
    """Mixin for `FullKG`; needs `self._driver`, `self._database` and the GDS plugin."""

    def run_gds(self):
        # ---- 1. Whole-network projection (used only to find components) ---------------
        QUERY_GRAPH_PROJECTION = """
        MATCH (e1:Person)-[r:TALKED_ABOUT|TALKED_WITH|WORKS_WITH]->(e2:Person)
        WHERE e1.name <> "WW" AND e2.name <> "WW" AND e1.name <> "Warren Weaver" AND e2.name <> "Warren Weaver" // WW is Warren Weaver, the author of these diaries
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

        QUERY_DROP_PROJECTION = "CALL gds.graph.drop('graph') YIELD graphName"

        QUERY_WCC = """
        CALL gds.wcc.write('graph', { writeProperty: 'wcc' })
        YIELD nodePropertiesWritten, componentCount
        """

        # run WCC to identify the largest connected component
        logger.info("Running WCC to identify isolated sub-graphs")
        with self._driver.session(database=self._database) as session:
            run_query(session, "Project the person network", QUERY_GRAPH_PROJECTION, show_result=True)
            run_query(session, "WCC", QUERY_WCC, show_result=True)
            run_query(session, "Drop projection", QUERY_DROP_PROJECTION)

        # ---- 2. Projection of the LARGEST component only -----------------------------
        # Centrality in tiny isolated islands is meaningless, so first find the component
        # id with the most persons, then project only edges inside it.
        QUERY_GRAPH_PROJECTION_SELECTED = """
        MATCH (p:Person)
        WHERE p.wcc is not Null
        WITH p.wcc AS component, count(*) AS num
        ORDER BY num DESC
        LIMIT 1

        WITH component AS largest_wcc

        MATCH (e1:Person)-[r:TALKED_ABOUT|TALKED_WITH|WORKS_WITH]->(e2:Person)
        WHERE e1.name <> "WW" AND e2.name <> "WW" AND e1.name <> "Warren Weaver" AND e2.name <> "Warren Weaver" AND e1.wcc = largest_wcc AND e2.wcc = largest_wcc
        WITH gds.graph.project('graph', e1, e2,
            {
                sourceNodeLabels: labels(e1),
                targetNodeLabels: labels(e2),
                relationshipType: type(r)
                //relationshipProperties: r { .count }
            },
            {undirectedRelationshipTypes: ['*']}
        ) AS g
        RETURN g.graphName AS graph, g.nodeCount AS nodes, g.relationshipCount AS rels
        """

        # Centrality / community algorithms (write mode => results become node properties).
        # PageRank & eigenvector take the target property as a parameter because they are
        # run twice (normal and "influencers" projection).
        QUERY_PAGERANK = """
        CALL gds.pageRank.write('graph', {
          maxIterations: 100,
          dampingFactor: 0.85,
          writeProperty: $property
        })
        YIELD nodePropertiesWritten, ranIterations
        """

        QUERY_EIGENVECTOR = """
        CALL gds.eigenvector.write('graph', {
          maxIterations: 100,
          writeProperty: $property
        })
        YIELD nodePropertiesWritten, ranIterations
        """

        QUERY_BETWEENNESS = """
        CALL gds.betweenness.write('graph', {
          writeProperty: 'betweenness'
        })
        YIELD centralityDistribution, nodePropertiesWritten
        RETURN centralityDistribution.min AS minimumScore, centralityDistribution.mean AS meanScore, nodePropertiesWritten
        """

        QUERY_LOUVAIN = """
        CALL gds.louvain.write('graph', { writeProperty: 'community' })
        YIELD communityCount, modularity, modularities
        """

        logger.info("Running centrality algorithms ...")
        with self._driver.session(database=self._database) as session:
            projection = run_query(session, "Project the largest component", QUERY_GRAPH_PROJECTION_SELECTED,
                                   show_result=True)
            if not projection:
                logger.warning("Largest-component projection is empty (no Person-Person relations?)")
            run_query(session, "PageRank", QUERY_PAGERANK, show_result=True, property="pagerank")
            run_query(session, "Eigenvector centrality", QUERY_EIGENVECTOR, show_result=True, property="eigenvector")
            run_query(session, "Betweenness centrality", QUERY_BETWEENNESS, show_result=True)
            run_query(session, "Louvain community detection", QUERY_LOUVAIN, show_result=True)
            run_query(session, "Drop projection", QUERY_DROP_PROJECTION)

        # ---- 3. "Influencer" projection -----------------------------------------------
        # Same nodes/edges, but the source/target labels are swapped. TALKED_ABOUT is
        # directed (A talked about B); reversing it makes the person who is TALKED ABOUT
        # accumulate score = influence. TALKED_WITH and WORKS_WITH are symmetric, so they
        # stay undirected.
        QUERY_PROJECTION_INFLUENCERS = """
        MATCH (p:Person)
        WHERE p.wcc is not Null
        WITH p.wcc AS component, count(*) AS num
        ORDER BY num DESC
        LIMIT 1

        WITH component AS largest_wcc

        MATCH (e1:Person)-[r:TALKED_ABOUT|TALKED_WITH|WORKS_WITH]->(e2:Person)
        WHERE e1.name <> "WW" AND e2.name <> "WW" AND e1.name <> "Warren Weaver" AND e2.name <> "Warren Weaver" AND e1.wcc = largest_wcc AND e2.wcc = largest_wcc
        WITH gds.graph.project('graph', e1, e2,
            {
                sourceNodeLabels: labels(e2), // we want to inverse the TALKED_ABOUT relations for influencer analysis
                targetNodeLabels: labels(e1),
                relationshipType: type(r)
            },
            {undirectedRelationshipTypes: ['TALKED_WITH', 'WORKS_WITH']}
        ) AS g
        RETURN g.graphName AS graph, g.nodeCount AS nodes, g.relationshipCount AS rels
        """

        logger.info("Running influencers analysis ...")
        with self._driver.session(database=self._database) as session:
            run_query(session, "Project the influencer network", QUERY_PROJECTION_INFLUENCERS, show_result=True)
            run_query(session, "Influencer PageRank", QUERY_PAGERANK, show_result=True, property="pr_influencers")
            run_query(session, "Influencer eigenvector centrality", QUERY_EIGENVECTOR, show_result=True,
                      property="eigen_influencers")
            run_query(session, "Drop projection", QUERY_DROP_PROJECTION)
