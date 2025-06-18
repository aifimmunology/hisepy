""" formatter.py

Description:

Contributors: James Harvey
"""

# libraries
import os

import h5py
import pandas as pd
import json

import hisepy.common_utils as cu

# setting global config
_here = os.path.abspath(os.path.dirname(__file__))
CONFIG = cu.read_yaml('{}/config.yaml'.format(_here))


def attach_project_info_to_df(df): 
    """ Adds project information to a data.frame object. data.frame object must have projectGuid column
    """
    # get projects 
    proj_df = cu.get_projects() 

    # add 'project' prefix to project columns 
    proj_df = proj_df.add_prefix('project.')

    # merge project info to data.frame
    return  pd.merge(df, proj_df, how='left', left_on='projectGuid', right_on='project.guid')


def convert_data_values(filepath: str, filetype: str):
    try:
        if filetype == 'csv':
            return pd.read_csv(filepath)
        elif filetype == 'h5':
            return h5py.File(filepath, mode='r')
        else:
            return None
    except:
        raise Exception(
            "Uh-oh, the file wasn't downloaded into the /cache directory")


def convert_single_val_to_df(df, single_val, col_name):
    """ Converts a single value to a data.frame object
    """
    assert (type(single_val) is str) or (type(single_val) is int) or (type(single_val) is bool), "Expected a single value to be of type str, int, or bool. Received type %s" % type(single_val)
    single_df_tmp = pd.DataFrame([single_val], columns=[col_name])
    df = pd.concat([df, single_df_tmp], axis=1)
    return df


def convert_dict_to_df(df, dict_val, col_name, add_prefix=True):
    """ Converts a dictionary to a data.frame object
    """
    assert type(dict_val) is dict, "Expected a dictionary to be of type dict. Received type %s" % type(dict_val)
    dict_val.update((k, [v]) for k, v in dict_val.items() if type(dict_val[k]) is not list)
    dict_val.update((k, v.append('')) for k, v in dict_val.items() if type(v) is list and len(v) == 0)
    dict_df_tmp = pd.DataFrame.from_dict(dict_val)
    if add_prefix:
        dict_df_tmp = dict_df_tmp.add_prefix('{}.'.format(col_name))
    else: 
        pass
    df = pd.concat([df, dict_df_tmp], axis=1)
    return df

def convert_list_to_df(df, list_val, col_name):
     # if there's just 1 entry, convert it to a data.frame  
    if len(list_val) == 1 and type(list_val[0]) is not dict:
        df = convert_single_val_to_df(df, list_val[0], col_name)
    elif len(list_val) > 1:
        df = convert_single_val_to_df(df, str(list_val), col_name)
    else: 
        # we have a dictionary with possibly multiple entries
        for this_dict in list_val: 
            df = convert_dict_to_df(df, this_dict, col_name)
    return df
    

def reshape_custom_metadata(custom_metadata, add_prefix=True):
    """ Takes a json payload and reshapes to a data.frame object
    """
    dict_keys = custom_metadata.keys()
    meta_df = pd.DataFrame()
    single_df = pd.DataFrame()
    for dk in dict_keys:
        this_entry = custom_metadata[dk]
        # skip if a field is null 
        if this_entry is None: 
            single_df = convert_single_val_to_df(single_df, "", dk)
        elif type(this_entry) is dict:
            if len(this_entry) == 0:
                single_df = convert_single_val_to_df(single_df, "", dk)
            else:
                meta_df = convert_dict_to_df(meta_df, this_entry, dk, add_prefix)
        elif (type(this_entry) is str) or (type(this_entry) is bool) or (type(this_entry) is int):
            single_df = convert_single_val_to_df(single_df, this_entry, dk)
        elif type(this_entry) is list:
           meta_df = convert_list_to_df(meta_df, this_entry, dk)
        else:
            raise ValueError(
                "There's an unexpected entry for collection... {}. please contact dev support!"
                .format(dk))
    final_df = pd.concat([single_df, meta_df], axis=1)
    return final_df


def subject_to_df(list_subject_out):
    subject_df = reshape_custom_metadata(list_subject_out[0])
    if len(list_subject_out) > 1:
        for i in range(1, len(list_subject_out)):
            tmp_df = reshape_custom_metadata(list_subject_out[i])
            subject_df = pd.concat([subject_df, tmp_df], ignore_index=True)
    return subject_df


def _dict_to_df(input_df, col_name):
    """
    This function takes a column from a data.frame and converts that column to its
    own data.frame object
    NOTE: the column you specify must have entries that are of type dict

        Parameters:
            input_df : pd.dataframe
                pandas dataframe
            col_name : str
                column name that exists in your input_df
        Returns:
            fin_df : pd.dataframe
                pandas data.frame
    """
    # subset to just the column of interest
    this_df = input_df.copy(deep=True)[[col_name]].reset_index(drop=True)
    fin_df = pd.DataFrame()
    for i in range(0, len(this_df)):
        this_dict = this_df[col_name].values[i]
        if this_dict is not None:
            this_dict.update((k, [v]) for k, v in this_dict.items())
            fin_df = pd.concat(
                [fin_df, pd.DataFrame.from_dict(this_dict)], ignore_index=True)
    return fin_df

