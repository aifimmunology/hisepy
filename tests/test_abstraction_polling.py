import sys
import os
from unittest.mock import MagicMock, patch, mock_open

os.environ['IDE_INSTANCE_GUID'] = 'test-guid-12345'
os.environ['HISE_URL'] = 'http://localhost:8080'

mock_auth = MagicMock()
mock_auth.get_bearer_token_header = MagicMock(return_value={})
mock_auth.ide_instance_guid = MagicMock(return_value='test-guid')
sys.modules['hisepy.auth'] = mock_auth

# Mock the logging module so @with_default_logging is a no-op, avoiding
# JSON serialization failures on MagicMock values during decorator teardown.
mock_logging = MagicMock()
mock_logging.with_default_logging = lambda f: f
mock_logging.logger = MagicMock()
sys.modules['hisepy.logging'] = mock_logging

from hisepy.abstraction import (
    _stage_message,
    _fetch_abstraction_status,
    _poll_abstraction_status,
    get_abstraction_status,
)
from hisepy.abstraction_result import AbstractionResult


def test_stage_message_known():
    assert _stage_message("saving") == "[HISE] Saving abstraction..."
    assert _stage_message("polling_build") == "[HISE] Building Docker image (this may take ~5 minutes)..."
    assert _stage_message("deployed") == "[HISE] Abstraction deployed successfully."


def test_stage_message_unknown():
    assert _stage_message("mystery_stage") == "[HISE] Status: mystery_stage"


@patch('hisepy.abstraction.requests.get')
@patch('hisepy.abstraction.parse_hise_response')
def test_fetch_abstraction_status(mock_parse, mock_get):
    mock_parse.return_value = {'stage': 'polling_build', 'abstractionId': None}
    result = _fetch_abstraction_status('wf-abc-123')
    assert result['stage'] == 'polling_build'
    mock_get.assert_called_once()


@patch('hisepy.abstraction.time.sleep')
@patch('hisepy.abstraction._fetch_abstraction_status')
def test_poll_abstraction_status_deployed(mock_fetch, mock_sleep):
    mock_fetch.side_effect = [
        {'stage': 'saving'},
        {'stage': 'polling_build'},
        {'stage': 'deployed', 'abstractionId': 'abs-123', 'appUrl': 'https://example.com/app/'},
    ]
    result = _poll_abstraction_status('wf-xyz', poll_interval=0)
    assert isinstance(result, AbstractionResult)
    assert result.status == 'deployed'
    assert result.abstraction_id == 'abs-123'
    assert result.app_url == 'https://example.com/app/'
    assert mock_sleep.call_count == 2  # slept before the 2nd and 3rd polls


@patch('hisepy.abstraction.time.sleep')
@patch('hisepy.abstraction._fetch_abstraction_status')
def test_poll_abstraction_status_failed(mock_fetch, mock_sleep):
    mock_fetch.side_effect = [
        {'stage': 'saving'},
        {'stage': 'failed', 'error': 'build timed out'},
    ]
    result = _poll_abstraction_status('wf-fail', poll_interval=0)
    assert result.status == 'failed'
    assert result.error == 'build timed out'
    assert result.abstraction_id is None


@patch('hisepy.abstraction._fetch_abstraction_status')
def test_get_abstraction_status_one_shot(mock_fetch):
    mock_fetch.return_value = {
        'stage': 'deploying',
        'abstractionId': 'abs-789',
    }
    result = get_abstraction_status('wf-oneshot')
    assert result.status == 'deploying'
    assert result.abstraction_id == 'abs-789'
    assert result.app_url is None
    mock_fetch.assert_called_once_with('wf-oneshot')


@patch('hisepy.abstraction._poll_abstraction_status')
@patch('hisepy.abstraction.parse_hise_response')
@patch('hisepy.abstraction.requests.post')
@patch('hisepy.abstraction.validate_files')
@patch('hisepy.abstraction.validate_hero_image', return_value='thumb.png')
@patch('hisepy.abstraction.validate_data_contract_id')
@patch('hisepy.abstraction.project_shortname_to_guid', return_value=None)
@patch('hisepy.abstraction.enumerate_all_files', return_value=['app.py'])
@patch('hisepy.abstraction.get_build_template_and_params', return_value=({'id': 'vbt-1'}, {}))
@patch('hisepy.abstraction.create_visualization_tarball', return_value='tarball.tar.gz')
@patch('builtins.open', new_callable=mock_open, read_data=b'fakepng')
def test_save_abstraction_wait_false(
    mock_file, mock_tarball, mock_vbt, mock_enum, mock_proj, mock_contract,
    mock_hero, mock_validate, mock_post, mock_parse, mock_poll
):
    from hisepy.abstraction import save_abstraction
    from hisepy.abstraction_result import AbstractionResult

    # Two parse_hise_response calls: image upload + workflow POST
    mock_parse.side_effect = [
        {'url': 'https://example.com/img.png'},
        {'WorkflowId': 'wf-abc-123'},
    ]

    result = save_abstraction(
        application_files=['app.py'],
        application_dirs=[],
        title='Test App Title',
        data_contract_id='f2f03ecb-5a1d-4995-8db9-56bd18a36aba',
        png_image='thumb.png',
        wait=False,
    )

    assert isinstance(result, AbstractionResult)
    assert result.status == 'submitted'
    assert result.workflow_id == 'wf-abc-123'
    mock_poll.assert_not_called()
