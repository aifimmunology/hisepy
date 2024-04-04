""" common_utils.py

Description: common methods for SDK development, but not available for end/HISE users

Methods:

Contributors: James Harvey
"""

import copy
import datetime
import json
import os
import pathlib
import shutil
import tarfile
from enum import Enum

import requests

import pandas as pd
import pyreadr
import formatter as format_helper

from src.auth import debug
from src.util import load_config

from src.auth import get_from_metadata_server, get_bearer_token_header, server_id_path

# directory of hisepy package
_here = os.path.abspath(os.path.dirname(__file__))

CONFIG = load_config()
cache_file_path = '{h}/{c}'.format(h=CONFIG['IDE']['HOME_DIR'], c=CONFIG['IDE']['CACHE_LOG_NAME'])


class DataFramePayload(Enum):
    SAMPLE = 1
    SUBJECT = 2


def get_filetype(this_filename):
    if "." in this_filename:
        return this_filename.split(".")[-1]
    else:
        return "json"


def tardir(output_filename, source_dir):
    """ Utility function that will create a tar file for an entire directory and its children """
    with tarfile.open(output_filename, "w:gz") as tar:
        tar.add(source_dir, arcname=os.path.basename(source_dir))


def list_files_and_dirs(directory):
    """ Lists all files and directories in a given path """
    return os.listdir(directory)


def find_files(directory, filenames):
    """ Given a directory, find all files in a given list """
    files_list = []
    for (root, dir_dir, file) in os.walk(directory):
        [
            files_list.append('{}/{}'.format(root, f)) for f in file
            if f in filenames
        ]
    return files_list


def remove_dir(directory):
    """ Removes entire directory, including any child files """
    shutil.rmtree(directory)
    return True


def parse_file_descriptor_from_hise_file(hise_file):
    """
    Takes a hise_file object and returns its file_id, file_name and the descriptor object

    Parameters:
        hise_file (hise_file): hisepy.reader.hise_file object
    Returns:
        a tuple (file_id, file_name, descriptor object)
    """
    this_file_id = None
    this_file_name = None
    this_desc = None

    if type(hise_file['descriptors']) is list:
        this_file_id = hise_file['descriptors'][0]['file']['id']
        this_file_name = hise_file['descriptors'][0]['file']['name']
        this_desc = hise_file['descriptors'][0]
    elif type(hise_file['descriptors']) is dict:
        this_file_id = hise_file['descriptors']['file']['id']
        this_file_name = hise_file['descriptors']['file']['name']
        this_desc = hise_file['descriptors']
    return this_file_id, this_file_name, this_desc


def log_replica_file_download(hise_file, file_id):
    """
    Creates another log entry. If a file was downloaded in a guest workspace, then the replica fileID is logged

    Parameters:
        hise_file (hise_file): hisepy.reader.hise_file object
        file_id (str): original file_id that's passed in to read_files() or cache_files()
    """
    this_file_id, this_file_name, this_desc = parse_file_descriptor_from_hise_file(
        hise_file)
    if this_file_id != file_id:
        tmp_hise_file = copy.deepcopy(this_desc)
        tmp_hise_file["id"] = file_id
        log_downloaded_files(tmp_hise_file)
    return


def log_downloaded_files(hise_file):
    """ Exports, or creates, a .rds file in data frame format and saves it in user's
        home directory

        Parameters:
            hise_file : hise_file object
    """
    cache_df = pd.DataFrame(columns=[
        'fileId', 'sampleId', 'downloadSourceDir', 'downloadTimeStamp'
    ])
    download_workdir = os.getcwd()

    if os.path.exists(cache_file_path):
        cache_file = pyreadr.read_r(cache_file_path)

        # extract out the data.frame
        cache_df = cache_file[None]

    # do some logging - what samples and files were downloaded?
    # descriptors can have > 1 entry if filetype == Olink
    # so lets just take the first sampleID if that's the case
    this_file_id = None
    this_sample_id = None
    if type(hise_file['descriptors']) is list:
        this_sample_id = hise_file['descriptors'][0]['sample']['id']
        this_file_id = hise_file['descriptors'][0]['file']['id']
    elif type(hise_file['descriptors']) is dict:
        this_sample_id = hise_file['descriptors']['sample']['id']
        this_file_id = hise_file['descriptors']['file']['id']

    # no need to append something a user has already downloaded and logged
    if this_file_id in cache_df['fileId'].values:
        pass
    else:
        this_entry_df = pd.DataFrame(
            data={
                'fileId': [this_file_id],
                'sampleId': [this_sample_id],
                'downloadSourceDir': [download_workdir],
                'downloadTimeStamp': [str(datetime.datetime.now())]
            })
        cache_df = pd.concat([cache_df, this_entry_df])
        pyreadr.write_rds(
            '{h}/{d}'.format(h=CONFIG['IDE']['HOME_DIR'],
                             d=CONFIG['IDE']['CACHE_LOG_NAME']), cache_df)
    return


