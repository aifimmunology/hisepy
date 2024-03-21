from re import M
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, '../')

import hisepy.common_utils as cu
import hisepy.upload as up
import os
import tempfile
import pytest


def test_create_temp_directory():
    """ tests that files and directories were correctly created, 
    and that the original paths are preserved
    """
    base_path = "/home/jupyter"
    tmpdir = tempfile.TemporaryDirectory()
    extra_dir = '/adir'
    orig_path = "{}{}{}".format(tmpdir.name, base_path, extra_dir)

    # create a directory that'll contain some files
    os.makedirs(orig_path)

    # create files
    afile_path = "{}/afile.csv".format(orig_path)
    bfile_path = "{}/bfile.csv".format(orig_path)
    os.system("touch {}".format(afile_path))
    os.system("touch {}".format(bfile_path))

    # create app.py file one directory up
    app_file_path = "{}{}/app.py".format(tmpdir.name, base_path)
    os.system("touch {}".format(app_file_path))

    # test it
    tmpdir2 = tempfile.TemporaryDirectory()
    up.create_temp_directory_files([orig_path, app_file_path], tmpdir2.name)

    # list of expected filepaths and directories
    assert os.path.exists("{}{}".format(
        tmpdir2.name, orig_path)), "expected directory does not exist"
    assert os.path.isfile("{}{}".format(
        tmpdir2.name,
        afile_path)), "expected afile was not copied over correctly"
    assert os.path.isfile("{}{}".format(
        tmpdir2.name, app_file_path)), "expected app.py file does not exist"
    return
