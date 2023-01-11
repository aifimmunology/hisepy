""" project_folder.py
Description:
Contributors: James Harvey
"""

import json
import os

import pandas as pd
import requests
import pyreadr
import datetime
from google.cloud import storage

import hisepy.common_utils as cu
from hisepy.auth import get_from_metadata_server, get_bearer_token_header, server_id_path
from hisepy.reader import hise_file

# load config for global variables and endpoints
_here = os.path.abspath(os.path.dirname(__file__))
CONFIG = cu.read_yaml('{}/config.yaml'.format(_here))


def list_project_folders():
    """
    Lists all project folders a user has access to
    Returns:
        list of project short-names user has access to
    """
    url = 'https://{ser}/{hy}/{pfe}'.format(
        ser=get_from_metadata_server(server_id_path),
        hy=CONFIG['HYDRATION']['HYDRATION_NAME'],
        pfe=CONFIG['PROJECT_FOLDER']['PROJECT_FOLDER_ENDPOINT'])
    resp = requests.request("GET", url, headers=get_bearer_token_header())
    if resp.status_code != 200:
        raise SystemError("Request to {} failed with status {}".format(
            url, resp.status_code))
    project_list = json.loads(resp.text)['folders']

    if len(project_list) == 0:
        ValueError(
            "user doesn't have access to any project Folders. Please contact dev support if this shouldn't be the case."
        )
    return project_list


def list_files_in_project_folder(folder_name):
    """
    Returns information about what files are present in a given project folder
    Parameters:
        folder_name (str): name of project folder
    Returns:
        data.frame containing fileIds and fileNames
    """
    folder = {'folders': [folder_name]}
    url = 'https://{ser}/{hy}/{pfe}/{f}'.format(
        ser=get_from_metadata_server(server_id_path),
        hy=CONFIG['HYDRATION']['HYDRATION_NAME'],
        pfe=CONFIG['PROJECT_FOLDER']['PROJECT_FOLDER_ENDPOINT'],
        f='files')
    resp = requests.post(url,
                         data=json.dumps(folder),
                         headers=get_bearer_token_header())
    if resp.status_code != 200:
        raise SystemError("Request to {} failed with status {}".format(
            url, resp.status_code))
    obj = json.loads(
        resp.text
    )[0]  # only allow users to submit 1 folder_name at a time, so we always index the first entry

    df = pd.DataFrame(obj['files'])
    df['folder_name'] = folder_name
    if len(df) == 0:
        ValueError(
            "No files were found in project folder... {}".format(folder_name))
    return df


def log_project_folder_download(file_id: str):
    """
    Attaches fileId for the project folder file that was downloaded 
    
    Parameters: 
        file_id (str) : file_id of file in project folder 
    """
    cache_file_path = '{h}/{c}'.format(h=CONFIG['IDE']['HOME_DIR'],
                                       c=CONFIG['IDE']['CACHE_LOG_NAME'])
    cache_df = pd.DataFrame()
    download_workdir = os.getcwd()
    if os.path.exists(cache_file_path):
        cache_file = pyreadr.read_r(cache_file_path)

        # extract out the data.frame
        cache_df = cache_file[None]

    # check if the file_id is already logged
    if file_id in cache_df['fileId'].values:
        pass
    else:
        new_entry = pd.DataFrame(
            data={
                'fileId': [file_id],
                'sampleId': [''],
                'downloadSourceDir': [download_workdir],
                'downloadTimeStamp': [str(datetime.datetime.now())]
            })

        cache_df = pd.concat([cache_df, new_entry])
        pyreadr.write_rds(
            '{h}/{d}'.format(h=CONFIG['IDE']['HOME_DIR'],
                             d=CONFIG['IDE']['CACHE_LOG_NAME']), cache_df)
    return


def download_from_project_folder(folder_name, file_name='', subdir=''):
    """
    Downloads a given file onto a user's IDE. The filepath pattern is as follows:
    '~/folder_name/file_name'.
    Parameters:
        folder_name (str): name of project folder
        file_name (str): name of file that you see under 'name' when utilizing 
            list_files_in_project_folder
    Returns:
        True if download was successful
    """

    def _submit_url_download(url: str, foldern: str, filen: str):
        truncate_file_name = filen.split('/', maxsplit=1)[1]
        resp = requests.request("GET",
                                url,
                                headers=get_bearer_token_header(),
                                stream=True)
        if resp.status_code != 200:
            raise SystemError("Request to {} failed with status {}".format(
                url, resp.status_code))
        with open('{}/{}/{}'.format(os.getcwd(), foldern, truncate_file_name),
                  'wb') as f:
            for chunk in resp.iter_content():
                f.write(chunk)

    # create directory
    try:
        if subdir != '':
            new_dir = '{}/{}/{}'.format(os.getcwd(), folder_name, subdir)
        else:
            new_dir = '{}/{}'.format(os.getcwd(), folder_name)
        os.mkdir(new_dir)
    except:  # directory already exists, but we don't want to error out
        pass
    pf_df = list_files_in_project_folder(folder_name)[['name', 'id']]

    # case where user wants to download all files within a subdir they uploaded
    if (file_name == '') & (subdir != ''):
        # find all files that has that subfolder in name
        list_files = pf_df['name'].unique().tolist()

        # subset to entries with '/<subdir>/' in name
        subdir_files = [x for x in list_files if '/{}/'.format(subdir) in x]

        # create urls for each file in subset
        url_list = []
        for i in subdir_files:
            this_url = 'https://{ser}/{hy}/{pfe}/{fol}/{fil}/{fn}'.format(
                ser=get_from_metadata_server(server_id_path),
                hy=CONFIG['HYDRATION']['HYDRATION_NAME'],
                pfe=CONFIG['PROJECT_FOLDER']['PROJECT_FOLDER_ENDPOINT'],
                fol=folder_name,
                fil='files',
                fn=i)
            _submit_url_download(this_url, folder_name, i)
            pf_file_id = pf_df.loc[pf_df['name'].eq(i), 'id'].item()
            cu.log_project_download(pf_file_id)
    else:
        # create url download
        url = 'https://{ser}/{hy}/{pfe}/{fol}/{fil}/{fn}'.format(
            ser=get_from_metadata_server(server_id_path),
            hy=CONFIG['HYDRATION']['HYDRATION_NAME'],
            pfe=CONFIG['PROJECT_FOLDER']['PROJECT_FOLDER_ENDPOINT'],
            fol=folder_name,
            fil='files',
            fn=file_name)
        _submit_url_download(url, folder_name, file_name)
        pf_file_id = pf_df.loc[pf_df['name'].eq(file_name), 'id'].item()
        cu.log_project_download(pf_file_id)
    return True
