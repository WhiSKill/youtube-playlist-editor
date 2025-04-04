# Placeholder for auth tests 

import pytest
import pickle
import sys
from pathlib import Path
from unittest.mock import MagicMock, mock_open, call

# Import actual classes for spec'ing
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import Resource
from googleapiclient.errors import HttpError # Keep this if needed by tests directly

# Mock classes/objects from google libraries
MockCredentials = MagicMock()
MockRequest = MagicMock()
MockInstalledAppFlow = MagicMock()
MockResource = MagicMock() # Mock for the returned service object

# Define constants used in the auth module
CLIENT_SECRETS_FILE = "client_secrets.json"
TOKEN_PICKLE_FILE = "token.pickle"
API_SERVICE_NAME = "youtube"
API_VERSION = "v3"
SCOPES = ["https://www.googleapis.com/auth/youtube"]

# --- Fixtures ---

@pytest.fixture
def mock_auth_env(mocker):
    """Fixture to mock all external dependencies for auth.py."""
    # Mock pathlib Path class used within auth.py
    mock_path_class = mocker.patch("youtube_playlist_editor.auth.Path")

    # Create distinct mock objects for the resolved paths
    mock_secrets_path = MagicMock(spec=Path, name=CLIENT_SECRETS_FILE)
    mock_token_path = MagicMock(spec=Path, name=TOKEN_PICKLE_FILE)

    # Configure the base Path() call to return a mock that can be divided
    mock_base_path_instance = MagicMock(spec=Path)
    def truediv_side_effect(part):
        if part == CLIENT_SECRETS_FILE:
            return mock_secrets_path
        elif part == TOKEN_PICKLE_FILE:
            return mock_token_path
        return MagicMock(spec=Path)
    mock_base_path_instance.__truediv__.side_effect = truediv_side_effect
    mock_path_class.return_value = mock_base_path_instance # Path() returns this

    # Default existence: neither file exists
    mock_secrets_path.exists.return_value = False
    mock_token_path.exists.return_value = False

    # Mock methods on the specific path objects
    mock_secrets_path.resolve.return_value = Path(f"/fake/{CLIENT_SECRETS_FILE}")
    mock_token_path.resolve.return_value = Path(f"/fake/{TOKEN_PICKLE_FILE}")
    mock_token_path.unlink.return_value = None # For deletion after failed refresh

    # Add __str__ mocking for path objects used in function calls
    mock_secrets_path.__str__.return_value = f"/fake/{CLIENT_SECRETS_FILE}"
    mock_token_path.__str__.return_value = f"/fake/{TOKEN_PICKLE_FILE}"

    # Simplify open/pickle mocking
    # Patch open with mock_open to handle context manager
    mock_open_func = mock_open()
    mocker.patch("youtube_playlist_editor.auth.open", mock_open_func)
    # Mock pickle load/dump directly
    mock_pickle_load = mocker.patch("youtube_playlist_editor.auth.pickle.load")
    mock_pickle_dump = mocker.patch("youtube_playlist_editor.auth.pickle.dump")

    # Mock google auth/api libraries
    mock_creds_class = mocker.patch("youtube_playlist_editor.auth.Credentials", spec=Credentials)
    mock_request_class = mocker.patch("youtube_playlist_editor.auth.Request", spec=Request)
    # Directly mock the from_client_secrets_file method
    mock_flow_from_secrets = mocker.patch("youtube_playlist_editor.auth.InstalledAppFlow.from_client_secrets_file")
    mock_flow_instance = mock_flow_from_secrets.return_value
    mock_flow_instance.run_local_server = MagicMock()

    mock_build_service = MagicMock(spec=Resource)
    mock_build = mocker.patch("youtube_playlist_editor.auth.build", return_value=mock_build_service)

    # Mock system exit & click
    mock_sys_exit = mocker.patch("sys.exit", side_effect=lambda code=None: exec("raise SystemExit(code)"))
    mock_click_echo = mocker.patch("click.echo")

    # Mock logging
    mock_log_info = mocker.patch("logging.info")
    mock_log_warning = mocker.patch("logging.warning")
    mock_log_error = mocker.patch("logging.error")

    # Return mocks (update flow mock)
    return {
        "secrets_path": mock_secrets_path,
        "token_path": mock_token_path,
        "open": mock_open_func,
        "pickle_load": mock_pickle_load,
        "pickle_dump": mock_pickle_dump,
        "Credentials": mock_creds_class,
        "Request": mock_request_class,
        # Replace class mock with method mock
        "from_client_secrets_file": mock_flow_from_secrets,
        "flow_instance": mock_flow_instance,
        "build": mock_build,
        "build_service": mock_build_service,
        "sys_exit": mock_sys_exit,
        "click_echo": mock_click_echo,
        "log_info": mock_log_info,
        "log_warning": mock_log_warning,
        "log_error": mock_log_error,
    }