def validate_upload_input_ids(input_file_ids: list, input_sample_ids: list):
    """ Checks that files associated with a result have
        been seen in a user's IDE
    """
    if debug():
        # allow local testing of stuff
        return

    if input_file_ids is not None:
        assert type(input_file_ids) is list
    if input_sample_ids is not None:
        assert type(input_sample_ids) is list

    if not os.path.exists(cache_file_path):
        raise FileNotFoundError(
            "No files have been downloaded into this IDE. You cannot upload results without utilizing any HISE input "
            "data."
        )

    cache_df = pyreadr.read_r(cache_file_path)[None]

    # loop through those ids and check they have been downloaded at some point
    invalid_file_ids = []

    for f in input_file_ids:
        if f not in cache_df['fileId'].unique():
            invalid_file_ids += [f]

    invalid_sample_ids = []
    for s in input_sample_ids:
        if s not in cache_df['sampleId'].unique():
            invalid_sample_ids += [s]

    if len(invalid_file_ids) > 0:
        raise AssertionError(
            "The following file Ids were not downloaded in this IDE. You cannot reference a file in a result without "
            "downloading it first. {}"
            .format(invalid_file_ids))
    if len(invalid_sample_ids) > 0:
        raise AssertionError(
            "The following sample Ids were not downloaded in this IDE. You cannot refernce a file in a result without "
            "downloading it first. {}"
            .format(invalid_sample_ids))

    return


def verify_file_count(directory, expected_num_files):
    """ Checks if the number of files in a directory is correct """

    file_count = 0
    # recursively walk down tree and check if current iteration is a file
    for root_dir, this_dir, file in os.walk(directory):
        file_count += len(file)
    if file_count != expected_num_files:
        raise ValueError("Expected to find %d files, but only %d were found" %
                         (expected_num_files, file_count))
    return True


def parse_hise_response(text):
    obj = None
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as e:
        print("Invalid JSON syntax:", e)

    return obj


# def parse_hise_response(resp):
#     obj = None
#     try:
#         obj = json.loads(resp.text)
#         if "Errors" in obj and len(obj["Errors"]) > 0:
#             msg = obj["Errors"][0]["Message"]
#         else:
#             msg = resp.reason
#     except BaseException:
#         msg = resp.reason
#
#     if resp.status_code != 200:
#         raise SystemError(
#             "%s request to %s returned with status %d. %s" %
#             (resp.request.method, resp.url, resp.status_code, msg))
#     return obj


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
                          this_file_name)

    # create directory if it doesn't exist; download
    pathlib.Path(this_path).mkdir(parents=True, exist_ok=True)
    if not os.path.isdir(this_path):
        raise SystemError("unable to create path, %s" % this_path)

    with open(dest, 'wb') as f:
        for chunk in resp.iter_content(CONFIG['IDE']['DOWNLOAD_CHUNK_SIZE']):
            f.write(chunk)
    print('file successfully downloaded: {}'.format(dest))
    return


def check_if_file_id_is_logged(file_id: str, cache_df: pd.DataFrame) -> dict:
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

    return cache_df


# TODO: combine this log_downloaded_files()
def log_project_download(file_id: str):
    """
    Attaches fileId for the project folder file that was downloaded

    Parameters:
        file_id (str) : file_id of file in project folder
    """
    cache_df = pd.DataFrame(columns=[
        'fileId', 'sampleId', 'downloadSourceDir', 'downloadTimeStamp'
    ])

    # check if the file_id is already logged
    validated_cache_df = check_if_file_id_is_logged(file_id, cache_df)
    pyreadr.write_rds(
        '{h}/{d}'.format(h=CONFIG['IDE']['HOME_DIR'],
                         d=CONFIG['IDE']['CACHE_LOG_NAME']), validated_cache_df)

    return


