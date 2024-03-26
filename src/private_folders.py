import json
import os

import pandas as pd
import requests

import common_utils as cu
from src.auth import get_bearer_token_header
from reader import hise_url
from util import load_config

# load config for global variables and endpoints
_here = os.path.abspath(os.path.dirname(__file__))
CONFIG = load_config()


def upload_file_to_private_folder(folder_name: str, file_path: str):
    '''
    Uploads a file to a private folder.

    Parameters:
        folder_name (str) : Name of Private Folder.
        file_path (str): Filepath of file you want uploaded.

    Returns:
        Response object
    '''
    assert type(folder_name) is str, 'folder_name must be of type str'
    assert type(file_path) is str, 'file_name must be of type str'
    assert len(
        file_path) < 1024, 'file_name character length cannot exceed 1024'

    this_file = {'file': open(file_path, 'rb')}
    url = hise_url('hydration',
                   'user_folder_path',
                   resource='%s/files' % (folder_name))
    resp = cu.parse_hise_response(
        requests.post(url, files=this_file, headers=get_bearer_token_header()))
    return resp


def list_files_in_all_private_folders():
    ''' Returns a data.frame of all private folders and files that are within each '''
    url = hise_url('hydration', 'user_folder_path')
    resp = cu.parse_hise_response(
        requests.get(url, headers=get_bearer_token_header()))
    return pd.DataFrame(resp)


def list_files_in_private_folder(folder_name=None):
    '''
    Lists files inside a given private folder.

    Parameters:
        folder_name (str) : Name of private folder.
    Returns:
        Data.frame with columns [folder,files]
    '''
    url = hise_url('hydration',
                   'user_folder_path',
                   resource='%s/files' % (folder_name))
    resp = cu.parse_hise_response(
        requests.get(url, headers=get_bearer_token_header()))
    return pd.DataFrame(resp['result'])


def create_private_folder(folder_name: str, file_expiration: int = None):
    '''
    Creates a new private folder.

    Note: Current max number of private folders = 10.

    Parameters:
        folder_name (str) : Name of folder to create.
        file_expiration (int) : Days until files in Private Folder get deleted. (Default None. Files won't be deleted)
    Returns:
        Response object
    '''
    assert type(folder_name
                ) is str, 'The name of folder must be assigned a string value.'

    # validate file_expiration parameter
    if file_expiration is None:
        file_expiration = ""
    else:
        assert type(
            file_expiration
        ) is int, 'file_expiration must be an integer that denotes the number of days until a file is removed.'
        file_expiration = str(file_expiration)

    # create url and payload
    folder_info = {
        'folderName': folder_name,
        'fileExpiration': file_expiration
    }
    url = hise_url('hydration', 'user_folder_path')
    resp = cu.parse_hise_response(
        requests.post(url,
                      data=json.dumps(folder_info),
                      headers=get_bearer_token_header()))

    return resp


def move_file_in_private_folder(file_name: str, source_folder: str,
                                destination_folder: str):
    '''
    Move a file between Private Folders.

    Parameters:
        file_name (str) : name of the file to move.
        source_folder (str) : name of the Private Folder where the file currently exists.
        destination_folder (str) : name of Private Folder to move the file to.
    Returns:
        Response object
    '''
    assert type(file_name) is str, 'file_name must be of type str'
    assert type(source_folder) is str, 'source_folder must be of type str'
    assert type(
        destination_folder) is str, 'destination_folder must be of type str'
    url = hise_url('hydration',
                   'user_folder_path',
                   resource='%s/files/%s' % (source_folder, file_name))
    file_info = {'newFolder': destination_folder}

    resp = cu.parse_hise_response(
        requests.put(url,
                     data=json.dumps(file_info),
                     headers=get_bearer_token_header()))
    return resp


def delete_file_in_private_folder(folder_name: str, file_name: str):
    '''
    Delete a file from a Private Folder.

    Parameters:
        folder_name (str) : name of Private Folder.
        file_name (str) : Name of the file you want deleted.
    '''
    assert type(folder_name) is str, 'folder_name must be of type str'
    assert type(file_name) is str, 'file_name must be of type str'

    url = hise_url('hydration',
                   'user_folder_path',
                   resource='%s/files/%s' % (folder_name, file_name))
    resp = cu.parse_hise_response(
        requests.delete(url, headers=get_bearer_token_header()))
    return resp


def download_from_private_folder(folder_name: str, file_name: str):
    '''
    Download a file from a Project Folder to your local working directory.

    Parameters:
        folder_name (str) : Name of Private Folder.
        file_name (str) : Name of file you want downloaded.
    Returns:
        Response object
    '''
    assert type(folder_name) is str, 'folder_name must be of type str'
    assert type(file_name) is str, 'file_name must be of type str'
    assert len(file_name) < 1024, 'file_name must not exceed 1024 characters'

    url = hise_url('hydration',
                   'user_folder_path',
                   resource='%s/files/%s' % (folder_name, file_name))
    resp = requests.get(url, headers=get_bearer_token_header(), stream=True)

    # assign download path
    dest_path = '{}/{}/{}'.format(os.getcwd(), folder_name, file_name)
    return cu.download_response_content(resp, dest_path)


def rename_file_in_private_folder(folder_name: str, old_file_name: str,
                                  new_file_name: str):
    '''
    Rename a file in a Private Folder.

    Parameters:
        folder_name (str) : Name of the Private Folder.
        old_file_name (str) : Name of file you want renamed.
        new_file_name (str) : New name of the file.
    Returns:
        Response object
    '''
    assert type(folder_name) is str, 'folder_name must be of type str'
    assert type(old_file_name) is str, 'old_file_name must be of type str'
    assert type(new_file_name) is str, 'new_file_name must be of type str'
    assert len(new_file_name
               ) < 1024, 'new_file_name character length cannot exceed 1024'

    file_info = {'newName': new_file_name}
    url = hise_url('hydration',
                   'user_folder_path',
                   resource='%s/files/%s' % (folder_name, old_file_name))
    resp = cu.parse_hise_response(
        requests.put(url,
                     data=json.dumps(file_info),
                     headers=get_bearer_token_header()))
    return resp


def delete_private_folder(folder_name):
    '''
    Delete an existing Private Folder

    Parameters:
        folder_name (str) : Name of Private Folder
    Returns:
        Response object
    '''
    assert type(folder_name) is str, "folder_name must be of type str"
    url = hise_url('hydration',
                   'user_folder_path',
                   resource='%s' % (folder_name))
    resp = cu.parse_hise_response(
        requests.delete(url, headers=get_bearer_token_header()))
    return resp
