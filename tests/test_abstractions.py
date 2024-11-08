from re import M
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, '../')

import os
import pytest
import requests
from unittest import mock
import pytest_mock
import hisepy
import tempfile
from hisepy.auth import get_bearer_token_header
from hisepy.abstraction import AbstractionAppImg, _validate_abstraction_params
from unittest.mock import Mock
from pathlib import Path
import hisepy.common_utils as cu


class TestAbstractionAppImg:

    @pytest.fixture
    def init_test(self):
        # create temporary directory
        self.tmpdir = tempfile.TemporaryDirectory()
        self.tmpdirname = self.tmpdir.name

        # create config file. and other necessary files
        os.system("touch {}/config.toml".format(os.getcwd()))
        os.system("touch {}/build.sh".format(os.getcwd()))
        os.system("touch {}/entrypoint.sh".format(os.getcwd()))
        os.system("touch {}/environment.yml".format(os.getcwd()))

        # create temporary files and instantiate abstractionAppImg
        self.app_path = os.path.normpath("{}/app.py".format(self.tmpdirname))
        self.img_path = os.path.normpath("{}/img.png".format(self.tmpdirname))
        os.system("touch {}/app.py".format(self.tmpdirname))
        os.system("touch {}/img.png".format(self.tmpdirname))
        self.abstraction_img = AbstractionAppImg(
            app_filepath=self.app_path,
            hero_image=self.img_path,
            title='test abstraction',
            description='a description worth reading',
            data_contract_id='fakeGUID123',
            result_file_ids=['scRNA-guid'],
            project_guid='projgu12d',
            work_dir=self.tmpdirname)

        self.metadata_abstraction = AbstractionAppImg(
            app_filepath=self.app_path,
            hero_image=self.img_path,
            title='test abstraction',
            description='a description worth reading',
            data_contract_id='fakeGUID123',
            is_sample_metadata_app=True,
            project_guid='projgu12d',
            work_dir=self.tmpdirname)

        # create tarball
        self.abstraction_img.copy_files_to_tmp(
            self.abstraction_img.abstraction_config_filenames)
        self.abstraction_img.create_tarball()

    def cleanup(self, init_test):
        self.tmpdir.cleanup()

    def test_validate_abstraction_params(self):
        generic_title = 'mocking a title'
        generic_description = "describing stuff"
        generic_contract_id = 'contract-123'
        proj = 'cohorts'
        # test1: trying to create an abstraction using a resultFile
        assert _validate_abstraction_params(
            title=generic_title,
            description=generic_description,
            input_ids=['fake scRNA GUID'],
            data_contract_id=generic_contract_id,
            project=proj,
            additional_files=None,
            additional_dirs=None,
            is_sample_app=False,
            is_subject_app=False
        ), "Failed validation check. should have passed with a guid being passed in"

    # decorator that marks the test as expected to fail if we raise a ValueError
    @pytest.mark.xfail(raises=ValueError)
    def test_failed_param_validation(self):
        generic_title = 'mocking a title'
        generic_description = "describing stuff"
        generic_contract_id = 'contract-123'
        proj = 'cohorts'
        with pytest.raises(
                ValueError,
                match=
                "One of result_file_types, is_sample_metadata_app, is_subject_metadata_app must be specified. Please try again by specifying only one of these parameters."
        ):
            _validate_abstraction_params(title=generic_title,
                                         description=generic_description,
                                         input_ids=['fake scRNA GUID'],
                                         data_contract_id=generic_contract_id,
                                         project=proj,
                                         additional_files=None,
                                         additional_dirs=None,
                                         is_sample_app=True,
                                         is_subject_app=False)
        return

    # arrange mock object for post request to toolchain
    @pytest.fixture
    def mock_post(self):
        mock = Mock()
        mock.patch("requests.post", return_value=mock)
        return mock

    # arrange mock object for params
    @pytest.fixture
    def post_params(self):
        return {
            "title": "mock title",
            "description": "descibing what an abstraction is",
            "inputResultFiles": ['d2700632-4ce8-44df-95ba-9290be3c86b6'],
            "projectGuid": 'project123',
            "notebook": "mock_notebook.ipynb",
            "appDetails": "random text",
            "homedir": "/home/jupyter",
            "instanceId": "user-ide-id"
        }

    @pytest.fixture
    def create_file_arg(self):
        return self.abstraction_img.create_file_arg()

    @pytest.fixture
    def create_url(self, post_params, init_test):
        return self.abstraction_img.create_url(post_params)

    """ this should be an integration test instead of a unit test
    def test_post_request(self, create_url, create_file_arg, mocker):

        mock_post = mocker.patch('requests.post')
        mock_response = mock_post.return_value
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "success"}

        # send it
        resp = self.abstraction_img.send_post(create_url, create_file_arg)

        # assertion checks
        assert resp.status_code == 200
        assert resp.json() == {"status": "success"}
        return
    """

    def test_tarball_creation(self, init_test):
        # init_test() method should have created the tarball, so we just check for it
        assert os.path.isfile('{}/{}'.format(
            self.tmpdirname, self.abstraction_img.abstraction_image_name))
        return

    """ this should be an integration test instead of a unit test
    def test_post_static_image(self, mocker, init_test):
        mock_post = mocker.patch('requests.post')
        mock_response = mock_post.return_value
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "success"}

        # send it
        resp = self.abstraction_img.send_static_image_post(
            self.abstraction_img.create_static_image_url(),
            self.abstraction_img.create_image_dict())

        # assertion checks
        assert resp.status_code == 200
        assert resp.json() == {"status": "success"}
        return
    """

    def test_config_files_exist(self, init_test):
        for f in self.abstraction_img.abstraction_config_filenames:
            assert os.path.isfile('{}/{}'.format(self.abstraction_img.work_dir,
                                                 f))

    def test_determine_app_type(self, init_test):
        app_type = self.abstraction_img.determine_app_type()
        assert app_type == self.abstraction_img.result_file_ids, "didn't determine the correct app type based on how the Abstraction class was initiailized"

        sample_app = self.metadata_abstraction.determine_app_type()
        assert sample_app == ['urn:hise:metadata:sample']
        return

    def test_cleanup(self, init_test):
        self.cleanup(init_test)
        assert os.path.isdir(self.abstraction_img.work_dir) == False
