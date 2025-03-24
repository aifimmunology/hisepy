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

        self.sample_metadata = [{'id': 'sampleid',
                                'projectGuid': 'pg-sample',
                                'subject': {'id': 'subjectid1',
                                'subjectGuid': 'BR1002'},
                                'sample': {'visitName': 'Flu Year 1 Day 0',
                                'visitDetails': 'N/A - Flu-Series Timepoint Only',
                                'sampleGuid': '00000sample'},
                                'specimens': [{'sampleId': 'sampleid1',
                                    'specimenGuid': 'PL00002-11',
                                    'specimenType': 'Plasma',
                                    'specimenStatus': 'Stored',
                                    'externalContainerID': '',
                                    'experimentSampleDescription': '',
                                    'timeToProcessingOnset': 3900,
                                    'totalViableCellCount': '',
                                    'additionalPayload': None},
                                {'sampleId': 'sampleid2',
                                    'specimenGuid': 'PL00002-18',
                                    'specimenType': 'Plasma',
                                    'specimenStatus': 'Stored',
                                    'externalContainerID': '',
                                    'experimentSampleDescription': '',
                                    'timeToProcessingOnset': 3900,
                                    'totalViableCellCount': '',
                                    'additionalPayload': None}],
                                'hasLabResults': True,
                                'lab': {'id': 'labid1',
                                'labResults': {'% Basophils': 0.9,
                                    '% Eosinophils': 2.4,
                                    '% Immature Granulocytes': '',
                                    '% Lymphocytes': 39.5,
                                    '% Monocytes': 8.9,
                                    '% Neutrophils': 48.3,
                                    '% Nucleated Red Blood Cells (NRBC)': '',
                                    '% Segmented Neutrophils': ''}},
                                'survey': [{'id': 'survID1',
                                    'sampleKitGuid': 'kitguid1',
                                    'answers': {'allenId': 'BR1002',
                                    'allenKitId': 'KT00002',
                                    'main_anxiety_fearful': '5'}}]}]
        self.expected_sample_output = {'metadata': pd.DataFrame({'id': ['sampleid'],
                                                                'projectGuid': ['pg-sample'],
                                                                'subject.id': ['subjectid1'],
                                                                'hasLabResults': [True],
                                                                'subject.subjectGuid': ['BR1002'],
                                                                'sample.visitName': ['Flu Year 1 Day 0'],
                                                                'sample.visitDetails': ['N/A - Flu-Series Timepoint Only'],
                                                                'sample.sampleGuid': ['00000sample']}),
                                    'specimens': pd.DataFrame({'sampleId': ['sampleid1', 'sampleid2'],
                                                                'specimenGuid': ['PL00002-11', 'PL00002-18'],
                                                                'specimenType': ['Plasma','Plasma'],
                                                                'specimenStatus': ['Stored', 'Stored'],
                                                                'externalContainerID': ['', ''],
                                                                'experimentSampleDescription': ['', ''],
                                                                'timeToProcessingOnset': [3900, 3900],
                                                                'totalViableCellCount': ['', ''],
                                                                'additionalPayload': ['', '']}),
                                    'labResults': pd.DataFrame({'id': ['labid1'],
                                                '% Basophils': [0.9],
                                                    '% Eosinophils': [2.4],
                                                    '% Immature Granulocytes': [''],
                                                    '% Lymphocytes': [39.5],
                                                    '% Monocytes': [8.9],
                                                    '% Neutrophils': [48.3],
                                                    '% Nucleated Red Blood Cells (NRBC)': [''],
                                                    '% Segmented Neutrophils': ['']}),
                                    'survey': pd.DataFrame({'id': ['survID1'],
                                                            'sampleKitGuid': ['kitguid1'],
                                                            'answers.allenId': ['BR1002'],
                                                            'answers.allenKitId': ['KT00002'],
                                                            'answers.main_anxiety_fearful': ['5']})}


    def test_reshape_custom_metadata(self, init_test): 
        formatted_metadata_df = hpf.reshape_custom_metadata(self.subject_metadata).sort_index(axis=1)

        # check column names match 
        assert formatted_metadata_df.columns.tolist() == self.expected_subject_df.columns.tolist(), "Column names do not match"

        # check values match 
        diff = self.expected_subject_df.compare(formatted_metadata_df, align_axis=1)
        assert diff.empty, f"Dataframes are not equal: {diff}"
    
    def test_sample_to_df(self, init_test): 
        formatted_sample_df = hpf.sample_to_df(self.sample_metadata)

        # check column names match
        assert formatted_sample_df['metadata'].sort_index(axis=1).columns.tolist() == self.expected_sample_output['metadata'].sort_index(axis=1).columns.tolist(), "metadata Column names do not match"
        assert formatted_sample_df['specimens'].sort_index(axis=1).columns.tolist() == self.expected_sample_output['specimens'].sort_index(axis=1).columns.tolist(), "specimens Column names do not match"
        assert formatted_sample_df['labResults'].sort_index(axis=1).columns.tolist() == self.expected_sample_output['labResults'].sort_index(axis=1).columns.tolist(), "labResults Column names do not match"
        assert formatted_sample_df['survey'].sort_index(axis=1).columns.tolist() == self.expected_sample_output['survey'].sort_index(axis=1).columns.tolist(), "survey Column names do not match"

        # check values match
        metadata_diff = self.expected_sample_output['metadata'].sort_index(axis=1).compare(formatted_sample_df['metadata'].sort_index(axis=1), align_axis=1)
        assert metadata_diff.empty, f"metadata Dataframes are not equal: {metadata_diff}"

        specimens_diff = self.expected_sample_output['specimens'].compare(formatted_sample_df['specimens'], align_axis=1)
        assert specimens_diff.empty, f"specimens Dataframes are not equal: {specimens_diff}"

        labResults_diff = self.expected_sample_output['labResults'].compare(formatted_sample_df['labResults'], align_axis=1)
        assert labResults_diff.empty, f"labResults Dataframes are not equal: {labResults_diff}"

        survey_diff = self.expected_sample_output['survey'].sort_index(axis=1).compare(formatted_sample_df['survey'].sort_index(axis=1), align_axis=1)
        assert survey_diff.empty, f"survey Dataframes are not equal: {survey_diff}"

