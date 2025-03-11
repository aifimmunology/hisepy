import sys
import os
import pytest
import unittest
from unittest import TestCase
import mock
from unittest.mock import patch, MagicMock
import requests
import pandas as pd
import pyreadr

sys.path.insert(0, '../')

import hisepy.upload as hpu
import hisepy.common_utils as cu
from hisepy.auth import ide_instance_guid, instance_account_guid, IDEInstance
from hisepy.upload import get_study_space

_here = os.path.abspath(os.path.dirname(hpu.__file__))
CONFIG = cu.read_yaml('{}/config.yaml'.format(_here))


class TestIDEInstance():

    # set to a os env var to get IDE instance
    os.environ["IDE_INSTANCE_GUID"] = "ide123"
    os.environ["INSTANCE_ACCOUNT_GUID"] = "account123"

    # create a fixture that mocks get ide instance object
    @pytest.fixture
    def mock_IDEInstance(self):

        # mock the get request
        mock_data = {
            'destinationProjectGuid': 'fakeProjectGuid',
            "podName": "pod",
            "id": "ide123",
            "tags": ["tag1", "tag2", "IDE_DEFAULT:default_store,permanent"]
        }
        mock_response = MagicMock()

        # mock up instance object attributes
        mock_response.podName = mock_data['podName']
        mock_response.tags = mock_data['tags']
        mock_response.id = mock_data['id']
        mock_response.destinationProjectGuid = mock_data[
            'destinationProjectGuid']
        with patch("hisepy.common_utils.hise_get", return_value=mock_response):
            ide = cu.hise_get(
                cu.hise_url("tracer", "ide_instance", ide_instance_guid()),
                False)
        return ide

    # check that the mock object is created with expected vals
    def test_ide_mock(self, mock_IDEInstance):
        # set env var
        assert mock_IDEInstance.id == "ide123"
        assert mock_IDEInstance.podName == "pod"
        assert mock_IDEInstance.tags == [
            "tag1", "tag2", "IDE_DEFAULT:default_store,permanent"
        ]

    # patch the get_default_project method and
    # check that default project is returned
    @patch('hisepy.auth.IDEInstance.get_default_project',
           return_value="fakeProject")
    def test_get_default_project(self, mock_IDEInstance):
        assert IDEInstance.get_default_project() == 'fakeProject'

    # patch the get_default_store method and
    # check that default store is returned
    @patch('hisepy.auth.IDEInstance.get_default_store',
           return_value="fakeStore")
    def test_get_default_store(self, mock_IDEInstance):
        assert IDEInstance.get_default_store() == 'fakeStore'

    # patch the set_default_store method and
    # check that default store is set
    def test_set_default_project(self, mock_IDEInstance):
        # patch the set_default_project method
        with patch('hisepy.auth.IDEInstance.set_default_project',
                   return_value="fakeProject"):
            assert IDEInstance.set_default_project(
                "fakeProject") == "fakeProject"

    # patch the set_default_store method and
    # check that default store is set
    def test_set_default_store(self, mock_IDEInstance):
        # patch the set_default_store method
        with patch('hisepy.auth.IDEInstance.set_default_store',
                   return_value="fakeStore"):
            assert IDEInstance.set_default_store("fakeStore") == "fakeStore"

    def test_instance_guid(self):
        assert ide_instance_guid() == "ide123"

    @pytest.mark.xfail(raises=Exception)
    def test_no_instance_guid(self):
        os.environ["IDE_INSTANCE_GUID"] = ""
        assert ide_instance_guid() == "ide123"

    def test_instance_account_guid(self):
        assert instance_account_guid() == "account123"

    @pytest.mark.xfail(raises=Exception)
    def test_no_instance_account_guid(self):
        os.environ["INSTANCE_ACCOUNT_GUID"] = ""
        assert instance_account_guid() == "account123"


