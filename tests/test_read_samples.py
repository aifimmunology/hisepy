import sys

sys.path.insert(0, '../')  # to be able to import hisepy package

import hisepy
import hisepy.reader as hr
import hisepy.formatter as hf
import hisepy.common_utils as cu

# testing framework
import pytest

CONFIG = cu.read_yaml('{}/hisepy/config.yaml'.format(sys.path[0]))


def get_samples():
    return hr.read_samples(["d30413d7-c71a-406d-8d75-38bac07b6bc8"],
                           to_df=False)


def create_colname_list(field_name, resp):
    colnames = []
    for i in resp.keys():
        colnames.append('%s.%s' % (field_name, i))
    return colnames


def check_metadata_cols(sample_df, this_obj, k):

    these_cols = create_colname_list(k, this_obj)
    check_cols = set(these_cols) - set(sample_df.columns.tolist())
    assert check_cols == set(), "the following columns are missing %s" % (
        check_cols)
    return True


def check_specimens_cols(sample_df, this_obj, k):
    # NOTE: multiple specimens can exist for a single sample
    # we'll also check each specimen has the same columns
    first_specimen_cols = this_obj[0].keys()
    check_cols = set(first_specimen_cols) - set(sample_df.columns.tolist())
    assert check_cols == set(
    ), "the following columns are missing from the reshaped object, %s" % (
        check_cols)
    for i in list(range(1, len(this_obj))):
        check_keys = set(this_obj[i].keys()) - set(first_specimen_cols)
        assert check_keys == set(), 'the following extra keys exist %s' % (
            check_keys)
    return


def check_survey_cols(sample_df, this_obj, k):
    # NOTE: multile surveys for a single sample may exist
    # and questions may differ between different surveys
    # import pdb; pdb.set_trace()
    for i in list(range(0, len(this_obj))):
        cols_in_response = []
        for k in this_obj[i].keys():
            if k == 'answers':
                cols_in_response += create_colname_list(k, this_obj[i][k])
            else:
                cols_in_response.append(k)
        check_cols = set(cols_in_response) - set(sample_df.columns)
        assert check_cols == set(
        ), "the following columns are missing from the reshaped survey object %s" % (
            check_cols)
    return


def test_read_samples():
    get_samples()
    return


# NOTE: the following are missing: [batchIdList, panelIdList, haslabResults]
def test_read_samples_reshape():
    resp = get_samples()
    sample_df = hf.sample_to_df(resp)
    for k in resp[0].keys():
        this_obj = resp[0][k]
        if type(this_obj) is dict:
            if k in CONFIG['METADATA_FIELDS']['DESCRIPTORS']:
                check_metadata_cols(sample_df['metadata'], this_obj, k)
        elif type(this_obj) is str:
            assert k in sample_df[
                'metadata'].columns, "the following column doesn't exist in the reshaped object %s" % (
                    k)
        elif type(this_obj) is list:
            if k in CONFIG['METADATA_FIELDS']['SPECIMENS']:
                check_specimens_cols(sample_df['specimens'], this_obj, k)
            elif k in CONFIG['METADATA_FIELDS']['SURVEY']:
                check_survey_cols(sample_df['survey'], this_obj, k)
            else:
                print('list value for key... %s' % (k))
        else:
            print('unexpected stuff... %s' % (k))
    return


if __name__ == "__main__":
    test_read_samples_reshape()
