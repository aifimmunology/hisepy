""" formatter.py

Description:

Contributors: James Harvey
"""

# libraries
import os

import h5py
import pandas as pd
import json

import common_utils as cu
from util import load_config

# setting global config
_here = os.path.abspath(os.path.dirname(__file__))
CONFIG = load_config()


def convert_data_values(filepath: str, filetype: str):
    try:
        if filetype == 'csv':
            return pd.read_csv(filepath)
        elif filetype == 'h5':
            return h5py.File(filepath, mode='r')
        else:
            return None
    except BaseException:
        raise Exception(
            "Uh-oh, the file wasn't downloaded into the /cache directory")


# there's another layer/dict under emr.patientData. is leaving a dict under this column okay?
# Do we want to expand this and create a df? maybe have a parameter asking what users want?
def subject_to_df_worker(subject_out):
    """
    Takes output from readSubjects, and reformats to a data.frame
        Parameters:
            subject_out: list
                list of dictionaries containing data from subject materialized view
        Returns:
            final_df : data.frame
                data.frame containing data from subject materialized view
    """
    dict_keys = subject_out.keys()
    meta_df = pd.DataFrame()
    single_df = pd.DataFrame()
    for dk in dict_keys:
        this_entry = subject_out[dk]


if isinstance(this_entry,         if )            this_entry.update(
                (k, [v]) for k, v in
                this_entry.items())  # convert values to lists inplace
            metadata_df_tmp = pd.DataFrame.from_dict(this_entry)
            metadata_df_tmp = metadata_df_tmp.add_prefix('{}.'.format(dk))
            meta_df = pd.concat([meta_df, metadata_df_tmp], axis=1)
elif isinstance(this_entry,         elif )            single_tmp = pd.DataFrame([this_entry], columns=[dk])
            single_df = pd.concat([single_df, single_tmp], axis=1)
        else:
            raise ValueError(
                "There's an unexpected entry for collection... {}. please contact dev support!"
                .format(dk))
    final_df = pd.concat([single_df, meta_df], axis=1)
    return final_df


def subject_to_df(list_subject_out):
    subject_df = subject_to_df_worker(list_subject_out[0])
    if len(list_subject_out) > 1:
        for i in range(1, len(list_subject_out)):
            tmp_df = subject_to_df_worker(list_subject_out[i])
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


def sample_to_df_worker(sample_out):
    """
    Reformats JSON output from read_samples() to a data.frame object

    Parameters:
        sample_out (dict): response object from read_samples()
    Returns:
        a dictionary of 4 data.frame objects with the following keys: ['metadata','labResults', 'specimens','survey']
    """

    # initialize all data.frame objects in case there is nothing to reformat
    metadata_df = pd.DataFrame(data=[''])
    specimen_df = pd.DataFrame(data=[''])
    surv_df = pd.DataFrame(data=[''])
    lab_df = pd.DataFrame(data=[''])
    for dv in sample_out.keys():
        if dv == 'specimens':
            specimen_df = pd.read_json(json.dumps(sample_out[dv]))
        elif dv == 'survey':
            surv_df = pd.read_json(json.dumps(sample_out[dv]))
            if len(surv_df) == 0:
                continue
            # expand answers column where possible
            answers_df = pd.DataFrame()
            for i in list(range(0, len(surv_df))):
                these_answers = pd.DataFrame([surv_df['answers'][i]])

                # assign id for later merge
                these_answers['id'] = surv_df.loc[i, 'id']

                # concat answers together
                answers_df = pd.concat([answers_df, these_answers])

            # rename columns by adding prefix "answers"
            answers_df = answers_df.add_prefix('answers.').reset_index(
                drop=True)
            surv_df = surv_df.merge(answers_df,
                                    left_on='id',
                                    right_on='answers.id')

            # clean up
            surv_df.drop(columns=['answers', 'answers.id'], inplace=True)
        elif dv == 'lab':
            lab_df = pd.DataFrame([sample_out[dv]])
            # expand on lab results
            lab_results = pd.DataFrame([lab_df['labResults'][0]])
            lab_df = pd.concat([lab_df, lab_results], axis=1)

            lab_df.drop(columns='labResults', inplace=True)

        # everything else goes under metadata
        else:
            this_entry = sample_out[dv]

if isinstance(this_entry,             if )                metadata_df[dv] = this_entry
            # only want to do this for samples/subject
elif isinstance(this_entry,             elif )                if dv in ['sample', 'subject']:
                    tmp_df = pd.DataFrame([sample_out[dv]
                                           ]).add_prefix('{}.'.format(dv))
                    metadata_df = pd.concat([metadata_df, tmp_df], axis=1)
                else:
                    metadata_df[dv] = [sample_out[dv]]

    # add idenftifier columns to each data.frame object (subjectGuid & sampleKitGuid)
    this_subject_id = metadata_df.loc[:, 'subject.subjectGuid'].item()
    this_samplekit_id = metadata_df.loc[:, 'sample.sampleKitGuid'].item()
    this_project_id = metadata_df.loc[:, 'projectGuid'].item()
    for this_obj in [lab_df, surv_df, specimen_df]:
        this_obj['subjectGuid'] = str(this_subject_id)
        this_obj['sampleKitGuid'] = str(this_samplekit_id)
        this_obj['projectGuid'] = str(this_project_id)

    dict_df = {
        'metadata': metadata_df,
        'specimens': specimen_df,
        'survey': surv_df,
        'labResults': lab_df
    }

    return dict_df


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
    if len(list_of_sample_obj) == 0:
        return {}

    sample_df_dict = sample_to_df_worker(list_of_sample_obj[0])
    if len(list_of_sample_obj) > 1:
        # loop and append
        for i in range(1, len(list_of_sample_obj)):
            tmp_df_dict = sample_to_df_worker(list_of_sample_obj[i])
            sample_df_dict['metadata'] = pd.concat(
                [sample_df_dict['metadata'], tmp_df_dict['metadata']],
                ignore_index=True)
            sample_df_dict['specimens'] = pd.concat(
                [sample_df_dict['specimens'], tmp_df_dict['specimens']],
                ignore_index=True)
            sample_df_dict['survey'] = pd.concat(
                [sample_df_dict['survey'], tmp_df_dict['survey']],
                ignore_index=True)
            sample_df_dict['labResults'] = pd.concat(
                [sample_df_dict['labResults'], tmp_df_dict['labResults']],
                ignore_index=True)
    return sample_df_dict


