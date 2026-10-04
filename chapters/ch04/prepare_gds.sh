#!/bin/bash
# Listings 4.7-4.10: label proteins, project the graph, run WCC and Louvain in the ppi database
set -e
run() { cypher-shell -a "$NEO4J_URI" -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" -d "$1" "$2"; }

echo "waiting for the ppi database (seed restore)..."
until [ "$(run system "SHOW DATABASE ppi YIELD currentStatus RETURN currentStatus" 2>/dev/null | tail -n1)" = '"online"' ]; do
  sleep 5
done

run ppi "MATCH (p:Protein)-[:INTERACTS_WITH]-() SET p:PPIProtein"
run ppi "CALL gds.graph.drop('ppi-graph', false) YIELD graphName RETURN graphName"
run ppi "CALL gds.graph.project('ppi-graph', 'PPIProtein', {INTERACTS_WITH: {orientation: 'UNDIRECTED'}})"
run ppi "CALL gds.wcc.write('ppi-graph', {writeProperty: 'componentId'}) YIELD componentCount RETURN componentCount"
run ppi "CALL gds.louvain.write('ppi-graph', {writeProperty: 'componentLouvainId'}) YIELD communityCount, modularity RETURN communityCount, modularity"
