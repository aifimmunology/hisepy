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
import hisepy.hise_requests as hreq
from hisepy.auth import hise_server, get_bearer_token_header, guest_hise_server, ide_is_from_guest_account
from hisepy.logging import with_default_logging, logger
import hisepy.reader_utils as ru

# setting global config
_here = os.path.abspath(os.path.dirname(__file__))
CONFIG = cu.read_yaml('{}/config.yaml'.format(_here))


@with_default_logging
def lookup_queryable_fields(field_type='all', is_public=False) -> pd.DataFrame:
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

    endpoint = ""
    if is_public:
        valid_types = CONFIG["MATERIALIZED_VIEW"][
            "PUBLIC_QUERYABLE_FIELDS"] + ["all"]
        if field_type not in valid_types:
            raise ValueError(
                f"Invalid field_type '{field_type}'. Must be one of {valid_types}."
            )
        endpoint = "PUBLISHING"
        collection_fields = CONFIG["MATERIALIZED_VIEW"][
            "PUBLIC_QUERYABLE_FIELDS"]
    else:
        valid_types = CONFIG["MATERIALIZED_VIEW"]["QUERYABLE_FIELDS"] + ["all"]
        if field_type not in valid_types:
            raise ValueError(
                f"Invalid field_type '{field_type}'. Must be one of {valid_types}."
            )
        endpoint = "LEDGER"
        collection_fields = CONFIG["MATERIALIZED_VIEW"]["QUERYABLE_FIELDS"]
    all_fields = []

    for collection in collection_fields:

        url = f"https://{hise_server()}/{CONFIG[endpoint][f'{collection.upper()}_SEARCH_PATH']}?field_names=true"

        try:
            fields = hreq.hise_post(url, data=json.dumps({"Filter": {}}))
        except Exception as e:
            raise SystemError(
                f"Failed to retrieve field names for collection '{collection}': {e}"
            )

        # keep only fields that have a '.' and belong to the current collection or cohort
        user_fields = [
            f.split('.')[1] for f in fields
            if '.' in f and f.split('.')[0] in {collection, 'cohort'}
        ]

        # remove file type if public
        if is_public:
            user_fields = [f for f in user_fields if f != "fileType"]

        try:
            df = pd.DataFrame({"field": user_fields, "field_type": collection})
            df = df.loc[~df["field"].isin(["cohort", "sampleGuid"])]
            df.loc[df["field"] == "cohortGuid", "field_type"] = "cohort"

            # add name field for release collection if public
            if is_public:
                df.loc[df["field"] == "name", "field_type"] = "release"

            if collection == "sample":
                df = pd.concat([
                    df,
                    pd.DataFrame([{
                        "field": "bridgingControl",
                        "field_type": "sample"
                    }])
                ],
                               ignore_index=True)

        except Exception as e:
            raise SystemError(
                f"Failed to process DataFrame for collection '{collection}': {e}"
            )
        all_fields.append(df)

    all_fields_df = pd.concat(all_fields, ignore_index=True).drop_duplicates()

    if field_type == "all":
        return all_fields_df

    # return only requested field type and cohort fields
    mask = all_fields_df["field_type"].isin([field_type, "cohort"])
    return all_fields_df.loc[mask].drop_duplicates()


@with_default_logging
def lookup_unique_entries(field: str) -> list:
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
    try:
        # fetch all queryable fields
        all_fields_df = lookup_queryable_fields()

        # validate input
        valid_fields = all_fields_df['field'].unique().tolist()
        if field not in valid_fields:
            raise ValueError(
                f"Invalid field: '{field}'. Must be one of: {valid_fields}")

        # determine the field type
        field_type = (all_fields_df.loc[all_fields_df['field'] == field,
                                        'field_type'].iloc[0])

        # Append 'ID' suffix if necessary
        if field in ('pool', 'panel'):
            field = f"{field}ID"

        # Build URL and make request
        url = (f"https://{hise_server()}/"
               f"{CONFIG['LEDGER']['LEDGER_NAME']}/"
               f"{field_type}?distinct_field={field}")
        unique_fields = cu.hise_get(url)

        if not isinstance(unique_fields, list):
            raise ValueError("Unexpected response format: expected a list.")

        # Remove empty or null values and deduplicate
        unique_fields = [
            v for v in unique_fields if v not in (None, "", "null")
        ]
        return np.unique(unique_fields)

    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Failed to fetch unique entries: {e}") from e

    except Exception as e:
        raise RuntimeError(f"Error in lookup_unique_entries: {e}") from e


def list_queryable_fields(is_public=False):
    ''' Returns a list of fields user can use to create a query
    '''
    df = lookup_queryable_fields(is_public=is_public)
    df = df.loc[
        (~df['field_type'].isin(['emr', 'lab'])
         & ~df['field'].isin(['cohort'])),
    ]

    fields = ""
    if is_public:
        fields = CONFIG['MATERIALIZED_VIEW']['PUBLIC_QUERYABLE_FIELD_TYPES']
    else:
        fields = CONFIG['MATERIALIZED_VIEW']['QUERYABLE_FIELDS']

    id_fields = ['{}.id'.format(i) for i in fields]
    return df['field'].unique().tolist() + id_fields
