import pytest
import sys
import os
from unittest.mock import MagicMock

# Set IDE environment before any hisepy imports
os.environ['IDE_INSTANCE_GUID'] = 'test-guid-12345'
os.environ['HISE_URL'] = 'http://localhost:8080'

# Mock auth at the sys.modules level before any hisepy imports occur
mock_auth = MagicMock()
mock_auth.HiseUser = MagicMock(return_value=MagicMock(current_account_name='test'))
mock_auth.IDEInstance = MagicMock(return_value=MagicMock(get_default_project=MagicMock(return_value='test')))
mock_auth.get_bearer_token_header = MagicMock(return_value={})
mock_auth.ide_instance_guid = MagicMock(return_value='test-guid')
sys.modules['hisepy.auth'] = mock_auth

from hisepy.abstraction_result import AbstractionResult


def test_abstraction_result_required_fields():
    result = AbstractionResult(workflow_id="wf-123", status="submitted")
    assert result.workflow_id == "wf-123"
    assert result.status == "submitted"
    assert result.abstraction_id is None
    assert result.app_url is None
    assert result.error is None


def test_abstraction_result_all_fields():
    result = AbstractionResult(
        workflow_id="wf-123",
        status="deployed",
        abstraction_id="abs-456",
        app_url="https://example.com/app/",
        error=None,
    )
    assert result.abstraction_id == "abs-456"
    assert result.app_url == "https://example.com/app/"


def test_abstraction_result_with_error():
    result = AbstractionResult(
        workflow_id="wf-789",
        status="failed",
        error="build failed at step 3",
    )
    assert result.status == "failed"
    assert result.error == "build failed at step 3"


def test_import_from_hisepy():
    from hisepy import AbstractionResult, get_abstraction_status  # noqa: F401
    assert AbstractionResult is not None
    assert get_abstraction_status is not None
