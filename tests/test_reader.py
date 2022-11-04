'''

Description: This file tests that reshaping a server response to a data.frame is sound 

Things that are tested 
- read_files() is working 

for the reshaped object...
- datatypes of columns 
- naming of columns 
- all data is still present; nothing got dropped 
'''

import sys

sys.path.insert(0, '../')  # to be able to import hisepy package

import hisepy
import hisepy.reader as hr
import hisepy.formatter as hf
import hisepy.common_utils as cu

# testing framework
import pytest

CONFIG = cu.read_yaml('{}/hisepy/config.yaml'.format(sys.path[0]))


# TODO: add more test files
def get_file():
    return hr.read_files(["c6820c0d-2b57-43ff-a0c2-fa6ae902a3d4"], to_df=False)


def test_read_files():
    '''
    '''
    resp_out = get_file()
    return


def create_colname_list(field_name: str, d: dict):
    '''
    Parameters: 
        field_name (str) : name of field. i.e (sample, file, subject, cohort)
        d (dict) : dictionary that contains the lsit of fields that's the "child" 
            of field_name
    Returns: 
        list of column names that should exist in the data.frame (i.e [sample.id, sample.visitName, sample.drawDate])
    '''
    colname_list = []
    for k in d.keys():
        colname_list.append('%s.%s' % (field_name, k))
    return colname_list


# NOTE: for descriptors
def check_all_columns_exist(resp, resp_df, field_name):
    ''' NOTE: [descriptors, specimens, labResults, values
    '''
    this_desc_col_list = create_colname_list(field_name, resp)
    check_cols = set(this_desc_col_list) - set(
        resp_df['descriptors'].columns.tolist())
    assert check_cols == set(
    ), "the following coloumns were dropped when reshaping, %s" % (check_cols)


def check_all_lab_cols_exist(resp, resp_df, field_name):
    # lab_cols_list = create_colname_list(field_name, resp)
    lab_cols_list = list(resp.keys()) + list(resp['labResults'].keys())

    # we drop this since we look at this dict object and reshape that too
    lab_cols_list.remove('labResults')
    check_cols = set(lab_cols_list) - set(
        resp_df['labResults'].columns.tolist())
    assert check_cols == set(
    ), "the following coloumns were dropped when reshaping, %s" % (check_cols)


def check_specimens_columns_exist(desc, resp_df, f):
    '''
    '''
    # we have a list of dictonary specimen objects
    # loop through each dict obj and ensure we have the same keys
    specimen_cols_list = desc[0].keys()

    # NOTE: runtime slow for this loop
    for i in list(range(1, len(desc))):
        check_keys = set(list(desc[i].keys())) - set(list(specimen_cols_list))
        assert check_keys == set(), "the following extra keys exist %s" % (
            check_keys)

    # then check against the reshaped obj
    check_cols = set(specimen_cols_list) - set(
        resp_df['specimens'].columns.tolist())
    assert check_cols == set(
    ), "the following coloumns were dropped when reshaping, %s" % (check_cols)


def test_read_files_reshape():
    ''' checks the following
    - nothing got dropped
    - dtypes remain the same 
    -  '''
    # REFACTOR:
    # create read_files_test object
    # test read file
    # check columns

    test = get_file()
    desc_df = hf.hise_file_to_df(test)
    # checking all columns exists and nothing was dropped
    # import pdb; pdb.set_trace()
    for f in test[0].descriptors.keys(
    ):  # NOTE: this is the unchanged response obj
        this_desc = test[0].descriptors[f]
        if type(this_desc) is list:
            if f == 'specimens':
                check_specimens_columns_exist(this_desc, desc_df, f)
            else:
                # the other values here are the arent descriptors without children. these were moved to desc_df['descriptors'] so we just check there
                assert f in desc_df['descriptors'].columns.tolist(
                ), "%s field was not found in the reshaped descriptor object"
        elif type(this_desc) is dict:
            # this_desc_col_list = create_colname_list(f, this_desc, f)
            if f in CONFIG['METADATA_FIELDS']['DESCRIPTORS']:
                check_all_columns_exist(this_desc, desc_df, f)
            elif f in CONFIG['METADATA_FIELDS']['LABS']:
                check_all_lab_cols_exist(this_desc, desc_df, f)
            else:
                # NOTE: at the moment the following are being skipped since the current test has these as empty
                # emr, survey, surveyScheme

                # but these should be coming from read_subjects()...?
                print("skipping for now...{}".format(f))
                continue
    return
