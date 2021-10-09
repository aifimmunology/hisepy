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
    df = pd.DataFrame()
    o_df = pd.DataFrame()
    ddf = pd.DataFrame() 
    for dv in dict_keys: 
        this_entry = sample_out[dv]
        if (type(this_entry) == list): 
            for i in range(0,len(this_entry)): 
                this_entry[i].update((k, [v]) for k,v in this_entry[i].items())                
                tmp2 = pd.DataFrame.from_dict(this_entry[i])
                ddf = pd.concat([ddf, tmp2], axis=0)
        elif (type(this_entry) == str):
            tmp_df = pd.DataFrame([this_entry], columns=[dv])
            df = pd.concat([df,tmp_df], axis=1)
        elif (type(this_entry) == dict):
            this_entry.update((k, [v]) for k,v in this_entry.items()) # convert values to lists inplace
            df2 = pd.DataFrame.from_dict(this_entry)
            df2 = df2.add_prefix('{}.'.format(dv))
            o_df = pd.concat([o_df, df2], axis=1)

    # combine everything together         
    dict_df = {'metadata':pd.concat([o_df,df], axis=1), 
                'specimens': ddf}


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