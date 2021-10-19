''' lookup.py

Description:

Contributors: James Harvey
'''

# libraries 
import os 
import re 
import json
import requests 
import pandas as pd
import numpy as np 
from hisepy.auth import get_from_metadata_server, get_bearer_token_header, server_id_path
import hisepy.common_utils as cu 

# setting global config 
_here = os.path.abspath(os.path.dirname(__file__))
CONFIG = cu.read_yaml('{}/config.yaml'.format(_here))


def lookup_queryable_fields(field_type): 
    '''
    Returns fields users can query on depending on the collection type (i.e file/subject/sample)
    
    NOTE: this will only work for the following values: [file, sample, subject]

        Parameters: 
            field_type : str
                field_type that determines what fields to return 
        
        Returns: 
            fields_df : pd.dataframe 
                data.frame containing all the field names users could query on 
    '''
    assert field_type in CONFIG['MATERIALIZED_VIEW']['QUERYABLE_FIELDS']

    # get a list of searchable fields 
    url = 'https://{ser}/{led}?field_names=true'.format(
        ser=get_from_metadata_server(server_id_path),
        led=CONFIG['LEDGER']['{}_SEARCH_PATH'.format(field_type.upper())])
    resp = requests.request("POST",
                            url,
                            headers=get_bearer_token_header())
    fields = json.loads(resp.text)
    
     # filter to just the collection type user requested 
    user_fields = [name.split('.')[1] for name in fields if ("{}.".format(field_type) in name)]

    # find other fields that are viable, but not necesarrily under the collection type 
    other_fields = []
    other_queryable_collections = CONFIG['MATERIALIZED_VIEW']['QUERYABLE_FIELDS'].copy()
    other_queryable_collections.remove(field_type)
    for of in other_queryable_collections: 
        other_fields += list(filter(lambda x:'{}.'.format(of) in x, fields))
    o_df = pd.DataFrame()
    for i in other_fields: 
        col = i.split('.')[0]
        fi =  i.split('.')[1]
        o_df = o_df.append(pd.DataFrame({'field': [fi], 'field_type':col}))
        
    fields_df = pd.DataFrame({'field' : user_fields})
    fields_df['field_type'] = field_type 
    fields_df = fields_df.append(o_df)

    # remove cohort, if file_type != cohort 
    fields_df = fields_df.loc[(fields_df['field'] != 'cohort'),  ]
    return fields_df 


def lookup_unique_entries(field): 
    '''
    Gets unique values for a given field. 
        Parameters: 
            field : str
                queryable field (e.g fileType, subjectGuid)
        Returns: 
            unique_fields : np.array 
                all unique values for a given field that you can pass in when creating a query 
    '''
    # create a data.frame of all searchable fields 
    all_field_df = pd.DataFrame() 
    for i in CONFIG['MATERIALIZED_VIEW']['QUERYABLE_FIELDS']: 
        tmp_fdf = lookup_queryable_fields(i)
        all_field_df = all_field_df.append(tmp_fdf) 
    
    # subset to users' field of interest 
    user_df = all_field_df.loc[all_field_df['field'] == field,]
    field_type = user_df['field_type'].values[0]

    # create query and POST request 
    url = 'https://{ser}/{led}/{ft}?distinct_field={fi}'.format(
        ser=get_from_metadata_server(server_id_path),
        led=CONFIG['LEDGER']['LEDGER_NAME'], 
        ft=field_type,
        fi=field)

    #  make request and parse through result 
    resp = requests.request('GET',
                            url,
                            headers=get_bearer_token_header())
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


