import json
import os

import pandas as pd
import requests
import shutil

import hisepy.common_utils as cu
import hisepy.private_folders_util as pfu
from hisepy.upload_utils import gen_upload_body
from hisepy.auth import get_bearer_token_header, ide_instance_guid
from hisepy.logging import with_default_logging, logger

# load config for global variables and endpoints
_here = os.path.abspath(os.path.dirname(__file__))
CONFIG = cu.read_yaml('{}/config.yaml'.format(_here))


@with_default_logging
def create_private_folder(folder_name: str) -> dict:
    '''
    Creates a new private folder. 

    Note: Current max number of private folders = 10. 

    Parameters: 
        folder_name (str) : Name of folder to create. 
    Returns: 
        Response object
    '''
    if not isinstance(folder_name, str):
        raise TypeError('The name of folder must be assigned a string value.')

    # create url and payload
    folder_info = {
        'folderName': folder_name,
    }
    url = cu.hise_url('hydration', 'user_folder_path')
    resp = cu.parse_hise_response(
        requests.post(url,
                      data=json.dumps(folder_info),
                      headers=get_bearer_token_header()))

    return resp


@with_default_logging
def delete_file_in_private_folder(file_name: str,
                                  folder_name: str | None = None) -> dict:
    '''
    Delete a file from a Private Folder. 

    Parameters: 
        folder_name (str) : name of Private Folder.
        file_name (str) : Name of the file you want deleted.
    '''
    if not isinstance(folder_name, str) and folder_name is not None:
        raise TypeError('folder_name must be of type str')
    if not isinstance(file_name, str):
        raise TypeError('file_name must be of type str')

    if folder_name is None:
        pfs = list(list_files_in_all_private_folders()['folder'].values)
        if len(pfs) > 1:
            raise ValueError(
                'Multiple private folders found. Please specify the folder_name parameter. options are: %s'
                % pfs)
        elif len(pfs) == 0:
            raise ValueError(
                'No private folders found. Please contact immunology support')
        else:
            folder_name = pfs[0]
    url = cu.hise_url('hydration',
                      'user_folder_path',
                      resource='%s/files/%s' % (folder_name, file_name))
    resp = cu.parse_hise_response(
        requests.delete(url, headers=get_bearer_token_header()))
    return resp


@with_default_logging
def delete_private_folder(folder_name: str) -> dict:
    ''' 
    Delete an existing Private Folder 

    Parameters: 
        folder_name (str) : Name of Private Folder 
    Returns: 
        Response object 
    '''
    if not isinstance(folder_name, str):
        raise TypeError("folder_name must be of type str")
    url = cu.hise_url('hydration',
                      'user_folder_path',
                      resource='%s' % (folder_name))
    resp = cu.parse_hise_response(
        requests.delete(url, headers=get_bearer_token_header()))
    return resp


@with_default_logging
def download_from_private_folder(file_name: str,
                                 folder_name: str | None = None,
                                 dest_path: str | None = None) -> dict:
    '''
    Download a file from a Project Folder to your local working directory.

    Parameters:
        file_name (str) : Name of file you want downloaded.
        folder_name (str) : (optional) Name of Private Folder. 
        dest_path (str) : (optional) Destination path to save the file.
    Returns: 
        Response object
    '''
    if not isinstance(folder_name, str) and folder_name is not None:
        raise TypeError('folder_name must be of type str')
    if not isinstance(file_name, str):
        raise TypeError('file_name must be of type str')
    if len(file_name) > 1024:
        raise ValueError('file_name must not exceed 1024 characters')

    if folder_name is None:
        pfs = list(list_files_in_all_private_folders()['folder'].values)
        if len(pfs) > 1:
            raise ValueError(
                'Multiple private folders found. Please specify the folder_name parameter. options are: %s'
                % pfs)
        elif len(pfs) == 0:
            raise ValueError(
                'No private folders found. Please contact immunology support')
        else:
            folder_name = pfs[0]
    url = cu.hise_url('hydration',
                      'user_folder_path',
                      resource='%s/files/%s' % (folder_name, file_name))
    resp = requests.get(url, headers=get_bearer_token_header(), stream=True)

    # assign download path
    if dest_path is None:
        dest_path = '{}/{}'.format(os.getcwd(), file_name)
    return pfu.download_response_content(resp, dest_path)


@with_default_logging
def find_private_folder_of_file(file_name: str) -> dict:
    """
    Returns the name of the private folder that the given file belongs to
    
    Parameters: 
        file_name (str) : Name of the file you like to search for. If the file is in a subdirectory, include the entire path.
    Returns:
        Name of private folder that the file belongs to. 
    """

    if not isinstance(file_name, str):
        raise TypeError('file_name must be of type str')

    url = "{}/{}?file={}".format(cu.hise_url("hydration", "user_folder_path"),
                                 "find", file_name)
    resp = cu.parse_hise_response(
        requests.get(url, headers=get_bearer_token_header()))
    return resp


@with_default_logging
def list_files_in_all_private_folders() -> pd.DataFrame:
    ''' Returns a data.frame of all private folders and files that are within each '''
    url = cu.hise_url('hydration', 'user_folder_path')
    resp = cu.parse_hise_response(
        requests.get(url, headers=get_bearer_token_header()))
    return pd.DataFrame(resp)


