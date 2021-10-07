''' formatter.py
Description: 
Methods:
Contributors: James Harvey 
'''

# set globals 


# set libraries 
import pandas as pd 


def _desc_lab_to_df(this_desc): 
    '''
    Takes a file descriptor and reshapes lab results into a data.frame 

        Parameters: 
            this_desc : dict 
                dictionary that contains labResults 

        Returns: 
            lab_df : data.frame of labResults 
    '''
    for labr in this_desc['lab']['labResults'].keys(): 
        this_desc['lab']['labResults'][labr] = [this_desc['lab']['labResults'][labr]]
    lab_df = pd.DataFrame(this_desc['lab']['labResults'].copy())

    tmp_dict = {}
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
    else: 
        # sometimes there is no change history 
        revision_dict = {'dataHistory':[]}  


    lab_df = pd.concat([pd.DataFrame.from_dict(tmp_dict), 
                        lab_df,
                        pd.DataFrame.from_dict(revision_dict.pop('dataHistory'))],
                        axis=1)
    return(lab_df) 


def descriptors_to_df_worker(hise_file): 
    '''
    Takes a hise_file and reformats attached descriptors into a data.frame 

        Parameters:
            hise_file : hise_file (see reader.py)

        Returns:
            dict_df : dictionary with keys where values are data.frames 
    '''

    # grab all keys from descriptor object 
    descriptor_keys = hise_file[0].descriptors.keys() 
    this_desc = hise_file[0].descriptors.copy()  
    df_desc = pd.DataFrame() 

    # go through each object and convert into a data.frame 
    # lab results has some extra layers to the dictionary, so we'll do that separately    
    for dk in descriptor_keys: 
        if (dk in ['lab','lastUpdated','emr']) | (this_desc[dk] == None): 
            continue 

        # go through each key-value pair, and convert the value into a list 
        id_dict = {} 
        for field in this_desc[dk].keys(): 
            # id is a redundant fieldname, so make it unique 
            if field == 'id':  
                id_dict['{}.{}'.format(dk, field)] = [this_desc[dk][field]]
            else: 
                this_desc[dk]['{}'.format(field)] = [this_desc[dk][field]]

        # add in the dk.id field, and drop 'id' column 
        if len(id_dict) > 0: 
            this_desc[dk]['{}.id'.format(dk)] = id_dict['{}.id'.format(dk)] 
            this_desc[dk].pop('id')
        df_desc = pd.concat([df_desc.reset_index(drop=True), 
                            pd.DataFrame.from_dict(this_desc[dk])], axis=1)

    # handle lastUpdated - create df then rename column 
    this_desc['lastUpdated'] = [this_desc['lastUpdated']]
    updated_df = pd.DataFrame.from_dict(this_desc['lastUpdated']).rename(columns={0:'lastUpdated'})
    df_desc = pd.concat([df_desc, updated_df], axis=1)
 

    # now take care of lab results
    lab_df = _desc_lab_to_df(this_desc)

    # do some final cleaning and return a dictionary of data.frames 
    dict_df = {'descriptors': df_desc, 
                'labResults' : lab_df}
    return(dict_df)


def descriptors_to_df(list_of_hise_files): 
    ''' 
    Given a list of hise_file objects, return a dictionary containing a data.frame of descriptors, and a data.frame of lab results 

        Parameters:
            list_of_hise_file : list 
                a list of hise_file objects  

        Returns: 
            final_dict : dictionary with keys {'descriptors',labResults'} that both contain appended data.frames 
    '''

    list_dict = []
    for i in range(0,len(list_of_hise_files)): 
        tmp_df = descriptors_to_df_worker([list_of_hise_files[i]])
        list_dict += [tmp_df]
    
    # go through all results from read_files() output, and create a master dictionary 
    # then parse through and append appropriately 
    desc_df = pd.DataFrame() 
    lab_df = pd.DataFrame()
    for i in range(0, len(list_dict)): 
        desc_df = desc_df.append(list_dict[i]['descriptors'])
        lab_df = lab_df.append(list_dict[i]['labResults'])
    final_dict = {'descriptors':desc_df, 
                  'labResults':lab_df}
    return(final_dict) 

