import matplotlib.pyplot as plt
import networkx as nx
import numpy as np


def getCommunityScores(nx_graph, assoc_gene_vector):
    adjacency_matrix = nx.adjacency_matrix(nx_graph)
    disease_properties = {}
    disease_indices = np.nonzero(assoc_gene_vector)[0]
    num_total_nodes = adjacency_matrix.shape[0]
    num_total_edges = (np.sum(adjacency_matrix) - sum(adjacency_matrix.diagonal())) / 2 + sum(
        adjacency_matrix.diagonal())

    num_nodes = len(disease_indices)
    disease_properties["num_nodes"] = num_nodes

    subgraph = nx_graph.subgraph([list(nx_graph.nodes())[i] for i in disease_indices])
    sliced_adj_matrix = adjacency_matrix[disease_indices, :]
    num_disease_node_edges = np.sum(
        sliced_adj_matrix)  # here no need to divide by 2 since the matrix is not simmetric anymore after the slicing, the self loop are not an issue since they are counted once
    sub_adj_matrix = sliced_adj_matrix[:, disease_indices]
    num_internal_edges = (np.sum(sub_adj_matrix) - np.sum(sub_adj_matrix.diagonal())) / 2 + np.sum(
        sub_adj_matrix.diagonal())
    external_edges = num_disease_node_edges - num_internal_edges

    # Internal connectivity
    disease_properties["density"] = nx.density(subgraph)
    disease_properties["average_degree"] = 2 * num_internal_edges / num_nodes
    disease_properties["average_internal_clustering"] = nx.average_clustering(subgraph)

    conn_comps = nx.connected_components(subgraph)
    sorted_cc = [len(c) for c in sorted(conn_comps, key=len, reverse=True)]
    disease_properties["size_largest_connected_component"] = sorted_cc[0]
    disease_properties["percent_in_largest_connected_component"] = float(sorted_cc[0]) / num_nodes
    disease_properties["number_connected_components"] = len(sorted_cc)

    # External connectivity
    disease_properties["expansion"] = external_edges / num_nodes
    disease_properties["cut_ratio"] = external_edges / (num_nodes * (num_total_nodes - num_nodes))

    # External and internal connectivity
    disease_properties["conductance"] = external_edges / (2 * num_internal_edges + external_edges)
    disease_properties["normalized_cut"] = disease_properties["conductance"] + external_edges / (
            2 * (num_total_edges - num_internal_edges) + external_edges)

    return disease_properties


def create_plot(dataframe, filename):
    cm = 1 / 2.54
    fig, axs = plt.subplots(1, 3, tight_layout=True, figsize=(35 * cm, 10 * cm))
    counts, bins = np.histogram(dataframe['percent_in_largest_connected_component'].values, bins=20)
    axs[0].hist(bins[:-1], bins, weights=counts, facecolor='g', align='mid', edgecolor="black", linewidth=0.4)
    # axs[0].set_xlabel('Value')
    axs[0].set_ylabel('Occurrences', fontsize=22)
    axs[0].set_title('a) Largest CC', fontsize=22)
    axs[0].tick_params(labelsize='x-large', width=2)
    axs[0].margins(x=0.01)
    counts, bins = np.histogram(dataframe['density'].values, bins=20)
    axs[1].hist(bins[:-1], bins, weights=counts, facecolor='g', align='mid', edgecolor="black", linewidth=0.4)
    # axs[1].set_ylabel('Occurrences')
    axs[1].set_title('b) Density', fontsize=22)
    axs[1].margins(x=0.01)
    axs[1].tick_params(labelsize='x-large', width=2)
    counts, bins = np.histogram(dataframe['conductance'].values, bins=20)
    axs[2].hist(bins[:-1], bins, weights=counts, facecolor='g', align='mid', edgecolor="black", linewidth=0.4)
    # axs[2].set_ylabel('Occurrences')
    axs[2].set_title('c) Conductance', fontsize=22)
    axs[2].margins(x=0.01)
    axs[2].tick_params(labelsize='x-large', width=2)
    fig.tight_layout()
    plt.savefig(filename)