@with_default_logging
def list_files_in_private_folder(
        folder_name: str | None = None) -> pd.DataFrame:
    ''' 
    Lists files inside a given private folder.
    
    Parameters: 
        folder_name (str) : Name of private folder.
    Returns: 
        Data.frame with columns [folder,files]
    '''
    if not isinstance(folder_name, str) and folder_name is not None:
        raise TypeError('folder_name must be of type str')
    if folder_name is not None:
        url = cu.hise_url('hydration',
                          'user_folder_path',
                          resource='%s/files' % (folder_name))
    else:
        pfs = list(list_files_in_all_private_folders()['folder'].values)
        if len(pfs) > 1:
            raise ValueError(
                'Multiple private folders found. Please specify the folder_name parameter. options are: %s'
                % pfs)
        elif len(pfs) == 0:
            raise ValueError(
                'No private folders found. Please contact immunology support')
        else:
            url = cu.hise_url('hydration',
                              'user_folder_path',
                              resource='%s/files' % (pfs[0]))
    resp = cu.parse_hise_response(
        requests.get(url, headers=get_bearer_token_header()))
    return pd.DataFrame(resp['result'])


@with_default_logging
def move_file_in_private_folder(file_name: str, source_folder: str,
                                destination_folder: str) -> dict:
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
    url = cu.hise_url('hydration',
                      'user_folder_path',
                      resource='%s/files/%s' % (source_folder, file_name))
    file_info = {'newFolder': destination_folder}

    resp = cu.parse_hise_response(
        requests.put(url,
                     data=json.dumps(file_info),
                     headers=get_bearer_token_header()))
    return resp


@with_default_logging
def rename_file_in_private_folder(old_file_name: str,
                                  new_file_name: str,
                                  folder_name: str = None):
    '''
    Rename a file in a Private Folder.

    Parameters: 
        folder_name (str) : Name of the Private Folder. 
        old_file_name (str) : Name of file you want renamed. 
        new_file_name (str) : New name of the file. 
    Returns: 
        Response object
    '''
    assert type(
        folder_name
    ) is str or folder_name is None, 'folder_name must be of type str'
    assert type(old_file_name) is str, 'old_file_name must be of type str'
    assert type(new_file_name) is str, 'new_file_name must be of type str'
    assert len(new_file_name
               ) < 1024, 'new_file_name character length cannot exceed 1024'

    if folder_name is None:
        pfs = list(list_files_in_all_private_folders()['folder'].values)
        if len(pfs) > 1:
            raise ValueError(
                'Multiple private folders found. Please specify the folder_name parameter. options are: %s'
                % pfs)
        elif len(pfs) == 0:
            raise ValueError(
                'No private folders found. Please contact immunology support')
        else:
            folder_name = pfs[0]
    file_info = {'newName': new_file_name}
    url = cu.hise_url('hydration',
                      'user_folder_path',
                      resource='%s/files/%s' % (folder_name, old_file_name))
    resp = cu.parse_hise_response(
        requests.put(url,
                     data=json.dumps(file_info),
                     headers=get_bearer_token_header()))
    return resp


@with_default_logging
def update_private_folder(folder_name: str = None, description: str = None):
    '''
    Update the properties of a Private Folder.

    Parameters: 
        folder_name (str) : Name of Private Folder.
        description (str) : Description of the Private Folder.

    Returns:
        Name of the Private Folder that was updated.
    '''

    if description is not None:
        assert type(description) is str, 'description must be of type str'

    # create url and payload
    folder_info = {"description": description}
    url = cu.hise_url('hydration',
                      'user_folder_path',
                      resource='%s' % (folder_name))
    resp = cu.parse_hise_response(
        requests.put(url,
                     data=json.dumps(folder_info),
                     headers=get_bearer_token_header()))
    return resp['name']


@with_default_logging
def upload_file_to_private_folder(file_path: str = None,
                                  folder_name: str | None = None,
                                  list_of_files: list | None = None,
                                  destination: str | None = None) -> dict:
    '''
    Uploads a file to a private folder.

    Parameters: 
        file_path (str): Filepath of file you want uploaded.
        folder_name (str) : (optional)  Name of Private Folder.
        list_of_files (list): (optional) List of filepaths for upload.
        destination (str): (optional) name of subdirectory to save within ~/private

    Returns: 
        Response object
    '''
    pfu.validate_upload_private_folder_params(file_path, folder_name,
                                              list_of_files, destination)
    if folder_name is not None:
        return pfu.do_post_file_to_private_folder(folder_name, file_path)
    else:  # use nextgen-ide private folder
        pfs = list(list_files_in_all_private_folders()['folder'].values)
        if len(pfs) > 1:
            raise ValueError(
                'Multiple private folders found. Please specify the folder_name parameter. options are: %s'
                % pfs)
        elif len(pfs) == 0:
            raise ValueError(
                'No private folders found. Please contact immunology support')
        else:
            return pfu.do_post_file_to_private_folder_v2(
                pfs[0], file_path, list_of_files, destination)