def _desc_lab_to_df(this_desc):
    """
    Takes a file descriptor and reshapes lab results into a data.frame

        Parameters:
            this_desc : dict
                dictionary that contains labResults

        Returns:
            lab_df : data.frame of labResults
    """

    lab_df = pd.DataFrame()

    # copy results, and convert entries to list
    if this_desc['labResults'] is None:
        labr = pd.DataFrame()
    else:
        labr = this_desc['labResults'].copy()
        labr.update((k, [v]) for k, v in labr.items())

    # handle revision history
    if (this_desc['revisionHistory'] is None) or (this_desc['revisionHistory']
                                                  == list()):
        revision_df = pd.DataFrame()
    else:
        revh = this_desc['revisionHistory'][0]
        revision_df = pd.DataFrame()
        if revh is not None:
            datah = revh['dataHistory'].copy()
            datah.update((k, [v]) for k, v in datah.items())
            datah_df = pd.DataFrame(datah)
            revh.pop('dataHistory')
            revh.update((k, [v]) for k, v in revh.items())
            revision_df = pd.concat([datah_df, pd.DataFrame(revh)], axis=1)

    # remove labResult from this entry and convert the rest into a data.frame
    this_desc.pop('labResults')
    this_desc.update((k, [v]) for k, v in this_desc.items())

    lab_df = pd.concat(
        [pd.DataFrame(labr),
         pd.DataFrame(this_desc), revision_df], axis=1)
    # de-dupe
    return lab_df.loc[:, ~lab_df.columns.duplicated()]


def _desc_specimen_to_df(this_desc, sample_kit_guid):
    spec_df = pd.DataFrame()
    for i in range(0, len(this_desc)):
        this_desc[i].update((k, [v]) for k, v in this_desc[i].items())
        specimen_tmp = pd.DataFrame.from_dict(this_desc[i])
        spec_df = pd.concat([spec_df, specimen_tmp], axis=0)
    spec_df['sampleKitGuid'] = sample_kit_guid
    return spec_df


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
        'specimens': pd.DataFrame()
    }
    this_df_desc = pd.DataFrame()
    for dk in this_desc.keys():
        if (dk in [
                'specimens', 'lab', 'emr', 'lastUpdated', 'labLastModified',
                'surveyLastModified', 'survey'
        ]) | (this_desc[dk] is None) | (this_desc[dk] == []):
            continue
        # convert dictionary to dataframe
        copy_tmp = this_desc[dk].copy()
        copy_tmp.update((k, [v]) for k, v in copy_tmp.items())
        tmp_df = pd.DataFrame(copy_tmp)

        # rename columns by adding a prefix (i.e lab.<col>, file.<col>, etc)
        tmp_df_cols = tmp_df.columns.tolist()
        new_cols = ['{}.{}'.format(dk, i) for i in tmp_df_cols]
        tmp_df.columns = new_cols

        this_df_desc = pd.concat([this_df_desc, tmp_df], axis=1)

    # handle lastUpdated, labLastModified, and surveyLastModified - create df then rename column
    update_df = pd.DataFrame()
    for update_col in ['lastUpdated', 'labLastModified', 'surveyLastModified']:
        this_desc[update_col] = [this_desc[update_col]]
        update_df = pd.DataFrame.from_dict(
            this_desc[update_col]).rename(columns={0: update_col})
        this_df_desc = pd.concat([this_df_desc, update_df],
                                 axis=1)  # column bind

    # now take care of lab results
    lab_df = _desc_lab_to_df(this_desc['lab'].copy())

    # and now handle specimens
    spec_df = _desc_specimen_to_df(this_desc['specimens'],
                                   this_desc['sample']['sampleKitGuid'])

    # do some final cleaning and return a dictionary of data.frames
    dict_df['descriptors'] = this_df_desc
    dict_df['labResults'] = lab_df
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
    filetype = list_of_hise_files[0].filetype
    list_dict = []
    values_df = pd.DataFrame()
    values_list = []
    for i in range(0, len(list_of_hise_files)):
        this_desc = list_of_hise_files[i].descriptors
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
            list_of_hise_files[i].data_values['filename'] = list_of_hise_files[
                i].descriptors['file']['name']
            values_df = pd.concat(
                [values_df, list_of_hise_files[i].data_values],
                ignore_index=True)
        elif filetype == 'h5':
            values_list.append(list_of_hise_files[i].data_values)

    # go through all results from read_files() output, and create a master dictionary
    # then parse through and append appropriately
    desc_df = pd.DataFrame()
    lab_df = pd.DataFrame()
    spec_df = pd.DataFrame()
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
        'values': data_values
    }
    return final_dict
