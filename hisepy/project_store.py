""" project_store.py

Description:

Contributors: James Harvey
"""

import json
import os

import pandas as pd
import requests

import hisepy.common_utils as cu
from hisepy.auth import get_bearer_token_header

# load config for global variables and endpoints
_here = os.path.abspath(os.path.dirname(__file__))
CONFIG = cu.read_yaml('{}/config.yaml'.format(_here))


def list_project_stores():
    """
    Lists all project stores a user has access to

    Returns:
        list of project short-names user has access to
    """
    url = 'https://{ser}/{hy}/{pfe}'.format(
        ser=hise_server(),
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
        data.frame containing fileIds and fileNames
    """
    store = {'stores': [store_name]}
    url = 'https://{ser}/{hy}/{pfe}/{f}'.format(
        ser=hise_server(),
        hy=CONFIG['HYDRATION']['HYDRATION_NAME'],
        pfe=CONFIG['PROJECT_STORE']['PROJECT_STORE_ENDPOINT'],
        f='files')
    resp = requests.post(url,
                         data=json.dumps(store),
                         headers=get_bearer_token_header())
    if resp.status_code != 200:
        raise SystemError("Request to {} failed with status {}".format(
            url, resp.status_code))
    obj = json.loads(
        resp.text
    )[0]  # only allow users to submit 1 store_name at a time, so we always index the first entry

    df = pd.DataFrame(obj['files'])
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
    Returns:
        True if download was successful
    """

    def _submit_url_download(url: str, store: str, filen: str):
        if '/' not in filen:
            truncate_file_name = filen
        else:
            truncate_file_name = filen.split('/', maxsplit=1)[1]
        resp = requests.request("GET",
                                url,
                                headers=get_bearer_token_header(),
                                stream=True)
        if resp.status_code != 200:
            err_obj = json.loads(resp.text)['Errors'][0]['Message']
            raise SystemError("Request to {} failed with status {}: {}".format(
                url, resp.status_code, err_obj))
        with open('{}/{}/{}'.format(os.getcwd(), store, truncate_file_name),
                  'wb') as f:
            for chunk in resp.iter_content(
                    CONFIG['IDE']['DOWNLOAD_CHUNK_SIZE']):
                f.write(chunk)

    # create directory
    try:
        if subdir != '':
            new_dir = '{}/{}/{}'.format(os.getcwd(), store_name, subdir)
        else:
            new_dir = '{}/{}'.format(os.getcwd(), store_name)
        os.mkdir(new_dir)
    except:  # directory already exists, but we don't want to error out
        pass
    ps_df = list_files_in_project_store(store_name)[['name', 'id']]

    # case where user wants to download all files within a subdir they uploaded
    if (file_name == '') & (subdir != ''):
        # find all files that has that subdir in name
        list_files = list_files_in_project_store(
            store_name)['name'].unique().tolist()

        # subset to entries with '/<subdir>/' in name
        subdir_files = [x for x in list_files if '/{}/'.format(subdir) in x]

        # create urls for each file in subset
        url_list = []
        for i in subdir_files:
            this_url = 'https://{ser}/{hy}/{pfe}/{fol}/{fil}/{fn}'.format(
                ser=hise_server(),
                hy=CONFIG['HYDRATION']['HYDRATION_NAME'],
                pfe=CONFIG['PROJECT_STORE']['PROJECT_STORE_ENDPOINT'],
                fol=store_name,
                fil='files',
                fn=i)
            _submit_url_download(this_url, store_name, i)
            ps_file_id = ps_df.loc[ps_df['name'].eq(i), 'id'].item()
            cu.log_project_download(ps_file_id)
    else:
        # create url download
        url = 'https://{ser}/{hy}/{pfe}/{fol}/{fil}/{fn}'.format(
            ser=hise_server(),
            hy=CONFIG['HYDRATION']['HYDRATION_NAME'],
            pfe=CONFIG['PROJECT_STORE']['PROJECT_STORE_ENDPOINT'],
            fol=store_name,
            fil='files',
            fn=file_name)
        _submit_url_download(url, store_name, file_name)
        ps_file_id = ps_df.loc[ps_df['name'].eq(file_name), 'id'].item()
        cu.log_project_download(ps_file_id)
    return True


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
        file_name (str): name of file that you want unpromoted and visible
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
        ser=hise_server(),
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
        message = 'Request to {} failed with status {}:'.format(
            url, resp.status_code)
        try:
            obj = json.loads(resp.text)
            if 'Errors' in obj and len(obj['Errors']) > 0:
                message = obj['Errors'][0]['Message']
        except:
            pass
        raise SystemError(message)

    return True
