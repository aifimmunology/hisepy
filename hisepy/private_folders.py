import json
import os

import pandas as pd
import requests
import shutil

import hisepy.common_utils as cu
from hisepy.upload import gen_upload_body
from hisepy.auth import get_bearer_token_header, ide_instance_guid

# load config for global variables and endpoints
_here = os.path.abspath(os.path.dirname(__file__))
CONFIG = cu.read_yaml('{}/config.yaml'.format(_here))


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


def do_post_file_to_private_folder(folder_name: str, file_path: str):
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
    url = cu.hise_url('hydration',
                      'user_folder_path',
                      resource='%s/files' % (folder_name))
    resp = cu.parse_hise_response(
        requests.post(url, files=this_file, headers=get_bearer_token_header()))
    return resp


def do_post_file_to_private_folder_v2(folder_name: str,
                                      file_path: str = None,
                                      list_of_files: list = None):
    '''
    Uploads a file to a private folder.

    Parameters: 
        folder_name (str) : Name of Private Folder.
        file_path (str): Filepath of file you want uploaded.

    Returns: 
        Response object
    '''
    assert type(folder_name) is str, 'folder_name must be of type str'
    assert type(
        file_path) is str or file_path is None, 'file_name must be of type str'
    # assert either file_path, or list_of_files is defined, not both
    assert (file_path is not None) ^ (
        list_of_files is not None
    ), "one of file_path or list_of_files must be defined, not both"

    if file_path is not None:
        assert len(
            file_path) < 1024, 'file_name character length cannot exceed 1024'
        files = [file_path]
    elif list_of_files is not None:
        for f in list_of_files:
            assert len(
                f
            ) < 1024, 'file_name {} character length cannot exceed 1024'.format(
                f)
        files = list_of_files

    qargs = {'instanceGuid': ide_instance_guid()}
    url = cu.hise_url('ide_management',
                      'upload_user_folder_path',
                      resource="%s/files" % folder_name,
                      args=qargs)
    resp = cu.parse_hise_response(
        requests.post(url,
                      json={"files": files},
                      headers=get_bearer_token_header()))
    return resp


def upload_file_to_private_folder(file_path: str = None,
                                  folder_name: str = None,
                                  list_of_files: list = None):
    '''
    Uploads a file to a private folder.

    Parameters: 
        folder_name (str) : (optional)  Name of Private Folder.
        file_path (str): Filepath of file you want uploaded.

    Returns: 
        Response object
    '''
    assert type(
        folder_name
    ) is str or folder_name is None, 'folder_name must be of type str'
    assert type(
        file_path) is str or file_path is None, 'file_name must be of type str'
    assert type(
        list_of_files
    ) is list or list_of_files is None, "list_of_files must be of type list"
    assert (file_path is not None) ^ (
        list_of_files is not None
    ), "one of file_path or list_of_files must be defined, not both"

    if file_path is not None:
        assert len(
            file_path) < 1024, 'file_name character length cannot exceed 1024'
    elif list_of_files is not None:
        for f in list_of_files:
            assert len(
                f
            ) < 1024, 'file_name {} character length cannot exceed 1024'.format(
                f)

    if folder_name is not None:
        return do_post_file_to_private_folder(folder_name, file_path)
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
            return do_post_file_to_private_folder_v2(pfs[0], file_path,
                                                     list_of_files)


def list_files_in_all_private_folders():
    ''' Returns a data.frame of all private folders and files that are within each '''
    url = cu.hise_url('hydration', 'user_folder_path')
    resp = cu.parse_hise_response(
        requests.get(url, headers=get_bearer_token_header()))
    return pd.DataFrame(resp)


def list_files_in_private_folder(folder_name: str = None):
    ''' 
    Lists files inside a given private folder.
    
    Parameters: 
        folder_name (str) : Name of private folder.
    Returns: 
        Data.frame with columns [folder,files]
    '''
    assert type(
        folder_name
    ) is str or folder_name is None, 'folder_name must be of type str'
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


def create_private_folder(folder_name: str):
    '''
    Creates a new private folder. 

    Note: Current max number of private folders = 10. 

    Parameters: 
        folder_name (str) : Name of folder to create. 
    Returns: 
        Response object
    '''
    assert type(folder_name
                ) is str, 'The name of folder must be assigned a string value.'

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
    url = cu.hise_url('hydration',
                      'user_folder_path',
                      resource='%s/files/%s' % (source_folder, file_name))
    file_info = {'newFolder': destination_folder}

    resp = cu.parse_hise_response(
        requests.put(url,
                     data=json.dumps(file_info),
                     headers=get_bearer_token_header()))
    return resp


def delete_file_in_private_folder(file_name: str, folder_name: str = None):
    '''
    Delete a file from a Private Folder. 

    Parameters: 
        folder_name (str) : name of Private Folder.
        file_name (str) : Name of the file you want deleted.
    '''
    assert type(
        folder_name
    ) is str or folder_name is None, 'folder_name must be of type str'
    assert type(file_name) is str, 'file_name must be of type str'

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


def download_from_private_folder(file_name: str,
                                 folder_name: str = None,
                                 dest_path: str = None):
    '''
    Download a file from a Project Folder to your local working directory.

    Parameters:
        file_name (str) : Name of file you want downloaded.
        folder_name (str) : (optional) Name of Private Folder. 
        dest_path (str) : (optional) Destination path to save the file.
    Returns: 
        Response object
    '''
    assert type(
        folder_name
    ) is str or folder_name is None, 'folder_name must be of type str'
    assert type(file_name) is str, 'file_name must be of type str'
    assert len(file_name) < 1024, 'file_name must not exceed 1024 characters'

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
    return cu.download_response_content(resp, dest_path)


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


def delete_private_folder(folder_name):
    ''' 
    Delete an existing Private Folder 

    Parameters: 
        folder_name (str) : Name of Private Folder 
    Returns: 
        Response object 
    '''
    assert type(folder_name) is str, "folder_name must be of type str"
    url = cu.hise_url('hydration',
                      'user_folder_path',
                      resource='%s' % (folder_name))
    resp = cu.parse_hise_response(
        requests.delete(url, headers=get_bearer_token_header()))
    return resp


def find_private_folder_of_file(file_name: str):
    """
    Returns the name of the private folder that the given file belongs to
    
    Parameters: 
        file_name (str) : Name of the file you like to search for. If the file is in a subdirectory, include the entire path.
    Returns:
        Name of private folder that the file belongs to. 
    """

    assert type(file_name) is str, 'file_name must be of type str'
    url = "{}/{}?file={}".format(cu.hise_url("hydration", "user_folder_path"),
                                 "find", file_name)
    resp = cu.parse_hise_response(
        requests.get(url, headers=get_bearer_token_header()))
    return resp
