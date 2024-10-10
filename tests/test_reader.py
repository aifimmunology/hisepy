import sys

sys.path.insert(
    0, '../')  # TODO: fix this up before getting a cloud build trigger

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

        #
        return

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

        return True

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
        return True

    def test_parse_file_descriptor_from_file(self, init_test):
        file_id, file_name, desc = hpcu.parse_file_descriptor_from_hise_file(
            self.descriptor_obj)
        assert file_id == 'file_id1', "Failed to parse file id correctly"
        assert file_name == "file_name1", "Failed to parse file name correctly"
        assert desc == self.descriptor_obj[
            'descriptors'], "Failed to parse descriptor correctly"
        return True

    # TODO...?
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
        return True

    # TODO...?
    def test_log_replica_file_download(self):
        return False

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
        return True

    def test_get_filetype(self):
        file1 = 'file1.txt'
        file2 = 'file2.csv'
        assert hpcu.get_filetype(
            file1) == 'txt', "Failed to get filetype correctly"
        assert hpcu.get_filetype(
            file2) == 'csv', "Failed to get filetype correctly"
        return True

    # TODO: needs refactoring
    def test_post_query(self):
        return False

    # TODO: needs refactoring
    def test_read_files(self):
        return False

    # TODO: needs refactoring
    def test_cache_files(self):
        return False


############################################################################################################

    def test_validate_user_query_fields(self):
        return False

    def test_append_descriptors(self):
        return False

    def test_get_file_descriptors(self):
        return False