# Remove the explicit reset fixture - rely on pytest-mock isolation
# @pytest.fixture(autouse=True)
# def reset_mocks():
#     """Reset mocks before each test to ensure isolation."""
#     # Only reset globally defined external mocks
#     MockCredentials.reset_mock()
#     MockRequest.reset_mock()
#     # Re-add reset for the class mock itself
#     MockInstalledAppFlow.reset_mock()
#     # pytest-mock should handle resets for mocks created by mocker fixture
#     # MockInstalledAppFlow.from_client_secrets_file.reset_mock()
#     MockResource.reset_mock()


# --- Test Cases --- Adjust assertions for flow mock ---

def test_get_authenticated_service_no_secrets_file(mock_auth_env):
    """Test behavior when client_secrets.json is missing."""
    # Arrange: Default state is secrets_path.exists = False

    # Act & Assert
    from youtube_playlist_editor.auth import get_authenticated_service
    with pytest.raises(SystemExit) as exc_info:
        get_authenticated_service()
    # Assert on the caught exception code
    assert exc_info.value.code == 1

    mock_auth_env["secrets_path"].exists.assert_called_once()
    mock_auth_env["log_error"].assert_called_once()
    mock_auth_env["click_echo"].assert_called_once()
    # Assert that the mock sys.exit was called with the correct code
    mock_auth_env["sys_exit"].assert_called_once_with(1)
    mock_auth_env["build"].assert_not_called()


def test_get_authenticated_service_valid_token_exists(mock_auth_env):
    """Test behavior when a valid token.pickle exists."""
    # Arrange
    mock_auth_env["secrets_path"].exists.return_value = True
    mock_auth_env["token_path"].exists.return_value = True
    mock_valid_creds = MagicMock(spec=Credentials)
    mock_valid_creds.valid = True
    mock_valid_creds.expired = False
    mock_auth_env["pickle_load"].return_value = mock_valid_creds

    # Act
    from youtube_playlist_editor.auth import get_authenticated_service
    result = get_authenticated_service()

    # Assert
    assert result == mock_auth_env["build_service"]
    mock_auth_env["secrets_path"].exists.assert_called_once()
    mock_auth_env["token_path"].exists.assert_called_once()
    mock_auth_env["pickle_load"].assert_called_once()
    mock_auth_env["log_info"].assert_any_call(f"Loaded credentials from {mock_auth_env['token_path']}")
    mock_auth_env["from_client_secrets_file"].assert_not_called()
    mock_auth_env["pickle_dump"].assert_not_called()
    mock_auth_env["build"].assert_called_once_with(API_SERVICE_NAME, API_VERSION, credentials=mock_valid_creds)
    mock_auth_env["sys_exit"].assert_not_called()


def test_get_authenticated_service_token_load_fails(mock_auth_env):
    """Test behavior when token.pickle exists but loading fails."""
    # Arrange
    mock_auth_env["secrets_path"].exists.return_value = True
    mock_auth_env["token_path"].exists.return_value = True
    mock_auth_env["pickle_load"].side_effect = EOFError("Simulated pickle error")
    mock_new_creds = MagicMock(spec=Credentials)
    mock_auth_env["flow_instance"].run_local_server.return_value = mock_new_creds

    # Act
    from youtube_playlist_editor.auth import get_authenticated_service
    result = get_authenticated_service()

    # Assert
    assert result == mock_auth_env["build_service"]
    mock_auth_env["token_path"].exists.assert_called_once()
    mock_auth_env["pickle_load"].assert_called_once()
    mock_auth_env["log_warning"].assert_any_call(f"Could not load token file ({mock_auth_env['token_path']}): Simulated pickle error. Re-authenticating.")
    mock_auth_env["from_client_secrets_file"].assert_called_once_with(
        str(mock_auth_env["secrets_path"]), SCOPES
    )
    mock_auth_env["flow_instance"].run_local_server.assert_called_once_with(port=0)
    # Check saving the new token - assert dump called with creds and the handle from mock_open
    mock_auth_env["pickle_dump"].assert_called_once_with(mock_new_creds, mock_auth_env["open"].return_value)
    mock_auth_env["build"].assert_called_once_with(API_SERVICE_NAME, API_VERSION, credentials=mock_new_creds)
    mock_auth_env["sys_exit"].assert_not_called()


