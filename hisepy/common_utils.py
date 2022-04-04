""" common_utils.py

Description: common methods for SDK development, but not available for end/HISE users

Methods:

Contributors: James Harvey
"""

import os
import shutil
import tarfile

import yaml


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
