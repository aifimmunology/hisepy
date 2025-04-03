import sys

sys.path.insert(
    0, '../')  # TODO: fix this up before getting a cloud build trigger
from unittest.mock import patch
import hisepy.reader as hpr
import hisepy.common_utils as hpcu
import os
import pytest
import pyreadr


class TestReader:

    @pytest.fixture
    def init_test(self):
        self.file_ids = ['file_id1', 'file_id2']
        self.query_id = ['query_id1']
        self.query_dict = {'field1': ['value1']}
        self.query_file_dict = {'fileType': ['txt'], 'cohortGuid': ['cohortA']}

        # TODO: at some point, metadata models will be generalized
        # and tests will most likely need to be adjusted
        self.descriptor_obj = {
            'descriptors': {
                'file': {
                    'id': 'file_id1',
                    'name': 'file_name1'
                },
                'sample': {
                    "id": "smaple_id1",
                    'sampleKitGuid': 'sample_kit_guid1'
                },
                'subject': {
                    'id': 'subject_id1',
                    'subjectGuid': 'subject_guid1',
                    'biologicalSex': "Male"
                },
                "specimens": {},
                "lab": {},
                "survey": {}
            }
        }
        self.list_descriptor = [
        ]  # TODO for olink data, or any other data has multiple samples per file

        self.mock_ide_obj = {'id': 'ide_id1', 'name': 'ide_name1', 'type': 'Legacy'}

    def test_validate_download_params(self):
        file_ids = ['file_id1', 'file_id2']
        query_id = ['query_id1']
        query_dict = {'field1': ['value1']}
        assert hpcu.validate_download_params(
            file_list=file_ids, query_id=None, query_dict=None
        ), "Failed to validate download params but it should have passed"

        assert hpcu.validate_download_params(
            file_list=None, query_id=query_id, query_dict=None
        ), "Failed to validate download params but it should have passed"

        assert hpcu.validate_download_params(
            file_list=None, query_id=None, query_dict=query_dict
        ), "Failed to validate download params but it should have passed"

    @pytest.mark.xfail(raises=Exception)
    def test_fail_validate_download_params(self):

        bad_file_ids = 'file_id1'
        bad_query_id = 'query_id1'
        bad_query_dict = {'field1': 'value1'}
        query_dict_not_dict = ["field1", "value1"]
        with pytest.raises(Exception,
                           match="file_ids parameter must be a list"):
            hpcu.validate_download_params(file_list=bad_file_ids,
                                          query_id=bad_query_id,
                                          query_dict=bad_query_dict)

        with pytest.raises(Exception,
                           match="query_id parameter must be a list"):
            hpcu.validate_download_params(file_list=[bad_file_ids],
                                          query_id=bad_query_id,
                                          query_dict=bad_query_dict)

        with pytest.raises(
                Exception,
                match=
                "One of file_ids, query_dict, or query_id must be a non-null"):
            hpcu.validate_download_params(file_list=None,
                                          query_id=None,
                                          query_dict=None)

        with pytest.raises(
                Exception,
                match="query dictionary values must be of type list"):
            hpcu.validate_download_params(file_list=[bad_file_ids],
                                          query_id=[bad_query_id],
                                          query_dict=bad_query_dict)

        with pytest.raises(
                Exception,
                match="query dictionary values must be of type list"):
            hpcu.validate_download_params(file_list=None,
                                          query_id=None,
                                          query_dict=query_dict_not_dict)

    def test_parse_file_descriptor_from_file(self, init_test):
        file_id, file_name, desc = hpcu.parse_file_descriptor_from_hise_file(
            self.descriptor_obj)
        assert file_id == 'file_id1', "Failed to parse file id correctly"
        assert file_name == "file_name1", "Failed to parse file name correctly"
        assert desc == self.descriptor_obj[
            'descriptors'], "Failed to parse descriptor correctly"

    @pytest.mark.xfail(raises=Exception)
    def test_log_downloaded_files(self):
        cwd = os.getcwd()

        # remove log file if it exists
        if os.path.exists('.hisefilelog.rds'):
            os.remove('.hisefilelog.rds')

        # create log file and make sure file exists
        hpcu.log_project_download('file_id1', cwd)
        assert os.path.exists('.hisefilelog.rds'), "Failed to save log file"

        # open file, and check if file_id1 is in the file
        log_file = pyreadr.read_r('.hisefilelog.rds')[None]
        fileIds = log_file['fileId'].values
        assert 'file_id1' in fileIds, "Failed to log downloaded files correctly. Expected file_id1, but it does not exist in the log file"

    def test_log_replica_file_download(self, init_test):
        cwd = os.getcwd()

        # remove log file if it exists
        if os.path.exists('.hisefilelog.rds'):
            os.remove('.hisefilelog.rds')

        # try to create a log file and make sure file exists
        hpcu.log_replica_file_download(self.descriptor_obj, 'file_id1', cwd)
        assert not os.path.exists(
            '.hisefilelog.rds'
        ), "this was not a replica file, so it should not be logged in this case"

        # now create a log file
        hpcu.log_replica_file_download(self.descriptor_obj, 'file_id2', cwd)
        assert os.path.exists('.hisefilelog.rds'), "Failed to save log file"

        # open the file and check if file_id1 is in the file
        log_file = pyreadr.read_r('.hisefilelog.rds')[None]
        fileIds = log_file['replicaFileId'].values
        assert 'file_id1' in fileIds, "Failed to log downloaded files correctly. Expected file_id1, but it does not exist in the log file"

    """ NOTE: can't test this here because it makes an api call
    def test_add_prefix_to_query(self):
        qd = {'id': ['fff']}
        qd_sample = {'visitName': ['vn1'], 'sampleKitGuid': ['skg']}
        qd_new = hpr._add_prefix_to_query(qd)
        qd_sample_new = hpr._add_prefix_to_query(qd_sample)
        assert qd_new == {
            'file.id': ['fff']
        }, "Failed to add prefix to query correctly"
        assert qd_sample_new == {
            'sample.visitName': ['vn1'],
            'sample.sampleKitGuid': ['skg']
        }, "Failed to add prefix to query correctly"
    """

    def test_get_filetype(self):
        file1 = 'file1.txt'
        file2 = 'file2.csv'
        assert hpcu.get_filetype(
            file1) == 'txt', "Failed to get filetype correctly"
        assert hpcu.get_filetype(
            file2) == 'csv', "Failed to get filetype correctly"

    # TODO: needs refactoring
    def test_post_query(self):
        return

    """ NOTE: can't test this here because it makes a POST request. need to deal with authentication
    def test_query_files(self, init_test):
        hpr.query_files(self.query_file_dict)
        return
    """

    def test_convert_query_dict_to_mongo_query(self, init_test):

        with patch("hisepy.lookup.list_queryable_fields",
                   return_value=['field1']):
            mq = hpr.MongoQuery(self.query_dict)
            converted_dict = mq.query_dict_to_mongo_query(mq.query_dict)
            #converted_dict = hpr.convert_query_dict_to_mongo_query(self.query_dict)
            assert converted_dict == {
                'field1': {
                    '$in': ['value1']
                }
            }, "Failed to convert query dictionary to mongo query"
        with patch("hisepy.lookup.list_queryable_fields",
                   return_value=['fileType', 'cohortGuid']):
            mq2 = hpr.MongoQuery(self.query_file_dict)
            assert mq2.query_dict_to_mongo_query(mq2.query_dict) == {
                'fileType': {
                    '$in': ['txt']
                },
                'cohortGuid': {
                    '$in': ['cohortA']
                }
            }, "Failed to convert query dictionary to mongo query"

    @pytest.mark.xfail(raises=AssertionError)
    def test_fail_validate_query_files_params(self, init_test):
        with pytest.raises(
                AssertionError,
                match=
                "One of file_ids, query_dict, or query_id must be a non-null"):
            hpr.validate_post_query_params(None, None, None)

        with pytest.raises(AssertionError,
                           match="You must only use 1 parameter"):
            hpr.validate_post_query_params(self.file_ids, self.query_id, None)

        with pytest.raises(
                AssertionError,
                match="You must pass a list of file ids to read_files"):
            hpr.validate_post_query_params(self.file_ids, None,
                                           self.query_dict)

    def test_validate_query_files_params(self, init_test):
        hpr.validate_post_query_params(self.file_ids, None, None)
        hpr.validate_post_query_params(None, self.query_id[0], None)
        hpr.validate_post_query_params(None, None, self.query_dict)

    @pytest.mark.xfail(raises=AssertionError)
    def test_fail_validate_query_files_params(self, init_test):
        with pytest.raises(Exception,
                           match="fileType must be in your query dictionary"):
            hpr.validate_query_files_params(self.query_dict)

        with pytest.raises(
                Exception,
                match="query dictionary values must be of type list"):
            hpr.validate_query_files_params({'fileType': 'txt'})




    """ TODO: properly mock a class that's instantiated from a GET call 
    def test_is_legacy_ide(self, init_test):
        with patch('hisepy.common_utils.get_ide', return_value=self.mock_ide_obj), patch('hisepy.auth.IDEInstance', return_value=self.mock_ide_obj):
            assert hpcu.is_legacy_ide(), "Expected legacy IDE, but did not get it"
    """

    # TODO: needs refactoring
    def test_read_files(self):
        return
    
    def test_validate_samples_subjects_params(self, init_test):
        hpr.validate_samples_subjects_params(self.file_ids, None)
        hpr.validate_samples_subjects_params(None, self.query_dict)

    def test_fail_validate_samples_subjects_params(self, init_test):
        with pytest.raises(
                Exception,
                match="either list of ids or query_dict must be a non-null"):
            hpr.validate_samples_subjects_params(None, None)
        with pytest.raises(
                Exception,
                match="You must only use 1 parameter"):
            hpr.validate_samples_subjects_params(self.file_ids, self.query_dict)