def test_get_authenticated_service_expired_token_refresh_success(mock_auth_env):
    """Test behavior when token is expired and refresh succeeds."""
    # Arrange
    mock_auth_env["secrets_path"].exists.return_value = True
    mock_auth_env["token_path"].exists.return_value = True
    mock_expired_creds = MagicMock(spec=Credentials)
    mock_expired_creds.valid = False
    mock_expired_creds.expired = True
    mock_expired_creds.refresh_token = "fake_refresh_token"
    mock_expired_creds.refresh.return_value = None
    mock_auth_env["pickle_load"].return_value = mock_expired_creds

    # Act
    from youtube_playlist_editor.auth import get_authenticated_service
    result = get_authenticated_service()

    # Assert
    assert result == mock_auth_env["build_service"]
    mock_auth_env["pickle_load"].assert_called_once()
    mock_expired_creds.refresh.assert_called_once_with(mock_auth_env["Request"].return_value)
    mock_auth_env["log_info"].assert_any_call("Credentials expired, refreshing...")
    # Check saving refreshed token - assert dump called with creds and handle
    mock_auth_env["pickle_dump"].assert_called_once_with(mock_expired_creds, mock_auth_env["open"].return_value)
    mock_auth_env["build"].assert_called_once_with(API_SERVICE_NAME, API_VERSION, credentials=mock_expired_creds)
    mock_auth_env["from_client_secrets_file"].assert_not_called()
    mock_auth_env["sys_exit"].assert_not_called()


def test_get_authenticated_service_expired_token_refresh_fails(mock_auth_env):
    """Test behavior when token is expired and refresh fails, triggers flow."""
    # Arrange
    mock_auth_env["secrets_path"].exists.return_value = True
    mock_auth_env["token_path"].exists.return_value = True # Token exists initially
    mock_expired_creds = MagicMock(spec=Credentials)
    mock_expired_creds.valid = False
    mock_expired_creds.expired = True
    mock_expired_creds.refresh_token = "fake_refresh_token"
    refresh_exception = Exception("Refresh failed")
    mock_expired_creds.refresh.side_effect = refresh_exception
    mock_auth_env["pickle_load"].return_value = mock_expired_creds
    mock_new_creds = MagicMock(spec=Credentials)
    mock_auth_env["flow_instance"].run_local_server.return_value = mock_new_creds

    # Act
    from youtube_playlist_editor.auth import get_authenticated_service
    result = get_authenticated_service()

    # Assert
    assert result == mock_auth_env["build_service"]
    mock_auth_env["pickle_load"].assert_called_once()
    mock_expired_creds.refresh.assert_called_once_with(mock_auth_env["Request"].return_value)
    mock_auth_env["log_warning"].assert_any_call(f"Failed to refresh token: {refresh_exception}. Re-authenticating by removing token.")
    # Check token deletion was attempted
    mock_auth_env["token_path"].exists.assert_called_with() # Called twice: once initial, once before unlink
    assert mock_auth_env["token_path"].exists.call_count >= 2
    mock_auth_env["token_path"].unlink.assert_called_once()
    mock_auth_env["log_info"].assert_any_call(f"Removed invalid token file: {mock_auth_env['token_path']}")
    # Check flow ran - use the new mock reference
    mock_auth_env["from_client_secrets_file"].assert_called_once_with(
        str(mock_auth_env["secrets_path"]), SCOPES
    )
    mock_auth_env["flow_instance"].run_local_server.assert_called_once_with(port=0)
    # Check saving new token - assert dump called with creds and handle
    mock_auth_env["pickle_dump"].assert_called_once_with(mock_new_creds, mock_auth_env["open"].return_value)
    mock_auth_env["build"].assert_called_once_with(API_SERVICE_NAME, API_VERSION, credentials=mock_new_creds)
    mock_auth_env["sys_exit"].assert_not_called()


