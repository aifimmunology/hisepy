""" common_utils.py

Description: common methods for SDK development, but not available for end/HISE users

Methods:

Contributors: James Harvey
"""

import os
import shutil
import tarfile
import yaml
import pyreadr
import pandas as pd
import datetime
import json
import pathlib

# directory of hisepy package
_here = os.path.abspath(os.path.dirname(__file__))
chunk_size = 100 * 1024


def read_yaml(file_path):
    with open(file_path, "r") as f:
        return yaml.safe_load(f)


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
    for (root, dir, file) in os.walk(directory):
        [
            files_list.append('{}/{}'.format(root, f)) for f in file
            if f in filenames
        ]
    return files_list


def remove_dir(directory):
    """ Removes entire directory, including any child files """
    shutil.rmtree(directory)
    return True


def log_downloaded_files(hise_file):
    """ Exports, or creates, a .rds file in data.frame format and saves it in user's 
        home directory 

        Parameters: 
            hise_file : hise_file object
    """
    CONFIG = read_yaml('{}/config.yaml'.format(_here))
    cache_file_path = '{h}/{c}'.format(h=CONFIG['IDE']['HOME_DIR'],
                                       c=CONFIG['IDE']['CACHE_LOG_NAME'])
    cache_df = pd.DataFrame()
    download_workdir = os.getcwd()

    if os.path.exists(cache_file_path):
        cache_file = pyreadr.read_r(cache_file_path)

        # extract out the data.frame
        cache_df = cache_file[None]

    # do some logging - what samples and files were downloaded?
    # descriptors can have > 1 entry if filetype == Olink
    # so lets just take the first sampleID if that's the case
    if type(hise_file['descriptors']) is list:
        this_sample_id = hise_file['descriptors'][0]['sample']['id']
        this_file_id = hise_file['descriptors'][0]['file']['id']
    elif type(hise_file['descriptors']) is dict:
        this_sample_id = hise_file['descriptors']['sample']['id']
        this_file_id = hise_file['descriptors']['file']['id']
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
    if input_file_ids is not None:
        assert type(input_file_ids) is list
    if input_sample_ids is not None:
        assert type(input_sample_ids) is list

    CONFIG = read_yaml('{}/config.yaml'.format(_here))
    cache_file_path = '{h}/{c}'.format(h=CONFIG['IDE']['HOME_DIR'],
                                       c=CONFIG['IDE']['CACHE_LOG_NAME'])

    if (not os.path.exists(cache_file_path)):
        raise FileNotFoundError(
            "No files have been downloaded into this IDE. You cannot upload results without utilizing any HISE input data."
        )

    cache_df = pyreadr.read_r(cache_file_path)[None]

    # loop through those ids and check they have been downloaded at some point
    invalid_file_ids = []
    mismatch_download_sources = dict()
    notebook_dir = os.getcwd()
    for f in input_file_ids:
        if f not in cache_df['fileId'].unique():
            invalid_file_ids += [f]

    invalid_sample_ids = []
    for s in input_sample_ids:
        if s not in cache_df['sampleId'].unique():
            invalid_sample_ids += [s]

    if len(invalid_file_ids) > 0:
        raise AssertionError(
            "The following file Ids were not downloaded in this IDE. You cannot reference a file in a result without downloading it first. {}"
            .format(invalid_file_ids))
    if len(invalid_sample_ids) > 0:
        raise AssertionError(
            "The following sample Ids were not downloaded in this IDE. You cannot refernce a file in a result without downloading it first. {}"
            .format(invalid_sample_ids))

    return


def verify_file_count(dir, expected_num_files):
    """ Checks if the number of files in a directory is correct """

    file_count = 0
    # recursively walk down tree and check if current iteration is a file
    for root_dir, this_dir, file in os.walk(dir):
        file_count += len(file)
    if file_count != expected_num_files:
        raise ValueError("Expected to find %d files, but only %d were found" %
                         (expected_num_files, file_count))
    return True


def parse_hise_response(resp):
    obj = None
    try:
        obj = json.loads(resp.text)
        if "Errors" in obj and len(obj["Errors"]) > 0:
            msg = obj["Errors"][0]["Message"]
        else:
            msg = resp.reason
    except:
        msg = resp.reason

    if resp.status_code != 200:
        raise SystemError(
            "%s request to %s returned with status %d. %s" %
            (resp.request.method, resp.url, resp.status_code, msg))
    return obj


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
        for chunk in resp.iter_content(chunk_size):
            f.write(chunk)
    print('file successfully downloaded: {}'.format(dest))
    return
