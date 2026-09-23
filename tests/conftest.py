import os
import sys
from unittest.mock import MagicMock, patch

# Set required environment variables before hisepy imports
os.environ['IDE_INSTANCE_GUID'] = 'test-guid-12345'
os.environ['HISE_URL'] = 'http://localhost:8080'

# Patch auth module before it's imported by other modules
sys.modules['hisepy.auth'] = MagicMock()

# Mock HiseUser and IDEInstance
mock_hise_user = MagicMock()
mock_hise_user.return_value.current_account_name = 'test-account'

mock_ide_instance = MagicMock()
mock_ide_instance.return_value.get_default_project = MagicMock(return_value='test-project')

sys.modules['hisepy.auth'].HiseUser = mock_hise_user
sys.modules['hisepy.auth'].IDEInstance = mock_ide_instance
