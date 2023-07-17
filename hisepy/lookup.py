""" lookup.py

Description:

Contributors: James Harvey
"""

import json
import os

import numpy as np
import pandas as pd
import requests

import hisepy.common_utils as cu
from hisepy.auth import get_from_metadata_server, get_bearer_token_header, server_id_path

# setting global config
_here = os.path.abspath(os.path.dirname(__file__))
CONFIG = cu.read_yaml('{}/config.yaml'.format(_here))


def lookup_queryable_fields(field_type='all'):
    """
    Returns fields users can query on depending on the collection type. 
    Acceptable values are either 'file', 'sample', or 'subject'

    Parameters:
        field_type (str): field_type that determines what fields to return
    Returns:
        data.frame containing all the field names users could query on
    Example: 
        hp.lookup_queryable_fields(field_type='subject')
    """
    assert field_type in CONFIG['MATERIALIZED_VIEW']['QUERYABLE_FIELDS'] + [
        'all'
    ]
    collection_fields = CONFIG['MATERIALIZED_VIEW']['QUERYABLE_FIELDS']
    all_fields_df = pd.DataFrame()
    for cf in collection_fields:

        # get a list of searchable fields
        url = 'https://{ser}/{led}?field_names=true'.format(
            ser=get_from_metadata_server(server_id_path),
            led=CONFIG['LEDGER']['{}_SEARCH_PATH'.format(cf.upper())])
        resp = requests.post(url, headers=get_bearer_token_header())
        fields = json.loads(resp.text)

        # filter to just the collection type user requested
        user_fields = list(
            filter(lambda x: '.' in x,
                   fields))  # keep only the fields that contain a '.'
        user_fields = [
            name.split('.')[1] for name in user_fields
            if (name.split('.')[0] in ["{}".format(cf), 'cohort'])
        ]
        fields_df = pd.DataFrame({'field': user_fields})
        fields_df['field_type'] = cf

        # remove cohort, if file_type != cohort
        # also fix the field_type for cohort_Guid
        fields_df = fields_df.loc[
            ~(fields_df['field'].isin(['cohort', 'sampleGuid'])), ]
        fields_df.loc[fields_df['field'].eq('cohortGuid'),
                      'field_type'] = 'cohort'
        all_fields_df = pd.concat([all_fields_df, fields_df],
                                  ignore_index=True)

        # sample.bridgingControl isn't a part of sample collection, and is instead part of file.
        # hard-coding and inserting this field to sample
        if cf == 'sample':
            all_fields_df = pd.concat([
                all_fields_df,
                pd.DataFrame({
                    'field': ['bridgingControl'],
                    'field_type': ['sample']
                })
            ],
                                      ignore_index=True)

    if field_type == 'all':
        return all_fields_df.drop_duplicates()
    else:
        return all_fields_df.loc[(
            (all_fields_df['field_type'].eq(field_type)) |
            (all_fields_df['field_type'].eq('cohort'))), ].drop_duplicates()


def lookup_unique_entries(field):
    """
    Returns unique values for a given field.

    Parameters:
        field (str): queryable field (e.g fileType, subjectGuid)
    Returns:
        all unique values for a given field that you can pass in when creating a query
    Examples: 
        hp.lookup_unique_entries('fileType')
        hp.lookup_unique_entries('cohortGuid') 
    """
    # create a data.frame of all searchable fields
    all_field_df = lookup_queryable_fields()

    # check that user submitted a viable field
    assert field in all_field_df['field'].unique().tolist(
    ), "The field you submitted isn't a viable one. Make sure your requesting one of the following fields - {}".format(
        all_field_df['field'].unique())

    # subset to user's field of interest
    user_df = all_field_df.loc[all_field_df['field'] == field, ]
    field_type = user_df['field_type'].values[0]

    # create query and POST request
    if field in ['pool', 'panel']:
        # suffix ID needs to be added for pool and panel when making a request
        field = '{}ID'.format(field)
    url = 'https://{ser}/{led}/{ft}?distinct_field={fi}'.format(
        ser=get_from_metadata_server(server_id_path),
        led=CONFIG['LEDGER']['LEDGER_NAME'],
        ft=field_type,
        fi=field)

    #  make request and parse through result
    resp = requests.request('GET', url, headers=get_bearer_token_header())
    unique_fields = json.loads(resp.text)

    # remove empty entry if it exists
    try:
        unique_fields.remove('')
    except:
        pass

    # ensure values are unique
    np_unique_fields = np.unique(np.array(unique_fields))
    unique_fields = np.unique(np_unique_fields)

    return unique_fields


def list_queryable_fields():
    ''' Returns a list of fields user can use to create a query 
    '''
    df = lookup_queryable_fields()
    df = df.loc[(~df['field_type'].isin(['emr', 'lab'])
                 & ~df['field'].isin(['cohort'])), ]
    id_fields = [
        '{}.id'.format(i)
        for i in CONFIG['MATERIALIZED_VIEW']['QUERYABLE_FIELDS']
    ]
    return df['field'].unique().tolist() + id_fields
