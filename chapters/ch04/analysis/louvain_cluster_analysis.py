from pathlib import Path

from util.graphdb_base import GraphDBBase
from community_scores import getCommunityScores, create_plot
import util.networkx_utility as networkx_utility
import networkx as nx
import pandas as pd
import sys
import time


class ClusterAnalysis(GraphDBBase):
    def __init__(self, argv, database):
        super().__init__(command=__file__, argv=argv)
        self.__database = database

    def get_data(self, query, param={}):
        with self._driver.session(database=self.__database) as session:
            results = session.run(query, param)
            data = pd.DataFrame(results.values(), columns=results.keys())
        return data

    def get_raw_data(self, query, param):
        with self._driver.session(database=self.__database) as session:
            results = session.run(query, param)
            return results.graph()

    def load_full_graph(self):
        query = """
            MATCH (m0:Protein)
            OPTIONAL MATCH (m0)-[r:INTERACTS_WITH]->(m1)
            return distinct m0, r, m1
        """
        return self.load_graph_and_get_nx_graph(query)

    def load_cluster_items(self, cluster_id):
        query = """
            MATCH (p:Protein {componentLouvainId:$cluster_id})
            return id(p) as node_id, p.id as protein_id, p.name as name 
        """
        param = {"cluster_id": int(cluster_id)}
        return self.get_data(query, param)

    def load_hd(self, disease):
        query = """
            MATCH (d:Disease {id:$id})-[:ASSOCIATED_WITH]->(p)
            WITH collect(p) as proteins
            UNWIND proteins as m0
            UNWIND proteins as m1
            OPTIONAL MATCH (m0)-[r:INTERACTS_WITH]->(m1)
            return distinct m0, r, m1
        """
        param = {"id": disease}
        return self.load_graph_and_get_nx_graph(query, param)

    def load_graph_and_get_nx_graph(self, query, param={}):
        data = self.get_raw_data(query, param)
        G = networkx_utility.graph_undirected_from_cypher(data)
        return G

    def compute_largest_components(self, networkx_graph):
        largest_cc = max(nx.connected_components(networkx_graph), key=len)
        return largest_cc

    def get_list_of_clusters(self):
        query = """
            MATCH (n:PPIProtein) 
            WITH n.componentLouvainId as clusterId, count(*) as occurrences
            WHERE occurrences >= 3
            return clusterId as id, occurrences
        """
        return self.get_data(query, {})

    def compute_Bd(self, disease):
        query = """
            MATCH (d:Disease {id:$id})-[:ASSOCIATED_WITH]->(p)
            WITH collect(p) as proteins
            MATCH (m0)-[r:INTERACTS_WITH]-(m1)
            WHERE m0 in proteins and not m1 in proteins
            RETURN count(DISTINCT r) as bd
        """
        param = {'id': disease}

        return self.get_data(query, param)["bd"][0]


def sub_graph(G, largest_wcc):
    # Create a subgraph SG based on a (possibly multigraph) G
    SG = G.__class__()
    SG.add_nodes_from((n, G.nodes[n]) for n in largest_wcc)
    if SG.is_multigraph():
        SG.add_edges_from((n, nbr, key, d)
                          for n, nbrs in G.adj.items() if n in largest_wcc
                          for nbr, keydict in nbrs.items() if nbr in largest_wcc
                          for key, d in keydict.items())
    else:
        SG.add_edges_from((n, nbr, d)
                          for n, nbrs in G.adj.items() if n in largest_wcc
                          for nbr, d in nbrs.items() if nbr in largest_wcc)
    SG.graph.update(G.graph)
    return SG


if __name__ == '__main__':
    base = Path(__file__).parent
    start = time.time()
    analysis = ClusterAnalysis(argv=sys.argv[1:], database="ppi")  # database should be also among the arguments
    clusters = analysis.get_list_of_clusters()
    results = []
    results_second_approach = []
    ppi_graph = analysis.load_full_graph()
    for index, cluster in clusters.iterrows():
        cluster_id = cluster['id']
        cluster_vector = analysis.load_cluster_items(cluster_id)
        cluster_vector_index = [1 if x[1]['id'] in list(cluster_vector['protein_id']) else 0 for x in
                                ppi_graph.nodes(data=True)]
        disease_property = getCommunityScores(ppi_graph, cluster_vector_index)
        disease_property['id'] = cluster_id
        results.append(disease_property)

    df = pd.DataFrame(results)
    largest_cc_frequency = df['percent_in_largest_connected_component'].value_counts(bins=20, sort=False)
    density_frequency = df['density'].value_counts(bins=20, sort=False)
    conductance_frequency = df['conductance'].value_counts(bins=20, sort=False)
    create_plot(df, base / 'louvain_cluster_analysis_plot.png')
    end = time.time() - start
    analysis.close()
    print("Time to complete:", end)
    print("done")
