""" scRNA_utils.py

Common utility functions to help with analyzing scRNA datasets
Contributors: Lucas Greybuck, James Harvey
"""

import anndata
import pandas as pd
import scipy.sparse as scs


def read_obs(h5con):
    """ 
    Creates a data.frame of observation metadata 

    Parameters: 
        h5con (h5py.File): opened file instance 
    Returns: 
        data.frame of observation metadata  
    Example: 
        h5_con = h5py.File(h5_file, mode = 'r')
        obs = hp.read_obs(h5_con)

    """
    bc = h5con['matrix']['barcodes'][:]
    bc = [x.decode('UTF-8') for x in bc]

    # Initialized the DataFrame with cell barcodes
    obs_df = pd.DataFrame({'barcodes': bc})

    # Get the list of available metadata columns
    obs_columns = h5con['matrix']['observations'].keys()

    # For each column
    for col in obs_columns:
        # Read the values
        values = h5con['matrix']['observations'][col][:]
        # Check for byte storage
        if isinstance(values[0], (bytes, bytearray)):
            # Decode byte strings
            values = [x.decode('UTF-8') for x in values]
        # Add column to the DataFrame
        obs_df[col] = values

    return obs_df


def read_mat(h5_con):
    """
    Creates a Gene x Cell count matrix as a SciPy sparse matrix

    Parameters:
        h5_con (h5py.File): opened file instance 
    Returns: 
        Gene x Cell sparse matrix 
    Example: 
        h5_con = h5py.File(h5_file, mode = 'r')
        mat = hp.read_mat(h5_con)
    """
    mat = scs.csc_matrix(
        (
            h5_con['matrix']['data'][:],  # Count values
            h5_con['matrix']['indices'][:],  # Row indices
            h5_con['matrix']['indptr'][:]),  # Pointers for column positions
        shape=tuple(h5_con['matrix']['shape'][:])  # Matrix dimensions
    )
    return mat


def read_genes(h5_con):
    """ 
    Grabs gene symbols from a H5 
    
    Parameters: 
        h5_con (h5py.File): opened file instance 
    Returns: 
        list of gene symbols 
    Example: 
        h5_con = h5py.File(h5_file, mode='r')
        hp.read_genes(h5_con) 
    """
    genes = h5_con['matrix']['features']['name'][:]
    genes = [x.decode('UTF-8') for x in genes]
    return genes


def create_AnnData(h5_con, add_genes=True):
    """ 
    Creates an AnnData Object for single-cell analysis 
    
    Parameters: 
        h5_con (h5py.File): opened file instance 
        agg_genes (bool): whether or not to add genes as a variable 
    Returns: 
        AnnData object (see scanpy)
    Example:
        h5_con = h5py.File(h5_file, mode = 'r')
        hp.create_AnnData(h5_con)
    """
    matrix = read_mat(h5_con)
    observations = read_obs(h5_con)
    adata = anndata.AnnData(matrix.T, obs=observations)

    if add_genes:
        genes = read_genes(h5_con)
        adata.var_names = genes
        adata.var_names_make_unique()

    return adata