def test_get_authenticated_service_no_token_file_flow_success(mock_auth_env):
    """Test the full OAuth flow when no token file exists."""
    # Arrange
    mock_auth_env["secrets_path"].exists.return_value = True
    mock_auth_env["token_path"].exists.return_value = False # Token does NOT exist
    mock_new_creds = MagicMock(spec=Credentials)
    mock_auth_env["flow_instance"].run_local_server.return_value = mock_new_creds

    # Act
    from youtube_playlist_editor.auth import get_authenticated_service
    result = get_authenticated_service()

    # Assert
    assert result == mock_auth_env["build_service"]
    mock_auth_env["token_path"].exists.assert_called_once()
    mock_auth_env["pickle_load"].assert_not_called()
    mock_auth_env["log_info"].assert_any_call("No valid credentials available, starting authentication flow.")
    mock_auth_env["from_client_secrets_file"].assert_called_once_with(
        str(mock_auth_env["secrets_path"]), SCOPES
    )
    mock_auth_env["flow_instance"].run_local_server.assert_called_once_with(port=0)
    # Check saving the new token - assert dump called with creds and handle
    mock_auth_env["pickle_dump"].assert_called_once_with(mock_new_creds, mock_auth_env["open"].return_value)
    mock_auth_env["log_info"].assert_any_call(f"New credentials saved to {mock_auth_env['token_path']}")
    mock_auth_env["build"].assert_called_once_with(API_SERVICE_NAME, API_VERSION, credentials=mock_new_creds)
    mock_auth_env["sys_exit"].assert_not_called()


def test_get_authenticated_service_flow_fails(mock_auth_env):
    """Test behavior when the OAuth flow itself fails."""
    # Arrange
    mock_auth_env["secrets_path"].exists.return_value = True
    mock_auth_env["token_path"].exists.return_value = False
    flow_exception = Exception("Flow failed")
    mock_auth_env["flow_instance"].run_local_server.side_effect = flow_exception

    # Act
    from youtube_playlist_editor.auth import get_authenticated_service
    result = get_authenticated_service()

    # Assert
    assert result is None
    mock_auth_env["from_client_secrets_file"].assert_called_once()
    mock_auth_env["flow_instance"].run_local_server.assert_called_once()
    mock_auth_env["log_error"].assert_any_call(f"Authentication flow failed: {flow_exception}", exc_info=True)
    mock_auth_env["click_echo"].assert_any_call(f"Error during authentication: {flow_exception}", err=True)
    mock_auth_env["pickle_dump"].assert_not_called()
    mock_auth_env["build"].assert_not_called()
    mock_auth_env["sys_exit"].assert_not_called()


def test_get_authenticated_service_token_save_fails(mock_auth_env):
    """Test behavior when saving the new token fails (non-critical)."""
    # Arrange
    mock_auth_env["secrets_path"].exists.return_value = True
    mock_auth_env["token_path"].exists.return_value = False
    mock_new_creds = MagicMock(spec=Credentials)
    mock_auth_env["flow_instance"].run_local_server.return_value = mock_new_creds
    save_exception = OSError("Cannot write token")
    mock_auth_env["pickle_dump"].side_effect = save_exception

    # Act
    from youtube_playlist_editor.auth import get_authenticated_service
    result = get_authenticated_service()

    # Assert
    assert result == mock_auth_env["build_service"]
    mock_auth_env["flow_instance"].run_local_server.assert_called_once()
    mock_auth_env["pickle_dump"].assert_called_once()
    mock_auth_env["log_error"].assert_any_call(f"Failed to save new token to {mock_auth_env['token_path']}: {save_exception}")
    mock_auth_env["click_echo"].assert_any_call(f"Warning: Could not save new credentials to {mock_auth_env['token_path']}: {save_exception}", err=True)
    mock_auth_env["build"].assert_called_once_with(API_SERVICE_NAME, API_VERSION, credentials=mock_new_creds)


def test_get_authenticated_service_build_fails(mock_auth_env):
    # Arrange
    mock_auth_env["secrets_path"].exists.return_value = True
    mock_auth_env["token_path"].exists.return_value = True
    mock_valid_creds = MagicMock(spec=Credentials)
    mock_valid_creds.valid = True
    mock_auth_env["pickle_load"].return_value = mock_valid_creds
    build_exception = HttpError(MagicMock(status=500), b"Build failed")
    mock_auth_env["build"].side_effect = build_exception

    # Act
    from youtube_playlist_editor.auth import get_authenticated_service
    result = get_authenticated_service()

    # Assert
    assert result is None
    mock_auth_env["pickle_load"].assert_called_once()
    mock_auth_env["build"].assert_called_once_with(API_SERVICE_NAME, API_VERSION, credentials=mock_valid_creds)
    mock_auth_env["log_error"].assert_any_call(f"Failed to build YouTube service: {build_exception}")
    mock_auth_env["click_echo"].assert_any_call(f"Error building YouTube service: {build_exception}", err=True) 