''' formatter.py 

Description:

Contributors: James Harvey
'''

# libraries 
import os 
import hisepy.common_utils as cu
import pandas as pd 

# setting global config 
_here = os.path.abspath(os.path.dirname(__file__))
CONFIG = cu.read_yaml('{}/config.yaml'.format(_here))

# there's another layer/dict under emr.patientData. is leaving a dict under this column okay?
# Do we want to expand this and create a df? maybe have a parameter asking what users want?  
def subject_to_df_worker(subject_out): 
    '''
    Takes output from readSubjects, and reformats to a data.frame
        Parameters: 
            subject_out: list 
                list of dictionaries containing data from subject materialized view
        Returns: 
            final_df : data.frame
                data.frame containing data from subject materialized view          
    '''
    dict_keys = subject_out.keys()
    meta_df = pd.DataFrame()
    single_df = pd.DataFrame()  
    for dk in dict_keys: 
        this_entry = subject_out[dk]
        if (type(this_entry) == dict):
            this_entry.update((k, [v]) for k,v in this_entry.items()) # convert values to lists inplace
            metadata_df_tmp = pd.DataFrame.from_dict(this_entry)
            metadata_df_tmp = metadata_df_tmp.add_prefix('{}.'.format(dk))
            meta_df = pd.concat([meta_df, metadata_df_tmp], axis=1)
        elif (type(this_entry) == str):
            single_tmp = pd.DataFrame([this_entry], columns=[dk])
            single_df = pd.concat([single_df,single_tmp], axis=1)
        else: 
            raise ValueError("There's an unexpected entry for collection... {}. please contact dev support!".format(dk))
    final_df = pd.concat([single_df, meta_df], axis=1)
    return final_df


def subject_to_df(list_subject_out): 
    '''
    '''
    subject_df = subject_to_df_worker(list_subject_out[0])
    if len(list_subject_out) > 1:
        for i in range(1, len(list_subject_out)): 
            tmp_df = subject_to_df_worker(list_subject_out[i])
            subject_df = subject_df.append(tmp_df)
    return subject_df

# TODO: this method really demonstrates how useful a class could be... 
# if the output of read_sample() changes then a lot of troubleshooting is going to be needed... 
def sample_to_df_worker(sample_out):
    '''
    Takes output from readSamples, and outputs to a data.frame 
        Parameters: 
            sample_out: dictionary
                dictionary that contains sample metadata 
        Returns: 
            dict_df : dictionary of 3 data.frame objects ['metadata','specimens','survey']
    '''
    dict_keys = sample_out.keys() 

    # if value is string vs. dict 
    single_df = pd.DataFrame()
    meta_df = pd.DataFrame()
    spec_df = pd.DataFrame() 
    surv_df = pd.DataFrame() 
    no_entry_df = pd.DataFrame()
    for dv in dict_keys:
        this_entry = sample_out[dv]

        # situations where we'll just omit a column
        if (this_entry is None) |(type(this_entry) is bool):
            no_entry = pd.DataFrame(data=[''], columns=[dv])
            no_entry_df = pd.concat([no_entry_df, no_entry], axis=1)
        elif (type(this_entry) is list): 
            if (this_entry[0] == ''): 
                no_entry_list = pd.DataFrame(data=[''], columns=[dv]) 
                no_entry_df = pd.concat([no_entry_df, no_entry_list], axis=1) 
            else: 
                try: 
                    if dv == 'survey': 
                        for i in this_entry[0].keys(): 
                            if type(this_entry[0][i]) == str:
                                tmp_surv_df = pd.DataFrame([this_entry[0][i]], columns=[i])
                                surv_df = pd.concat([surv_df, tmp_surv_df], axis=1)
                            elif type(this_entry[0][i] == dict): 
                                this_entry[0][i].update((k, [v]) for k,v in this_entry[0][i].items())                
                                tmp_surv_df = pd.DataFrame.from_dict(this_entry[0][i])
                                tmp_cols = tmp_surv_df.columns.tolist()
                                new_cols = ['{}.{}'.format(i, j) for j in tmp_cols]
                                tmp_surv_df.columns = new_cols 
                                surv_df = pd.concat([surv_df, tmp_surv_df], axis=1)
                    elif dv == 'specimens':
                        for i in range(0,len(this_entry)): 
                            this_entry[i].update((k, [v]) for k,v in this_entry[i].items())                
                            specimen_tmp = pd.DataFrame.from_dict(this_entry[i])
                            spec_df = pd.concat([spec_df, specimen_tmp], axis=0)
                except: # for entries like batchIdList that aren't always null/emptry 
                    single_df = pd.concat([single_df, pd.DataFrame(this_entry, columns=[dv])], axis=1)
        elif (type(this_entry) == str):
            single_tmp = pd.DataFrame([this_entry], columns=[dv])
            single_df = pd.concat([single_df,single_tmp], axis=1)
        elif (type(this_entry) == dict):
            this_entry.update((k, [v]) for k,v in this_entry.items()) # convert values to lists inplace
            metadata_df_tmp = pd.DataFrame.from_dict(this_entry)
            metadata_df_tmp = metadata_df_tmp.add_prefix('{}.'.format(dv))
            meta_df = pd.concat([meta_df, metadata_df_tmp], axis=1)
        else: 
            raise ValueError("There's an unexpected entry for collection... {}. please contact dev support!".format(dv))

    # combine everything together
    # also ensure all data.frames have an identifier users can merge on  
    dict_df = {'metadata':pd.concat([single_df,meta_df, no_entry_df], axis=1), 
                'specimens': spec_df,
                'survey' : surv_df}
    dict_df['specimens']['subjectGuid'] = dict_df['metadata']['subject.subjectGuid']
    dict_df['specimens']['sampleKitGuid'] = dict_df['metadata']['sample.sampleKitGuid']
    dict_df['survey']['subjectGuid'] = dict_df['metadata']['subject.subjectGuid']
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
            sample_df_dict['survey'] = sample_df_dict['survey'].append(tmp_df_dict['survey'])
    return(sample_df_dict) 



