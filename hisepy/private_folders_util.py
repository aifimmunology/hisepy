import pathlib
import os
import requests
from hisepy.auth import get_bearer_token_header, ide_instance_guid
import hisepy.common_utils as cu

# load config for global variables and endpoints
_here = os.path.abspath(os.path.dirname(__file__))
CONFIG = cu.read_yaml('{}/config.yaml'.format(_here))


def do_post_file_to_private_folder(folder_name: str, file_path: str):
    '''
    Uploads a file to a private folder.

    Parameters: 
        folder_name (str) : Name of Private Folder.
        file_path (str): Filepath of file you want uploaded.

    Returns: 
        Response object
    '''
    if not isinstance(folder_name, list):
        raise TypeError('folder_name must be of type str')
    if not isinstance(file_path, str):
        raise TypeError('file_name must be of type str')
    if len(file_path) > 1024:
        raise ValueError('file_name character length cannot exceed 1024')

    this_file = {'file': open(file_path, 'rb')}
    url = cu.hise_url('hydration',
                      'user_folder_path',
                      resource='%s/files' % (folder_name))
    resp = cu.parse_hise_response(
        requests.post(url, files=this_file, headers=get_bearer_token_header()))
    return resp


def do_post_file_to_private_folder_v2(folder_name: str,
                                      file_path: str | None = None,
                                      list_of_files: list | None = None,
                                      destination: str | None = None):
    '''
    Uploads a file to a private folder.

    Parameters: 
        folder_name (str) : Name of Private Folder.
        file_path (str): Filepath of file you want uploaded.

    Returns: 
        Response object
    '''

    # validate
    if not isinstance(folder_name, str):
        raise TypeError('folder_name must be of type str')
    if not isinstance(file_path, str) and file_path is not None:
        raise TypeError('file_name must be of type str')
    if (file_path is not None) == (list_of_files is not None):
        raise ValueError(
            "Exactly one of `file_path` or `list_of_files` must be defined, not both."
        )
    if file_path is not None:
        if len(file_path) > 1024:
            raise ValueError('file_name character length cannot exceed 1024')
        files = [file_path]
    elif list_of_files is not None:
        for f in list_of_files:
            if len(f) > 1024:
                raise ValueError(
                    f'file_name {f} character length cannot exceed 1024')
        files = list_of_files

    qargs = {'instanceGuid': ide_instance_guid()}
    if destination is not None:
        qargs['destination'] = destination
    url = cu.hise_url('ide_management',
                      'upload_user_folder_path',
                      resource="%s/files" % folder_name,
                      args=qargs)
    resp = cu.parse_hise_response(
        requests.post(url,
                      json={"files": files},
                      headers=get_bearer_token_header()))
    return resp


def download_response_content(resp, dest):
    # check status
    if resp.status_code != 200:
        raise SystemError(
            "%s request to %s returned with status %d. %s" %
            (resp.request.method, resp.url, resp.status_code, resp.text))

    # separate filename and path
    dest_list = dest.split('/')
    this_file_name = dest_list[-1]
    dest_list.pop()
    this_path = '/'.join(dest_list)
    if '.' not in this_file_name:
        raise SystemError("Unable to parse out fileName, %s" %
                          (this_file_name))

    # create directory if it doesn't exist; download
    pathlib.Path(this_path).mkdir(parents=True, exist_ok=True)
    if not os.path.isdir(this_path):
        raise SystemError("unable to create path, %s" % (this_path))

    with open(dest, 'wb') as f:
        for chunk in resp.iter_content(CONFIG['IDE']['DOWNLOAD_CHUNK_SIZE']):
            f.write(chunk)
    print('file successfully downloaded: {}'.format(dest))
    return


def validate_upload_private_folder_params(file_path: str | None = None,
                                          folder_name: str | None = None,
                                          list_of_files: list | None = None,
                                          destination: str | None = None):
    # type validation
    if folder_name is not None and not isinstance(folder_name, str):
        raise TypeError("`folder_name` must be of type str or None.")

    if file_path is not None and not isinstance(file_path, str):
        raise TypeError("`file_path` must be of type str or None.")

    if list_of_files is not None and not isinstance(list_of_files, list):
        raise TypeError("`list_of_files` must be of type list or None.")

    # combination validation
    if (file_path is not None) == (list_of_files is not None):
        raise ValueError(
            "Exactly one of `file_path` or `list_of_files` must be defined, not both."
        )

    # file existence and name length validation
    def validate_file(f: str):
        if not os.path.exists(f):
            raise FileNotFoundError(f"File not found: {f}")
        if len(f) >= 1024:
            raise ValueError(f"File name too long (>1024 characters): {f}")

    if file_path is not None:
        validate_file(file_path)
    elif list_of_files is not None:
        for f in list_of_files:
            validate_file(f)

    # destination validation
    if destination is not None:
        if cu.string_contains_whitespaces(destination):
            raise ValueError(
                "Whitespace detected in `destination`. Please remove all spaces."
            )

    return
