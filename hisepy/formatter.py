''' formatter.py 

Description:

Contributors: James Harvey
'''

# libraries 
import pandas as pd 

def sample_to_df_worker(sample_out):
    '''
    Takes output from readSamples, and outputs to a data.frame 
        Parameters: 
            sample_out: dictionary
                dictionary that contains sample metadata 
        Returns: 
            dict_df : dictionary of 2 data.frame objects 
    '''
    dict_keys = sample_out.keys() 

    # if value is string vs. dict 
    single_df = pd.DataFrame()
    meta_df = pd.DataFrame()
    spec_df = pd.DataFrame() 
    for dv in dict_keys: 
        this_entry = sample_out[dv]
        if (type(this_entry) == list): 
            for i in range(0,len(this_entry)): 
                this_entry[i].update((k, [v]) for k,v in this_entry[i].items())                
                specimen_tmp = pd.DataFrame.from_dict(this_entry[i])
                spec_df = pd.concat([spec_df, specimen_tmp], axis=0)
        elif (type(this_entry) == str):
            single_tmp = pd.DataFrame([this_entry], columns=[dv])
            single_df = pd.concat([single_df,single_tmp], axis=1)
        elif (type(this_entry) == dict):
            this_entry.update((k, [v]) for k,v in this_entry.items()) # convert values to lists inplace
            metadata_df_tmp = pd.DataFrame.from_dict(this_entry)
            metadata_df_tmp = metadata_df_tmp.add_prefix('{}.'.format(dv))
            meta_df = pd.concat([meta_df, metadata_df_tmp], axis=1)

    # combine everything together         
    dict_df = {'metadata':pd.concat([single_df,meta_df], axis=1), 
                'specimens': spec_df}


    return dict_df  



def sample_to_df(list_of_sample_obj): 
    '''
    Given a list of outputs from readSamples(), returns the same data but in a dictionary of data.frames format

        Parameters: 
            list_of_sample_onj : list 
                list of dictionaries for each sampleID
        Returns: 
            sample_df_dict : dictionary 
                dictionary with keys ['metadata','specimens'] where each key is mapped to a data.frame 

    '''
    sample_df_dict = sample_to_df_worker(list_of_sample_obj[0])
    if len(list_of_sample_obj) > 1: 
        # loop and append 
        for i in range(1, len(list_of_sample_obj)): 
            tmp_df_dict = sample_to_df_worker(list_of_sample_obj[i])
            sample_df_dict['metadata'] = sample_df_dict['metadata'].append(tmp_df_dict['metadata'])
            sample_df_dict['specimens'] = sample_df_dict['specimens'].append(tmp_df_dict['specimens'])
    return(sample_df_dict) 