def _desc_lab_to_df(this_desc): 
    '''
    Takes a file descriptor and reshapes lab results into a data.frame 

        Parameters: 
            this_desc : dict 
                dictionary that contains labResults 

        Returns: 
            lab_df : data.frame of labResults 
    '''

    lab_df = pd.DataFrame()

    # copy results, and convert entries to list 
    labr = this_desc['labResults'].copy() 
    labr.update((k, [v]) for k,v in labr.items())
    
    # handle revision history     
    revh = this_desc['revisionHistory']
    revision_df = pd.DataFrame() 
    if (revh != None):  

        datah = revh['dataHistory'].copy()
        for hist in datah.keys(): 
            datah.update((k,[v]) for k,v in datah.items())
        datah_df = pd.DataFrame(datah) 

        revh.pop('dataHistory')
        for labf in revh.keys(): 
            revh.update((k,[v]) for k,v in revh.items())
        revision_df = pd.concat([datah_df, pd.DataFrame(revh)], axis=1)

    # remove labResult from this entry and convert the rest into a data.frame 
    this_desc.pop('labResults')
    this_desc.update((k, [v]) for k,v in this_desc.items())

    lab_df = pd.concat([pd.DataFrame(labr), pd.DataFrame(this_desc), revision_df], axis=1)
    return lab_df


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
    desc_labs = this_desc['lab'].copy() 
    df_desc = pd.DataFrame() 

    # go through each object and convert into a data.frame 
    # lab results has some extra layers to the dictionary, so we'll do that separately    
    for dk in descriptor_keys: 
        if (dk in ['lab','emr','lastUpdated']) | (this_desc[dk] == None): 
            continue 

        # convert dictionary to dataframe 
        copy_tmp = this_desc[dk].copy() 
        copy_tmp.update((k, [v]) for k,v in copy_tmp.items())
        tmp_df = pd.DataFrame(copy_tmp) 

        # rename columns by adding a prefix (i.e lab.<col>, file.<col>, etc)
        tmp_df_cols = tmp_df.columns.tolist()
        new_cols = ['{}.{}'.format(dk, i) for i in tmp_df_cols]
        tmp_df.columns = new_cols 

        df_desc = pd.concat([df_desc, tmp_df], axis=1)

    # handle lastUpdated - create df then rename column 
    this_desc['lastUpdated'] = [this_desc['lastUpdated']]
    updated_df = pd.DataFrame.from_dict(this_desc['lastUpdated']).rename(columns={0:'lastUpdated'})
    df_desc = pd.concat([df_desc, updated_df], axis=1)
 

    # now take care of lab results
    lab_df = _desc_lab_to_df(this_desc['lab'])

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


