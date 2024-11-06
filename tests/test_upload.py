import hisepy.upload_v3 as hpu3
import hisepy.upload as hpu
import sys

sys.path.insert(0, '../')

import os
import pytest


class TestUploader:

    @pytest.fixture
    def init_test(self):
        return

    def test_set_default_store(self):
        return False

    def test_set_default_project(self):
        return False

    def test_get_default_store(self):
        return False

    def test_get_default_project(self):
        return False

    def test_get_conda_env_name(self):
        return False

    def test_do_conda_export(self):
        return False

    def test_move_file_to_output_staging(self):
        return False

    def test_check_project_against_study_space(self):
        return False
