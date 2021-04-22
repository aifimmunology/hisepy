import nptsne
import pyreadr
import pandas
import numpy
import networkx
import community as community_louvain
from hisepy.scheduler import schedule_notebook

hsne_clustering_output = "clustering.rds"
hsne_embedding_output = "embedding.rds"

def schedule_hsne_notebook(data, num_scales = 5, graph_scale_index = 4, project = None):
    if type(data) is pandas.core.frame.DataFrame:
        data = data.to_numpy()
    elif type(data) is not numpy.ndarray:
        raise(TypeError("%s is not a recognized datatype for HSNE dimension reduction. Must be dataframe or numpy ndarray" % (type(data))))
    
    if graph_scale_index > num_scales - 1:
        raise(Exception("cannot ask for a graph_scale_index greater than the number of scales - 1 (values were %d scales and index of %d)" % (num_scales, graph_scale_index)))
    
    schedule_notebook([hsne_clustering_output, hsne_embedding_output],
                      args = {"project": project},                      
                      function = run_hsne,                      
                      function_args = {"data": data,
                                       "num_scales": num_scales,
                                       "graph_scale_index": graph_scale_index})
                      

def run_hsne(args):
    print("Running HSNE")
    hsne = nptsne.HSne(True)
    hsne.create_hsne(args["data"], args["num_scales"])
    print("HSNE Completed")
    hsne_scale = hsne.get_scale(args["graph_scale_index"])
    hsne_graph = make_graph_from_transition_matrix(hsne_scale.transition_matrix)   
    print("Running Louvain Partitioning")
    clusters = community_louvain.best_partition(hsne_graph, resolution = 1)
    print("Partitioning Done - Saving clusters data frame as %s" % (clustering_output))
    cluster_df = pandas.DataFrame(list(clusters.items()),
                              columns = ['orig_cell','cluster_id'])
    cluster_df = cluster_df.sort_values('orig_cell')
    cluster_df = cluster_df.reset_index()
    cluster_df['cell_idx'] = list(hsne_scale.landmark_orig_indexes)
    pyreadr.write_rds(clustering_output, cluster_df)
    print("Running embedding")
    model = nptsne.hsne_analysis.Analysis(hsne, nptsne.hsne_analysis.EmbedderType.CPU)
    for i in range(2000):
        model.do_iteration()
    nptsne_embedding = model.embedding
    print("Embedding done -- Saving embedding data frame as %s" % (embedding_output))
    nptsne_df = pandas.DataFrame({'x' : [val[0] for val in nptsne_embedding],
                                  'y' : [val[1] for val in nptsne_embedding]})
    nptsne_df['cell_idx'] = hsne_scale.landmark_orig_indexes
    nptsne_df = nptsne_df.sort_values('cell_idx')
    nptsne_df = nptsne_df.reset_index()
    nptsne_df['cluster_id'] = cluster_df['cluster_id'].astype('category')
    pyreadr.write_rds(embedding_output, nptsne_df)
    print("Done")

def make_graph_from_transition_matrix(tmat):    
    row = []
    col = []
    data = []

    for r_ind, rcol in enumerate(tmat):
        for tup in rcol:
            if not isinstance(tup, tuple):
                continueexit()
            row.append(r_ind)
            col.append(tup[0])
            data.append(tup[1])
    
    g = networkx.Graph()
    g.add_weighted_edges_from(list(zip(row, col, data)))
    return g
