'''
'''

import sys

sys.path.insert(0, '../')  # to be able to import hisepy package

import hisepy
import hisepy.reader as hr
import hisepy.formatter as hf
import hisepy.common_utils as cu

# testing framework
import pytest


def get_subjects():
    out = hr.read_subjects(["e2753c71-076a-49ec-b2c2-5e48a7b54aec"],
                           to_df=False)
    return out


def create_colname_list(resp):
    '''
    '''
    colname_list = []
    for k in resp.keys():
        if type(resp[k]) is dict:
            for i in resp[k].keys():
                colname_list.append('%s.%s' % (k, i))
        else:
            colname_list.append(k)
    return colname_list


## tests
def test_read_subjects():
    get_subjects()
    return


def test_subject_reshape():
    ''' compares the response object with the reshaped data.frame 

    items that are checked: 
    - all columns exists and nothing got dropped 
    - dtypes of columns are correct 
    '''
    resp = get_subjects()
    subj_df = hf.subject_to_df(resp)
    all_subject_cols = create_colname_list(resp[0])

    check_cols = set(all_subject_cols) - set(subj_df.columns.tolist())
    assert check_cols == set(
    ), 'the following columns are missing from reshaped output %s' % (
        check_cols)
    return
