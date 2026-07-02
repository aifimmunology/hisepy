""" project_store.py

Description:

Contributors: James Harvey
"""

import json
import os

import pandas as pd
import requests

import hisepy.common_utils as cu
from hisepy.auth import get_bearer_token_header, hise_server, IDEInstance, guest_hise_server, ide_is_from_guest_account
from hisepy.logging import with_default_logging, logger

# load config for global variables and endpoints
_here = os.path.abspath(os.path.dirname(__file__))
CONFIG = cu.read_yaml('{}/config.yaml'.format(_here))


@with_default_logging
def list_project_stores() -> list:
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


@with_default_logging
def list_files_in_project_store(store_name: str) -> pd.DataFrame:
    """
    Returns information about what files are present in a given project store

    Parameters:
        store_name (str): name of project store
    Returns:
        data.frame containing fileIds and fileNames
    """
    if type(store_name) is not str:
        raise ValueError("store_name must be of type str")

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


@with_default_logging
def download_from_project_store_v1(store_name: str,
                                   file_name: str | None = None,
                                   subdir: str | None = None):
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
    if type(store_name) is not str:
        raise ValueError("store_name must be of type str")

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

            cu.log_downloaded_files_or_samples(ps_file_id, None,
                                               CONFIG['STORES']['TEMP_STORE'])
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
        cu.log_downloaded_files_or_samples(ps_file_id, None,
                                           CONFIG['STORES']['TEMP_STORE'])
    return True


@with_default_logging
def download_from_project_store(store_name: str,
                                file_name: str | None = None,
                                subdir: str | None = None) -> bool:
    """
    Downloads a given file onto a user's IDE

    Parameters:
        store_name (str): name of project store
        file_name (str, optional): Name of the specific file to download.
        subdir (str, optional): Subdirectory name; if specified, downloads all
            files under that subdirectory.
    Returns:
        True if download was successful
    """

    # validate input parameters
    if not isinstance(store_name, str):
        raise ValueError("`store_name` must be a string.")
    if file_name is not None and not isinstance(file_name, str):
        raise ValueError("`file_name` must be a string if provided.")
    if subdir is not None and not isinstance(subdir, str):
        raise ValueError("`subdir` must be a string if provided.")
    if not store_name.strip():
        raise ValueError("`store_name` cannot be empty.")
    if not file_name and not subdir:
        raise ValueError(
            "Specify either `file_name` or `subdir` to download from.")

    # retrieve available files
    try:
        ps_df = list_files_in_project_store(store_name)[['name', 'id']]
    except Exception as e:
        raise RuntimeError(
            f"Failed to list files in project store '{store_name}': {e}")

    ide_name = IDEInstance().podName
    files_to_download = []

    # determine which files to download
    if subdir:
        all_files = ps_df['name'].unique().tolist()
        files_to_download = [f for f in all_files if f'/{subdir}/' in f]
        if not files_to_download:
            raise ValueError(f"No files found in subdirectory '{subdir}'.")
    else:
        if file_name not in ps_df['name'].values:
            raise ValueError(
                f"File '{file_name}' not found in store '{store_name}'.")
        files_to_download = [file_name]

    # download each file
    for f in files_to_download:
        url = (f"https://{hise_server()}/"
               f"{CONFIG['HYDRATION']['HYDRATION_NAME']}/"
               f"{CONFIG['PROJECT_STORE']['PROJECT_STORE_ENDPOINT']}/"
               f"{store_name}/{ide_name}/files/{f}")

        try:
            response = requests.get(url,
                                    headers=get_bearer_token_header(),
                                    timeout=30)
            obj = cu.parse_hise_response(response)
            local_path = obj.get("file")
            ps_file_id = ps_df.loc[ps_df['name'].eq(f), 'id'].item()
            cu.log_downloaded_files_or_samples(ps_file_id, None,
                                               CONFIG['STORES']['TEMP_STORE'])

            logger.info(f"File '{f}' successfully downloaded to {local_path}")

        except requests.Timeout:
            raise RuntimeError(f"Download timed out for file '{f}'.")
        except requests.RequestException as e:
            raise RuntimeError(f"Network error while downloading '{f}': {e}")
        except Exception as e:
            raise RuntimeError(f"Failed to process file '{f}': {e}")

    logger.info(
        f"Successfully downloaded {len(files_to_download)} file(s) from store '{store_name}'."
    )
    return True


@with_default_logging
def promote_file_in_project_store(store_name: str, file_name: str) -> bool:
    """
    Mark a file in a project store to be promoted to the permanent store. 
    Promoted files will not be listed in hp.list_files_in_project_store()

    Parameters:
        store_name (str): name of project store
        file_name (str): name of file
    Returns:
        True if function call was a success
    """

    # validate input parameters
    if not isinstance(store_name, str):
        raise ValueError("`store_name` must be a string.")
    if file_name is not None and not isinstance(file_name, str):
        raise ValueError("`file_name` must be a string if provided.")
    if not store_name.strip():
        raise ValueError("`store_name` cannot be empty.")
    return project_store_file_action(store_name, file_name,
                                     CONFIG['PROJECT_STORE']['PROMOTION_TAG'])


