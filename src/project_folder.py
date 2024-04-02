""" project_folder.py
Description:
Contributors: James Harvey
"""

import json
import os

import pandas as pd
import pyreadr
import requests

import common_utils as cu
from src.auth import get_from_metadata_server, get_bearer_token_header, server_id_path
from util import load_config

# load config for global variables and endpoints
_here = os.path.abspath(os.path.dirname(__file__))
CONFIG = load_config()


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

    files = cu.get_file_list(url, folder)
    df = pd.DataFrame(files)
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

    cache_df = pd.DataFrame()

    # check if the file_id is already logged
    cache_df = cu.check_if_file_id_is_logged(file_id, cache_df)
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
        subdir (str): name of subdirectory
    Returns:
        True if download was successful
    """

    result = cu.handle_downloads(folder_name, file_name, subdir, 'PROJECT_FOLDER', list_files_in_project_folder)

    return result