def prompt_user(msg: str = None, additional_fields=None):
    """ Prompts end users in order to continue """
    if msg is None:
        raise ValueError("Must provide a contextual message")
    if additional_fields is None:
        additional_fields = ""
    print("{m}: {af}. Do you want to Proceed? [Y/N]".format(
        m=msg, af=additional_fields))
    user_input = input('(y/n')
    while user_input.lower() not in ['y', 'n']:
        print('please enter either "n" for no, or "y" for yes.')
        user_input = input('(y/n)')
    if user_input.lower() == 'y':
        return True
    elif user_input.lower() == 'n':
        return False


def string_contains_whitespaces(file_str):
    """ returns True if a string contains whitespaces"""

    # loop through each string character and check if it's a whitespace
    if any(s.isspace() for s in file_str):
        return True
    else:
        return False


def get_file_list(url, folder):
    resp = requests.post(url,
                         data=json.dumps(folder),
                         headers=get_bearer_token_header())
    if resp.status_code != 200:
        raise SystemError("Request to {} failed with status {}".format(
            url, resp.status_code))
    obj = json.loads(
        resp.text
    )[0]  # only allow users to submit 1 folder_name at a time, so we always index the first entry

    return obj['files']


def download_file(download_url: str, directory: str, file_name: str):
    truncated_file_name = file_name.split('/', maxsplit=1)[-1]
    resp = requests.get(
        download_url, headers=get_bearer_token_header(), stream=True)
    if resp.status_code != 200:
        raise SystemError(f"Request to {download_url} failed with status {resp.status_code}")
    with open(os.path.join(directory, truncated_file_name), 'wb') as f:
        for chunk in resp.iter_content(CONFIG['IDE']['DOWNLOAD_CHUNK_SIZE']):
            f.write(chunk)


def create_directory(base_dir: str, subdir: str = ''):
    new_dir = os.path.join(base_dir, subdir) if subdir else base_dir
    try:
        os.makedirs(new_dir, exist_ok=True)
    except OSError as e:
        print(f"Directory {new_dir} already exists or error: {e}")


def get_download_url(file_name: str, folder_name: str, endpoint_key: str):
    return 'https://{ser}/{hy}/{pfe}/{fol}/{fil}/{fn}'.format(
        ser=get_from_metadata_server(server_id_path),
        hy=CONFIG['HYDRATION']['HYDRATION_NAME'],
        pfe=CONFIG[endpoint_key][endpoint_key + '_ENDPOINT'],
        fol=folder_name,
        fil='files',
        fn=file_name)


def handle_downloads(folder_name: str, file_name: str, subdir: str, endpoint_key: str, df_function):
    base_dir = os.path.join(os.getcwd(), folder_name)
    create_directory(base_dir, subdir)

    df = df_function(folder_name)[['name', 'id']]
    if file_name:
        files_to_download = [file_name]
    else:
        files_to_download = df['name'].unique().tolist()
        if subdir:
            files_to_download = [x for x in files_to_download if f'/{subdir}/' in x]

    for file in files_to_download:
        url = get_download_url(file, folder_name, endpoint_key)
        download_file(url, base_dir, file)
        file_id = df.loc[df['name'].eq(file), 'id'].item()
        log_project_download(file_id)

    return True


def get_ledger_query(endpoint: str, query: dict, to_df, data_frame_payload: DataFramePayload):
    resp = requests.post(endpoint,
                         data=json.dumps({"filter": query}),
                         headers=get_bearer_token_header())

    if resp.status_code != 200:
        raise SystemError("Request to %s failed with status %d. %s" %
                          (endpoint, resp.status_code, resp.text))

    obj = json.loads(resp.text)
    if obj['payload'] is None:
        raise ValueError("User's query resulted in 0 results")
    if type(obj) is not dict:
        raise TypeError("Response %s is not a list, it is a %s." %
                        (resp.text, type(obj)))
    elif "payload" not in obj:
        raise TypeError("Response %s contained an empty payload!" % resp.text)
    if to_df:
        if data_frame_payload == DataFramePayload.SUBJECT:
            return format_helper.subject_to_df(obj["payload"])

        elif data_frame_payload == DataFramePayload.SAMPLE:
            return format_helper.sample_to_df(obj["payload"])
    else:
        return obj["payload"]
