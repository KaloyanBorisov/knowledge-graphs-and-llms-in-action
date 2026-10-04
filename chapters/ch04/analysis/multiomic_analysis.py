from pathlib import Path

from util.graphdb_base import GraphDBBase
from community_scores import getCommunityScores, create_plot

import networkx as nx
import pandas as pd
import sys
import time
from util.networkx_utility import graph_undirected_from_cypher


class MultiOmicAnalysis(GraphDBBase):
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

    def load_assoc_gene_vector(self, disease):
        query = """
            MATCH (d:Disease {id:$id})-[:ASSOCIATED_WITH]->(p)
            return id(p) as node_id, p.id as protein_id 
        """
        param = {"id": disease}
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
        G = graph_undirected_from_cypher(data)
        return G

    def compute_largest_components(self, networkx_graph):
        largest_cc = max(nx.connected_components(networkx_graph), key=len)
        return largest_cc

    def get_list_of_diseases(self):
        query = """
            MATCH (d:Disease)
            return d.id as id, d.name as name
        """
        return self.get_data(query, {})

    def compute_bd(self, disease):
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
    analysis = MultiOmicAnalysis(argv=sys.argv[1:], database="ppi")  # database should be also among the arguments
    diseases = analysis.get_list_of_diseases()
    # networkx_graph = analysis.load_hd("C0036095") #Salivary Gland Neoplasms
    # networkx_graph = analysis.load_hd("C0019693")  # HIV Infections
    results = []
    results_second_approach = []
    ppi_graph = analysis.load_full_graph()
    for index, disease in diseases.iterrows():
        disease_id = disease['id']
        assoc_gene_vector = analysis.load_assoc_gene_vector(disease_id)
        assoc_gene_vector_index = [1 if x[1]['id'] in list(assoc_gene_vector['protein_id']) else 0 for x in
                                   ppi_graph.nodes(data=True)]
        disease_property = getCommunityScores(ppi_graph, assoc_gene_vector_index)
        disease_property['id'] = disease['id']
        disease_property['name'] = disease['name']
        results.append(disease_property)

        networkx_graph = analysis.load_hd(disease_id)
        bd = analysis.compute_bd(disease_id)
        nodes_count = networkx_graph.nodes.__len__()
        edges_count = networkx_graph.edges.__len__()
        largest_cc = analysis.compute_largest_components(networkx_graph)
        largest_cc_size = largest_cc.__len__()
        relative_size_of_largest_cc = float(largest_cc_size) / nodes_count
        density_pathway = 2.0 * float(edges_count) / (nodes_count * (nodes_count - 1))
        conductance = float(bd) / (bd + 2 * edges_count)
        results_second_approach.append({
            'id': disease['id'],
            'name': disease['name'],
            'relative_size_of_largest_cc': relative_size_of_largest_cc,
            'nodes_count': nodes_count,
            'largest_cc_size': largest_cc_size,
            'density_pathway': density_pathway,
            'conductance': conductance}
        )

    df = pd.DataFrame(results)
    largest_cc_frequency = df['percent_in_largest_connected_component'].value_counts(bins=20, sort=False)
    density_frequency = df['density'].value_counts(bins=20, sort=False)
    conductance_frequency = df['conductance'].value_counts(bins=20, sort=False)

    df2 = pd.DataFrame(results_second_approach)
    largest_cc_frequency2 = df2['relative_size_of_largest_cc'].value_counts(bins=20, sort=False)
    density_frequency2 = df2['density_pathway'].value_counts(bins=20, sort=False)
    conductance_frequency2 = df2['conductance'].value_counts(bins=20, sort=False)
    create_plot(df, base/'pharma_analysis_plot.png')
    end = time.time() - start
    analysis.close()
    print("Time to complete:", end)
    print("done")
