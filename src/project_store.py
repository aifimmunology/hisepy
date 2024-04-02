""" project_store.py

Description:

Contributors: James Harvey
"""

import json
import os

import pandas as pd
import requests

import common_utils as cu
from src.auth import get_from_metadata_server, get_bearer_token_header, server_id_path
from util import load_config

# load config for global variables and endpoints
_here = os.path.abspath(os.path.dirname(__file__))
CONFIG = load_config()


def list_project_stores():
    """
    Lists all project stores a user has access to

    Returns:
        list of project short-names user has access to
    """
    url = 'https://{ser}/{hy}/{pfe}'.format(
        ser=get_from_metadata_server(server_id_path),
        hy=CONFIG['HYDRATION']['HYDRATION_NAME'],
        pfe=CONFIG['PROJECT_STORE']['PROJECT_STORE_ENDPOINT'])
    resp = requests.request("GET", url, headers=get_bearer_token_header())
    if resp.status_code != 200:
        raise SystemError("Request to {} failed with status {}".format(
            url, resp.status_code))
    project_list = json.loads(resp.text)['stores']

    if project_list is None or len(project_list) == 0:
        ValueError(
            "user doesn't have access to any project Stores. Please contact dev support if this shouldn't be the case."
        )
    return project_list


def list_files_in_project_store(store_name):
    """
    Returns information about what files are present in a given project store

    Parameters:
        store_name (str): name of project store
    Returns:
        data frame containing fileIds and fileNames
    """
    store = {'stores': [store_name]}
    url = 'https://{ser}/{hy}/{pfe}/{f}'.format(
        ser=get_from_metadata_server(server_id_path),
        hy=CONFIG['HYDRATION']['HYDRATION_NAME'],
        pfe=CONFIG['PROJECT_STORE']['PROJECT_STORE_ENDPOINT'],
        f='files')

    files = cu.get_file_list(url, store)
    df = pd.DataFrame(files)

    df['store_name'] = store_name
    if len(df) == 0:
        ValueError(
            "No files were found in project store... {}".format(store_name))
    return df


def download_from_project_store(store_name, file_name='', subdir=''):
    """
    Downloads a given file onto a user's IDE. The filepath pattern is as follows:
    '~/store_name/file_name'.

    Parameters:
        store_name (str): name of project store
        file_name (str): name of file that you see under 'name' when utilizing
            list_files_in_project_store
        subdir (str): subdirectory
    Returns:
        True if download was successful
    """
    result = cu.handle_downloads(store_name, file_name, subdir, 'PROJECT_STORE', list_files_in_project_store)

    return result


def promote_file_in_project_store(store_name, file_name):
    """
    Mark a file in a project store to be promoted to the permanent store.
    Promoted files will not be listed in hp.list_files_in_project_store()

    Parameters:
        store_name (str): name of project store
        file_name (str): name of file
    Returns:
        True if function call was a success
    """
    return project_store_file_action(store_name, file_name,
                                     CONFIG['PROJECT_STORE']['PROMOTION_TAG'])


def undo_promote_in_project_store(store_name, file_name):
    """
    Undoes the promotion action, so long as the file
    has not already been moved to the permanent store.
    The file will once again be visible through list_files_in_project_store()

    Parameters:
        store_name (str): name of project store
        file_name (str): name of file that you want demoted and visible
    Returns:
        True if function call was a success
    """
    return project_store_file_action(store_name, file_name,
                                     CONFIG['PROJECT_STORE']['AVAILABLE_TAG'])


def delete_file_in_project_store(store_name, file_name):
    """
    Deletes a file in the project store, so long as it is not otherwise in use
    The file will not be visible through list_files_in_project_store()

    Parameters:
        store_name (str): name of project store
        file_name (str): name of file
    Returns:
        True if function call was a success
    """
    return project_store_file_action(store_name, file_name,
                                     CONFIG['PROJECT_STORE']['DELETED_TAG'])


def undo_delete_in_project_store(store_name, file_name):
    """
    Undoes the file delete action, so long as it is within the file's retention period
    (usually 90 days)
    The file will once again be visible through list_files_in_project_store()

    Parameters:
        store_name (str): name of project store
        file_name (str): name of file that you want undeleted and visible
    Returns:
        True if function call was a success
    """
    return project_store_file_action(store_name, file_name,
                                     CONFIG['PROJECT_STORE']['AVAILABLE_TAG'])


def project_store_file_action(store_name, file_name, action):
    tag_field = CONFIG['PROJECT_STORE']['TAG_FIELD_NAME']
    json_tag = {tag_field: action}
    url = 'https://{ser}/{hy}/{pfe}/{fol}/{fil}/{fn}'.format(
        ser=get_from_metadata_server(server_id_path),
        hy=CONFIG['HYDRATION']['HYDRATION_NAME'],
        pfe=CONFIG['PROJECT_STORE']['PROJECT_STORE_ENDPOINT'],
        fol=store_name,
        fil='files',
        fn=file_name)
    resp = requests.request("PUT",
                            url,
                            data=json.dumps(json_tag),
                            headers=get_bearer_token_header())
    if resp.status_code != 200:
        message = 'Request to {} failed with status {}'.format(
            url, resp.status_code)
        try:
            obj = json.loads(resp.text)
            if 'Errors' in obj and len(obj['Errors']) > 0:
                message = obj['Errors'][0]['Message']
        except ValueError:
            print("Error parsing JSON, continuing")
            pass
        raise SystemError(message)

    return True
