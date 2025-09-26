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
