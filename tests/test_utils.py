from re import M
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, '../')

import hisepy.common_utils as cu
import os
import pytest


def test_whitespace_detection():
    """ tests if a string contains whitespaces
    """

    assert cu.string_contains_whitespaces("/white space") == True
    assert cu.string_contains_whitespaces("/home/jupyter") == False
    assert cu.string_contains_whitespaces(
        "/home/jupyter/bad a file.csv") == True
    return

def test_files_within_private():
    """ tests if a file is within a private directory
    """

    assert len(cu.files_within_private(["/home/jupyter"])) == 0
    assert len(cu.files_within_private(["/home/jupyter/afile.csv"])) == 0
    assert len(cu.files_within_private(["/home/workspace"])) == 0
    assert len(cu.files_within_private(["/home/workspace/private/afile.csv"])) == 1
    assert len(cu.files_within_private(["/home/workspace/private/afile.csv", '/home/workspace/private/subdir/vfile.csv'])) == 2
    return