def reshape_list_metadata_to_df(spec_obj):
    """
    Given a list of specimens, returns a data.frame object

        Parameters:
            spec_obj : list
                list of dictionaries for each specimen

        Returns:
            spec_df : pd.dataframe
                pandas data.frame
    """
    spec_df = pd.DataFrame()
    for i in range(0, len(spec_obj)):
        this_spec_df = reshape_custom_metadata(spec_obj[i])
        spec_df = pd.concat([spec_df, this_spec_df], ignore_index=True)
    return spec_df

def reshape_survey_results_to_df(survey_obj): 
    """
    Given a list of survey results, returns a data.frame object

        Parameters:
            survey_obj : dict
                dictionary fof survey results

        Returns:
            surv_df : pd.dataframe
                pandas data.frame
    """
    # reshape survey answers - take each dict entry and convert to a data.frame
    ans_df = convert_dict_to_df(pd.DataFrame(), survey_obj['answers'], 'answers')
    if survey_obj is not None:
        survey_obj.update((k, [v]) for k, v in survey_obj.items() if type(survey_obj[k]) is not list)
        this_surv_df = convert_dict_to_df(pd.DataFrame(), survey_obj, '', add_prefix=False)
        del this_surv_df['answers']
    surv_df = pd.concat([this_surv_df, ans_df], axis=1) # add answers to survey df
    return surv_df


def sample_to_df(list_of_sample_obj):
    """
    Given a list of outputs from readSamples(), returns the same data but in a dictionary of data.frames format

        Parameters:
            list_of_sample_obj : list
                list of dictionaries for each sampleID
        Returns:
            sample_df_dict : dictionary
                dictionary with keys ['metadata','specimens'] where each key is mapped to a data.frame

    """
    sample_df_dict = {}
    if len(list_of_sample_obj) == 0:
        return pd.DataFrame()
    if 'specimens' in list_of_sample_obj[0].keys():
        spec_df = reshape_list_metadata_to_df(list_of_sample_obj[0]['specimens'])
        list_of_sample_obj[0].pop('specimens') # remove so we don't reshape it again 
    
    surv_df = pd.DataFrame()
    if 'survey' in list_of_sample_obj[0].keys():

        # we have a list of dictionaries, so we need to reshape each dictionary to a data.frame
        for i in range(0, len(list_of_sample_obj[0]['survey'])):
            this_dict = list_of_sample_obj[0]['survey'][i]
            this_surv_df = reshape_survey_results_to_df(this_dict) 
            surv_df = pd.concat([surv_df, this_surv_df], ignore_index=True)
        list_of_sample_obj[0].pop('survey') # remove so we don't reshape it again
    lab_df = pd.DataFrame()
    if 'lab' in list_of_sample_obj[0].keys() and list_of_sample_obj[0]['hasLabResults'] is True:
        lab_df = reshape_custom_metadata(list_of_sample_obj[0]['lab'], False)
        list_of_sample_obj[0].pop('lab') # remove so we don't reshape it again
    sample_df = reshape_custom_metadata(list_of_sample_obj[0])

    if len(list_of_sample_obj) > 1:
        # loop and append
        this_surv_df = pd.DataFrame()
        for i in range(1, len(list_of_sample_obj)):
            # reshape specimens, survey, and labResults first, if they exist 
            if 'specimens' in list_of_sample_obj[i].keys():
                this_spec_df = reshape_list_metadata_to_df(list_of_sample_obj[i]['specimens'])
                list_of_sample_obj[i].pop('specimens') # remove so we don't reshape it again 
                spec_df = pd.concat([spec_df.reset_index(drop=True), this_spec_df.reset_index(drop=True)], ignore_index=True)
            if 'survey' in list_of_sample_obj[i].keys():                
                for j in range(0, len(list_of_sample_obj[i]['survey'])):
                    this_surv_df = reshape_survey_results_to_df(list_of_sample_obj[i]['survey'][j])
                    surv_df = pd.concat([surv_df, this_surv_df], ignore_index=True)
                list_of_sample_obj[i].pop('survey') # remove so we don't reshape it again
            if 'lab' in list_of_sample_obj[i].keys() and list_of_sample_obj[i]['hasLabResults'] is True:
                this_lab_df = reshape_custom_metadata(list_of_sample_obj[i]['lab'], False)
                list_of_sample_obj[i].pop('lab') # remove so we don't reshape it again`
                lab_df = pd.concat([lab_df, this_lab_df])
            # reshape the rest of metadata 
            this_sample_df = reshape_custom_metadata(list_of_sample_obj[i])
            sample_df = pd.concat([sample_df, this_sample_df])
    sample_df_dict['metadata'] = sample_df
    sample_df_dict['specimens'] = spec_df
    sample_df_dict['survey'] = surv_df
    sample_df_dict['labResults'] = lab_df
    return sample_df_dict


