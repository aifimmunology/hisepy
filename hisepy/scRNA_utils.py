''' scRNA_utils.py 

Common utility functions to help with analyzing scRNA datasets 
Contributors: Lucas Greybuck, James Harvey 
'''

# libraries 
import pandas as pd 
import scipy.sparse as scs # TODO: what do I do with libraries not already installed? 
import anndata


def read_obs(h5con):
    bc = h5con['matrix']['barcodes'][:]
    bc = [x.decode('UTF-8') for x in bc]

    # Initialized the DataFrame with cell barcodes
    obs_df = pd.DataFrame({ 'barcodes' : bc })

    # Get the list of available metadata columns
    obs_columns = h5con['matrix']['observations'].keys()

    # For each column
    for col in obs_columns:
        # Read the values
        values = h5con['matrix']['observations'][col][:]
        # Check for byte storage
        if(isinstance(values[0], (bytes, bytearray))):
            # Decode byte strings
            values = [x.decode('UTF-8') for x in values]
        # Add column to the DataFrame
        obs_df[col] = values
    
    return obs_df


def read_mat(h5_con):
    mat = scs.csc_matrix(
        (h5_con['matrix']['data'][:], # Count values
         h5_con['matrix']['indices'][:], # Row indices
         h5_con['matrix']['indptr'][:]), # Pointers for column positions
        shape = tuple(h5_con['matrix']['shape'][:]) # Matrix dimensions
    )
    return mat


def read_genes(h5_con): 
    genes = h5_con['matrix']['features']['name'][:]
    genes = [x.decode('UTF-8') for x in genes]
    return genes


def create_AnnData(h5_con, add_genes=True): 
    '''
    '''
    matrix = read_mat(h5_con)
    observations = read_obs(h5_con)
    adata = anndata.AnnData(matrix.T,
                            obs = observations)

    
    if add_genes: 
        genes = read_genes(h5_con)
        adata.var_names = genes
        adata.var_names_make_unique()

    return adata
