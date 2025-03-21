import sys

sys.path.insert(
    0, '../')  # TODO: fix this up before getting a cloud build trigger
from unittest.mock import patch
import hisepy.formatter as hpf
import hisepy.common_utils as hpcu
import os
import pandas as pd 
import pandas.testing as pdt
import pytest
import pyreadr


class TestFormatter: 

    @pytest.fixture
    def init_test(self):
        self.subject_metadata = {
            "id": "id1",
            "accountGuid": "random_acct_guid",
            "projectGuid": "random_project_guid",
            "ageAtEnrollment": "",
            "biologicalSex": "",
            "birthYear": "",
            "certificateGuids": {},
            "customData": [
                {
                    "schemeId": "scheming",
                    "data": {
                        "strain": "C57BL/6"
                    }
                }
            ],
            "droppedOut": False,
            "deleted": "",
            "ethnicity": "",
            "fileReferences": {},
            "species": "micky mouse"
        }
        self.expected_subject_df = pd.DataFrame({"id": ["id1"], 
                                "accountGuid":["random_acct_guid"],
                                "projectGuid":["random_project_guid"], 
                                "ageAtEnrollment" : [""],
                                "biologicalSex" : [""],
                                "birthYear" : [""],
                                "certificateGuids" : [""],
                                "customData.schemeId" : ["scheming"],
                                "customData.data" : [{'strain': 'C57BL/6'}],
                                "droppedOut" : [False],
                                "deleted" : [""],
                                "ethnicity" : [""],
                                "fileReferences" : [""],
                                "species" : ["micky mouse"]}).sort_index(axis=1)


    def test_reshape_custom_metadata(self, init_test): 
        formatted_metadata_df = hpf.reshape_custom_metadata(self.subject_metadata).sort_index(axis=1)

        # check column names match 
        assert formatted_metadata_df.columns.tolist() == self.expected_subject_df.columns.tolist(), "Column names do not match"

        # check values match 
        diff = self.expected_subject_df.compare(formatted_metadata_df, align_axis=1)
        assert diff.empty, f"Dataframes are not equal: {diff}"

    
