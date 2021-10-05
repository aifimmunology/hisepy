''' formatter.py
Description: 
Methods:
Contributors: James Harvey 
'''

# set globals 


# set libraries 
import pandas as pd 


def descriptors_to_df(hise_file): 
    '''
    Takes a hise_file and reformats attached descriptors into a data.frame 

        Parameters:

        Returns: 
    '''

    # grab all keys from descriptor object 
    descriptor_keys = hise_file[0].descriptors.keys() # NOTE: what about if we read multiple files? 
    this_desc = hise_file[0].descriptors 
    df_desc = pd.DataFrame() 

    # go through each object and convert into a data.frame 
    # lab results has some extra layers to the dictionary, so we'll do that separately    
    for dk in descriptor_keys: 
        if (dk in ['lab','lastUpdated','emr']) | (this_desc[dk] == None): 
            continue 

        # go through each key-value pair, and convert the value into a list 
        # TODO: handle duplicate ids - maybe just add a prefix to these column names 
        for field in this_desc[dk].keys():  
            this_desc[dk][field] = [this_desc[dk][field]]
        df_desc = pd.concat([df_desc.reset_index(drop=True), 
                            pd.DataFrame.from_dict(this_desc[dk])], axis=1)

    # handle lastUpdated - create df then rename column 
    this_desc['lastUpdated'] = [this_desc['lastUpdated']]
    updated_df = pd.DataFrame.from_dict(this_desc['lastUpdated']).rename(columns={0:'lastUpdated'})
    df_desc = pd.concat([df_desc, updated_df], axis=1)
 

    # now take care of lab results
    for labr in this_desc['lab']['labResults'].keys(): 
        this_desc['lab']['labResults'][labr] = [this_desc['lab']['labResults'][labr]]
    lab_df = pd.DataFrame(this_desc['lab']['labResults'].copy())

    tmp_dict = {}
    import pdb; pdb.set_trace() 
    if (this_desc['lab']['revisionHistory'] != None): 
        revision_dict = this_desc['lab']['revisionHistory'][0].copy() # NOTE: there's going to be more than 1 revision entry 
        for hist in revision_dict['dataHistory'].keys(): 
            tmp_dict['{}_oldValue'.format(hist)] = [revision_dict['dataHistory'][hist]['oldValue']]
            tmp_dict['{}_newValue'.format(hist)] = [revision_dict['dataHistory'][hist]['newValue']]

        for labf in revision_dict.keys(): 
            if labf == 'dataHistory': 
                continue
            else: 
                revision_dict[labf] = [revision_dict[labf]]
    else : 
        revision_dict = {'dataHistory':[]}  


    lab_df = pd.concat([pd.DataFrame.from_dict(tmp_dict), 
                        lab_df,
                        pd.DataFrame.from_dict(revision_dict.pop('dataHistory'))],
                        axis=1)

    # do some final cleaning and return a dictionary of data.frames 
    dict_df = {'descriptors': df_desc, 
                'labResults' : lab_df}
    return(dict_df)


