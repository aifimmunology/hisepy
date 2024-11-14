import sys
import os
import pytest

sys.path.insert(0, '../')

import hisepy.upload_v3 as hpu3
import hisepy.upload as hpu
from hisepy.auth import ide_instance_guid, IDEInstance


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

    def test_get_study_space(self):
        return False

    def test_do_conda_export(self):
        return False

    def test_move_file_to_output_staging(self):
        return False

    def test_check_project_against_study_space(self):
        return False

    def test_validate_upload_input_ids(self):
        return False

    def test_validate_upload_data(self):
        return False

    def test_gen_upload_body(self):
        return False

    def test_ide_instance_guid(self):
        # set env var
        os.environ["IDE_INSTANCE_GUID"] = "123"

        # test
        assert ide_instance_guid() == "123"

    def test_IDEInstance(self, mocker):
        mock_data = {"podName": "pod", "id": "123"}
        mock_response = mocker.MagicMock()
        mock_response.json.return_value = mock_data

        mocker.patch("requests.get", return_value=mock_response)
        ide = IDEInstance()
        print("HEY")