def reshape_descriptors(this_desc):
    """ Reshapes descriptors to a dataframe object 
    """
    assert type(
        this_desc
    ) is dict, "expected descriptors to be a dictionary. Received type %s" % type(
        this_desc)
    dict_df = {
        'descriptors': pd.DataFrame(),
        'labResults': pd.DataFrame(),
        'specimens': pd.DataFrame(),
        'survey': pd.DataFrame()
    }
    # check if lab results exist - reformat and remove from dictionary if it does
    lab_df = pd.DataFrame()
    if 'lab' in this_desc.keys():
        lab_df = reshape_custom_metadata(this_desc['lab'], False)
        this_desc.pop('lab') # remove so we don't reshape it again

    # check if specimens exist - reformat and remove from dictionary if it does 
    spec_df = pd.DataFrame() 
    if 'specimens' in this_desc.keys():
        spec_df = reshape_list_metadata_to_df(this_desc['specimens'])
        this_desc.pop('specimens') # remove so we don't reshape it again
    surv_df = pd.DataFrame()
    if 'survey' in this_desc.keys():
        surv_df = reshape_list_metadata_to_df(this_desc['survey'])
        this_desc.pop('survey')
    dict_df['descriptors'] = reshape_custom_metadata(this_desc)
    dict_df['labResults'] = lab_df
    dict_df['survey'] = surv_df
    dict_df['specimens'] = spec_df
    return dict_df
    

def hise_file_to_df(list_of_hise_files):
    """
    Given a list of hise_file objects, return a dictionary containing a data.frame of descriptors, and a data.frame of lab results

        Parameters:
            list_of_hise_files : list
                a list of hise_file objects

        Returns:
            final_dict : dictionary with keys {'descriptors',labResults', 'specimens', 'values'} which are all data.frame objects.
            except for values, which depends on the filetype the user passes in.
    """
    list_dict = []
    values_df = pd.DataFrame()
    values_list = []
    errors_df = pd.DataFrame()
    for i in range(0, len(list_of_hise_files)):
        # deal with any failed downloads
        if list_of_hise_files[i].status is False:
            errors_df = pd.concat([
                errors_df,
                pd.DataFrame(
                    data={
                        'filetype': [list_of_hise_files[0].filetype],
                        'id': [list_of_hise_files[0].id],
                        'message': [list_of_hise_files[0].message]
                    })
            ],
                                  ignore_index=True)
            continue
        this_desc = list_of_hise_files[i].descriptors
        filetype = list_of_hise_files[i].filetype
        if type(this_desc) is list:
            for olink_desc in this_desc:
                tmp_df = reshape_descriptors(olink_desc)
                list_dict += [tmp_df]

        elif type(this_desc) is dict:
            tmp_df = reshape_descriptors(this_desc)
            list_dict += [tmp_df]

        # create an object of data values for a given data type
        if filetype == 'csv':
            # attach file_name
            list_of_hise_files[i].data_values['filename'] = str(list_of_hise_files[
                i].descriptors['file']['name'][0])
            values_df = pd.concat(
                [values_df, list_of_hise_files[i].data_values],
                ignore_index=True)
        elif filetype == 'h5':
            values_list.append(list_of_hise_files[i].data_values)

    # if everything failed, don't create data.frames
    all_files_not_found = all(item.status is False
                              for item in list_of_hise_files)
    desc_df = pd.DataFrame()
    lab_df = pd.DataFrame()
    spec_df = pd.DataFrame()
    if all_files_not_found:
        return {
            'descriptors': desc_df,
            'labResults': lab_df,
            'specimens': spec_df,
            'values': [],
            'errors': errors_df
        }
    else:
        # go through all results from read_files() output, and create a master dictionary
        # then parse through and append appropriately

        for i in range(0, len(list_dict)):
            desc_df = pd.concat([desc_df, list_dict[i]['descriptors']],
                                ignore_index=True)
            lab_df = pd.concat([lab_df, list_dict[i]['labResults']],
                               ignore_index=True)
            spec_df = pd.concat([spec_df, list_dict[i]['specimens']],
                                ignore_index=True)

        if filetype == 'csv':
            data_values = values_df
        elif filetype == 'h5':
            data_values = values_list
        else:  # don't return anything useful under values
            data_values = []
        final_dict = {
            'descriptors': desc_df,
            'labResults': lab_df,
            'specimens': spec_df,
            'values': data_values,
            'errors': errors_df
        }
        return final_dict