class TestUploader():

    wd = os.getcwd()

    @pytest.fixture
    def mock_ide(self):
        # mock IDEInstance object
        mock_data = {
            'destinationProjectGuid': 'fakeProjectGuid',
            "podName": "pod",
            "id": "ide123",
            "tags": ["tag1", "tag2", "IDE_DEFAULT:default_store,permanent"],
            "environment": {
                "condaEnvName": "test_env"
            }
        }
        mock_response = MagicMock()

        # mock up instance object attributes
        mock_response.podName = mock_data['podName']
        mock_response.tags = mock_data['tags']
        mock_response.id = mock_data['id']
        mock_response.destinationProjectGuid = mock_data[
            'destinationProjectGuid']
        mock_response.environment = mock_data['environment']
        return mock_response

    def test_get_conda_env_name(self, mock_ide):
        assert mock_ide.environment['condaEnvName'] == "test_env"

    def test_get_study_space(self, mock_ide):
        mock_study = {
            "id": "84dfd43c-e034-4ae8-8a50-25ecbce6fe24",
            "accountGuid": "10f58583-1cdf-4f18-8de4-dc1ca94783e2",
            "projectGuid": "a5b6683c-2fed-4e5f-8f76-f87c67eedc85",
            "name": "test study",
            "shortName": "testing"
        }
        with patch('hisepy.upload.get_study_space',
                   return_value=mock_study):
            assert hpu.get_study_space(
                "84dfd43c-e034-4ae8-8a50-25ecbce6fe24") == mock_study

    @patch('subprocess.run')
    def test_do_conda_export(self, mock_subprocess_run):
        # Simulate successful export
        mock_subprocess_run.return_value = 0

        with patch('hisepy.upload.get_conda_env_name',
                   return_value="test_env") as gce:
            export_path = hpu.do_conda_export()

            expected_env_dir = f"{CONFIG['STORES']['ENV_STORE']}/{gce()}"
            expected_command = f"conda env export -p {expected_env_dir} > {CONFIG['STORES']['TEMP_STORE']}/environment.yml"

            # Assert expected behavior
            assert export_path == f"{CONFIG['STORES']['TEMP_STORE']}/environment.yml"
            mock_subprocess_run.assert_called_once_with(expected_command,
                                                        shell=True)

    """ this method is not in use anymore: 1/2/25
    @patch('hisepy.upload.get_study_space',
           return_value={
               "projectGuid": "mock_project_guid",
               "name": "mock_study_space"
           })
    @patch('hisepy.upload.project_guid_to_shortname',
           return_value="mock_project")
    @patch('hisepy.common_utils.get_from_config',
           return_value='{}/tmp'.format(os.getcwd()))
    def test_move_file_to_output_staging(self, mock_ides, mock_project,
                                         mock_config):

        # remove test file before testing
        if os.path.exists("{}/tmp".format(self.wd)):
            os.system("rm -r {}/tmp".format(self.wd))

        # Test successful file move
        source_file = '{}/{}'.format(self.wd, "test_file.txt")
        os.system("touch {}".format(source_file))

        dest_file = hpu.move_file_to_output_staging(str(source_file), None,
                                                     "mock_study_space_id")
        assert os.path.exists(dest_file)

        # Test file overwrite
        hpu.move_file_to_output_staging(str(source_file),
                                         None,
                                         "mock_study_space_id",
                                         replace_ok=True)

        # Test error for existing file without replace_ok
        with pytest.raises(ValueError):
            hpu.move_file_to_output_staging(str(source_file), None,
                                             "mock_study_space_id")

        # Test error for missing project and study space
        with pytest.raises(ValueError):
            hpu.move_file_to_output_staging(str(source_file), None,
                                             "no study")

        # clean up test file
        os.system("rm -r {}/tmp".format(self.wd))
        os.system("rm {}".format(source_file))

    def test_check_project_against_study_space(self):
        # patch helper methods and
        # Test successful match
        with patch('hisepy.upload.get_study_space', return_value={"projectGuid": "mock_project_guid", "name": "mock_study_space"}), \
            patch('hisepy.upload.project_guid_to_shortname', return_value="mock_project"), \
            patch('hisepy.common_utils.get_projects', return_value=pd.DataFrame({"guid": ["mock_project_guid"], "short_name": ["mock_project"]})):
            assert hpu.check_project_against_study_space(
                "mock_project", "mock_study_guid") is None

        # Test error for mismatch
        with pytest.raises(ValueError), \
        patch('hisepy.upload.get_study_space', return_value={"badProjectGuid": "mock_project_guid", "name": "mock_study_space"}), \
        patch('hisepy.upload.project_guid_to_shortname', return_value='mock_project'), \
        patch('hisepy.common_utils.get_projects', return_value=pd.DataFrame({"guid": ["mock_project_guid"], "short_name": ["mock_project"]})):
            hpu.check_project_against_study_space("mock_project",
                                                   "bad_study_id")
    """
    def test_validate_upload_input_ids(self):

        # create cache log file wiht some sample and file ids
        cache_file = f"{self.wd}/{CONFIG['IDE']['CACHE_LOG_NAME']}"
        cache_df = pd.DataFrame({
            "fileId": ["f1", "f2"],
            'replicaFileId' : ['fr1', 'fr2'],
            "sampleId": ["s1", "s2"],
            'replicaSampleId' : ['sr1', 'sr2']
        })
        pyreadr.write_rds(cache_file, cache_df)
        assert cu.validate_upload_input_ids(['f1', 'f2'], ['s1', 's2'],
                                            self.wd) is None

        # Test error for missing file id
        with pytest.raises(AssertionError), \
            patch('hisepy.auth.debug', return_value=1):
            cu.validate_upload_input_ids(['abc'], ['s1', 's2'], self.wd)

    def test_validate_upload_data(self):
        # create a temporary file
        file_path = f"{self.wd}/file.txt"
        os.system(f"touch {file_path}")

        # test successful validation
        assert hpu.validate_upload_data(files=[file_path],
                                        study_space_id='study123',
                                        project='proj',
                                        title='a cool title',
                                        input_file_ids=['f1', 'f2']) is None

        # test error for missing file
        with pytest.raises(ValueError):
            hpu.validate_upload_data(files=[file_path],
                                     study_space_id='study123',
                                     project='proj',
                                     title='a cool title',
                                     input_file_ids=[])

            hpu.validate_upload_data(files=[file_path],
                                     study_space_id=None,
                                     project=None,
                                     title='a cool title',
                                     input_file_ids=['f1', 'f2'])

        # clean up test file
        os.system(f"rm {file_path}")

    def test_gen_upload_body(self):
        # create temporary files
        os.system(f"touch {self.wd}/file1.txt")
        os.system(f"touch {self.wd}/file2.txt")

        assert hpu.gen_upload_body(
            [f"{self.wd}/file1.txt", f"{self.wd}/file2.txt"],
            ["txt", "txt"]) == {
                "files": [{
                    "name": f"{self.wd}/file1.txt",
                    "type": "txt"
                }, {
                    "name": f"{self.wd}/file2.txt",
                    "type": "txt"
                }]
            }

        # clean up temporary files
        os.system(f"rm {self.wd}/file1.txt")
        os.system(f"rm {self.wd}/file2.txt")