@with_default_logging
def set_file_metadata_in_project_store(store_name : str, 
                                       file_name : str, 
                                       fields_to_set : dict, 
                                       replace_where_multiple : bool = False): 
    """
    Add or modify panel ID, batch ID, user tags, and sample references on a file in a project store, to make it more easily findable when searching HISE
    
    Parameters: 
        store_name (str): name of project store 
        file_name (str): name of file 
        fields_to_set (dict): dictionary containing the fields to set. 
            Possible keys are 'panelId', 'batchId', 'userTags', and 'sampleRefs'.
            'panelId' and 'batchId' should be strings, 'userTags' should be a dictionary, and 'sampleRefs' should be a list of sample references.
        replace_where_multiple (bool): if True, will replace the field values even if there are multiple existing values. If False, will not replace if there are multiple existing values. Default is False.

    Returns: 
        Response from the HISE server after attempting to set the metadata.

    Example: 
            set_file_metadata_in_project_store(
                store_name='my_project_store',
                file_name='my_file.txt',
                fields_to_set={
                    'panelId': 'panel_123',
                    'batchId': 'batch_456',
                    'userTags': {'other': 'value1', 'name': 'value2'},
                    'sampleRefs': ['sample_1', 'sample_2']
                },
                replace_where_multiple=True
            )
    """
    
    # validate params 
    if not isinstance(store_name, str) or store_name is None:
        raise ValueError("`store_name` must be a string.")
    if not isinstance(file_name, str) or file_name is None:
        raise ValueError("`file_name` must be a string.")
    if not isinstance(fields_to_set, dict) or fields_to_set is None:
        raise ValueError("`fields_to_set` must be a dictionary.")
    if not isinstance(replace_where_multiple, bool):
        raise ValueError("`replace_where_multiple` must be a boolean.")

    # extract vals from keys, and check if they are valid
    panel_id = fields_to_set.get('panelId', None)
    batch_id = fields_to_set.get('batchId', None)
    user_tags = fields_to_set.get('userTags', None)
    sample_refs = fields_to_set.get('sampleRefs', None)
    if panel_id is not None and not isinstance(panel_id, str):
        raise ValueError("`panelId` must be a string if provided.")
    if batch_id is not None and not isinstance(batch_id, str):
        raise ValueError("`batchId` must be a string if provided.")
    if user_tags is not None and not isinstance(user_tags, dict):
        raise ValueError("`userTags` must be a list if provided.")
    if sample_refs is not None and not isinstance(sample_refs, list):
        raise ValueError("`sampleRefs` must be a list if provided.")
    elif sample_refs is not None: 
        refs = dict()
        for sf in sample_refs:
            refs[sf] = None
        fields_to_set['sampleRefs'] = refs

    fields_to_set['replaceWhereMultiple'] = replace_where_multiple

    resp = cu.parse_hise_response(requests.request("PUT",
                            'https://{ser}/{hy}/{pfe}/{fol}/{fil}/{fn}'.format(
                                ser=hise_server(),
                                hy=CONFIG['HYDRATION']['HYDRATION_NAME'],
                                pfe=CONFIG['PROJECT_STORE']['PROJECT_STORE_ENDPOINT'],
                                fol=store_name,
                                fil='files',
                                fn=file_name),
                            data=json.dumps(fields_to_set),
                            headers=get_bearer_token_header()))

    return resp 


@with_default_logging
def undo_promote_in_project_store(store_name: str, file_name: str) -> bool:
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
    # validate input parameters
    if not isinstance(store_name, str):
        raise ValueError("`store_name` must be a string.")
    if file_name is not None and not isinstance(file_name, str):
        raise ValueError("`file_name` must be a string if provided.")
    if not store_name.strip():
        raise ValueError("`store_name` cannot be empty.")
    return project_store_file_action(store_name, file_name,
                                     CONFIG['PROJECT_STORE']['AVAILABLE_TAG'])


@with_default_logging
def delete_file_in_project_store(store_name: str, file_name: str) -> bool:
    """
    Deletes a file in the project store, so long as it is not otherwise in use
    The file will not be visible through list_files_in_project_store()    

    Parameters:
        store_name (str): name of project store
        file_name (str): name of file 
    Returns:
        True if function call was a success
    """
    # validate input parameters
    if not isinstance(store_name, str):
        raise ValueError("`store_name` must be a string.")
    if file_name is not None and not isinstance(file_name, str):
        raise ValueError("`file_name` must be a string if provided.")
    if not store_name.strip():
        raise ValueError("`store_name` cannot be empty.")
    return project_store_file_action(store_name, file_name,
                                     CONFIG['PROJECT_STORE']['DELETED_TAG'])


@with_default_logging
def undo_delete_in_project_store(store_name: str, file_name: str) -> bool:
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
    # validate input parameters
    if not isinstance(store_name, str):
        raise ValueError("`store_name` must be a string.")
    if file_name is not None and not isinstance(file_name, str):
        raise ValueError("`file_name` must be a string if provided.")
    if not store_name.strip():
        raise ValueError("`store_name` cannot be empty.")
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
