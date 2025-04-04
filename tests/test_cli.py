# Placeholder for cli tests 

import pytest
from click.testing import CliRunner
from unittest.mock import MagicMock, mock_open, call, patch
from pathlib import Path

# Import the CLI application
from youtube_playlist_editor import cli
# Import modules containing functions we need to mock *references* to
from youtube_playlist_editor import auth, api, utils

# --- Fixtures ---

@pytest.fixture
def runner():
    """Provides a CliRunner instance."""
    return CliRunner()

# --- Test Cases ---

# Use patch decorators to mock functions *before* the test runs
@patch("youtube_playlist_editor.cli.get_authenticated_service")
@patch("youtube_playlist_editor.cli.verify_playlist_exists")
@patch("youtube_playlist_editor.cli.get_existing_playlist_video_ids")
@patch("youtube_playlist_editor.cli.add_video_to_playlist")
@patch("youtube_playlist_editor.cli.extract_video_id")
@patch("youtube_playlist_editor.cli.Path") # Mock Path used by click.Path
@patch("builtins.open") # Mock open used by cli.add to read file
@patch("click.echo") # Mock echo for checking output
def test_add_command_success(
    mock_echo,
    mock_builtin_open,
    mock_cli_path,
    mock_extract,
    mock_add,
    mock_get_existing,
    mock_verify,
    mock_get_auth,
    runner,
    tmp_path
):
    """Test the happy path: adding videos successfully."""
    # Arrange
    playlist_id = "PL_success"
    input_content = "https://youtu.be/vid1\nhttps://www.youtube.com/watch?v=vid2"
    input_file_path_obj = tmp_path / "videos.txt"
    input_file_path_obj.write_text(input_content)
    input_file_str = str(input_file_path_obj)

    # Configure mocks passed as arguments by decorators
    mock_youtube_service = MagicMock()
    mock_get_auth.return_value = mock_youtube_service
    mock_verify.return_value = True
    mock_get_existing.return_value = set()
    mock_add.return_value = True
    mock_extract.side_effect = ["vid1", "vid2"]

    # Configure Path mock for click.Path check
    mock_cli_path.return_value.exists.return_value = True
    mock_cli_path.return_value.is_file.return_value = True
    mock_cli_path.return_value.is_dir.return_value = False
    # Configure builtin open mock for reading the file
    mock_builtin_open.return_value = mock_open(read_data=input_content).return_value

    # Act
    result = runner.invoke(cli.cli, ['add', '-f', input_file_str, '-p', playlist_id])

    # Assert
    assert result.exit_code == 0, f"CLI failed with output: {result.output}\nException: {result.exception}"
    mock_get_auth.assert_called_once()
    mock_verify.assert_called_once_with(mock_youtube_service, playlist_id)
    mock_get_existing.assert_called_once_with(mock_youtube_service, playlist_id)
    mock_extract.assert_has_calls([
        call("https://youtu.be/vid1"),
        call("https://www.youtube.com/watch?v=vid2")
    ])
    mock_add.assert_has_calls([
        call(mock_youtube_service, playlist_id, "vid1"),
        call(mock_youtube_service, playlist_id, "vid2")
    ])
    assert mock_add.call_count == 2
    mock_echo.assert_has_calls([
        call("\n--- Summary ---"),
        call("Successfully added: 2 videos."),
        call("Skipped (invalid URL/ID): 0 lines."),
        call("Skipped (duplicate): 0 videos."),
        call("Errors during addition: 0 videos.")
    ], any_order=False)

@patch("youtube_playlist_editor.cli.get_authenticated_service")
@patch("youtube_playlist_editor.cli.verify_playlist_exists") # Still need to patch downstream
@patch("youtube_playlist_editor.cli.Path")
@patch("click.echo")
def test_add_command_authentication_fails(
    mock_echo,
    mock_cli_path,
    mock_verify,
    mock_get_auth,
    runner,
    tmp_path
):
    """Test behavior when authentication fails."""
    # Arrange
    playlist_id = "PL_auth_fail"
    input_file_path_obj = tmp_path / "videos.txt"
    input_file_path_obj.touch()
    input_file_str = str(input_file_path_obj)

    mock_get_auth.return_value = None # Simulate auth failure
    # Configure Path mock for click.Path check
    mock_cli_path.return_value.exists.return_value = True
    mock_cli_path.return_value.is_file.return_value = True
    mock_cli_path.return_value.is_dir.return_value = False

    # Act
    result = runner.invoke(cli.cli, ['add', '-f', input_file_str, '-p', playlist_id])

    # Assert
    assert result.exit_code == 1, f"CLI should exit with 1 on auth fail. Output: {result.output}\nException: {result.exception}"
    mock_get_auth.assert_called_once()
    mock_echo.assert_any_call("Failed to authenticate with YouTube API. Exiting.", err=True)
    mock_verify.assert_not_called()

@patch("youtube_playlist_editor.cli.get_authenticated_service")
@patch("youtube_playlist_editor.cli.verify_playlist_exists")
@patch("youtube_playlist_editor.cli.get_existing_playlist_video_ids") # Patch downstream
@patch("youtube_playlist_editor.cli.Path")
def test_add_command_playlist_verification_fails(
    mock_cli_path,
    mock_get_existing,
    mock_verify,
    mock_get_auth,
    runner,
    tmp_path
):
    """Test behavior when playlist verification fails."""
    # Arrange
    playlist_id = "PL_verify_fail"
    input_file_path_obj = tmp_path / "videos.txt"
    input_file_path_obj.touch()
    input_file_str = str(input_file_path_obj)

    mock_youtube_service = MagicMock()
    mock_get_auth.return_value = mock_youtube_service
    mock_verify.return_value = False # Simulate verify failure
    # Configure Path mock for click.Path check
    mock_cli_path.return_value.exists.return_value = True
    mock_cli_path.return_value.is_file.return_value = True
    mock_cli_path.return_value.is_dir.return_value = False

    # Act
    result = runner.invoke(cli.cli, ['add', '-f', input_file_str, '-p', playlist_id])

    # Assert
    assert result.exit_code == 1, f"CLI should exit with 1 on verify fail. Output: {result.output}\nException: {result.exception}"
    mock_get_auth.assert_called_once()
    mock_verify.assert_called_once_with(mock_youtube_service, playlist_id)
    mock_get_existing.assert_not_called()

@patch("youtube_playlist_editor.cli.get_authenticated_service")
@patch("youtube_playlist_editor.cli.verify_playlist_exists")
@patch("youtube_playlist_editor.cli.get_existing_playlist_video_ids")
@patch("youtube_playlist_editor.cli.add_video_to_playlist")
@patch("youtube_playlist_editor.cli.extract_video_id")
@patch("youtube_playlist_editor.cli.Path")
@patch("builtins.open")
@patch("click.echo")
@patch("logging.info") # Mock logging to check duplicate message
def test_add_command_handles_duplicates(
    mock_log_info,
    mock_echo,
    mock_builtin_open,
    mock_cli_path,
    mock_extract,
    mock_add,
    mock_get_existing,
    mock_verify,
    mock_get_auth,
    runner,
    tmp_path
):
    """Test skipping videos already present in the playlist or file."""
    # Arrange
    playlist_id = "PL_duplicates"
    input_content = (
        "https://youtu.be/vid1\n"  # New
        "https://youtu.be/vid2\n"  # Existing in playlist
        "https://youtu.be/vid1\n"  # Duplicate within file
        "https://youtu.be/vid3"   # New
    )
    input_file_path_obj = tmp_path / "videos.txt"
    input_file_path_obj.write_text(input_content)
    input_file_str = str(input_file_path_obj)

    mock_youtube_service = MagicMock()
    mock_get_auth.return_value = mock_youtube_service
    mock_verify.return_value = True
    mock_get_existing.return_value = {"vid2"} # vid2 already exists
    mock_add.return_value = True
    mock_extract.side_effect = ["vid1", "vid2", "vid1", "vid3"]
    mock_cli_path.return_value.exists.return_value = True
    mock_cli_path.return_value.is_file.return_value = True
    mock_cli_path.return_value.is_dir.return_value = False
    mock_builtin_open.return_value = mock_open(read_data=input_content).return_value

    # Act
    result = runner.invoke(cli.cli, ['add', '-f', input_file_str, '-p', playlist_id])

    # Assert
    assert result.exit_code == 0, f"CLI failed with output: {result.output}\nException: {result.exception}"
    mock_get_existing.assert_called_once()
    mock_add.assert_has_calls([
        call(mock_youtube_service, playlist_id, "vid1"),
        call(mock_youtube_service, playlist_id, "vid3")
    ])
    assert mock_add.call_count == 2
    mock_log_info.assert_any_call("Skipping duplicate video ID: vid2 (already in playlist)")
    mock_log_info.assert_any_call("Skipping duplicate video ID: vid1 (already in playlist)")
    mock_echo.assert_has_calls([
        call("\n--- Summary ---"),
        call("Successfully added: 2 videos."),
        call("Skipped (invalid URL/ID): 0 lines."),
        call("Skipped (duplicate): 2 videos."),
        call("Errors during addition: 0 videos.")
    ], any_order=False)

@patch("youtube_playlist_editor.cli.get_authenticated_service")
@patch("youtube_playlist_editor.cli.verify_playlist_exists")
@patch("youtube_playlist_editor.cli.get_existing_playlist_video_ids")
@patch("youtube_playlist_editor.cli.add_video_to_playlist")
@patch("youtube_playlist_editor.cli.extract_video_id")
@patch("youtube_playlist_editor.cli.Path")
@patch("builtins.open")
@patch("click.echo")
def test_add_command_handles_invalid_urls(
    mock_echo,
    mock_builtin_open,
    mock_cli_path,
    mock_extract,
    mock_add,
    mock_get_existing,
    mock_verify,
    mock_get_auth,
    runner,
    tmp_path
):
    """Test skipping lines with invalid URLs."""
    # Arrange
    playlist_id = "PL_invalid"
    input_content = (
        "https://youtu.be/vid1\n"  # Valid
        "not a url\n"             # Invalid
        "https://example.com\n"     # Valid URL, but not youtube
        "\n"                     # Empty line
        "#https://youtu.be/vid2" # Comment
    )
    input_file_path_obj = tmp_path / "videos.txt"
    input_file_path_obj.write_text(input_content)
    input_file_str = str(input_file_path_obj)

    mock_youtube_service = MagicMock()
    mock_get_auth.return_value = mock_youtube_service
    mock_verify.return_value = True
    mock_get_existing.return_value = set()
    mock_add.return_value = True
    mock_extract.side_effect = ["vid1", None, None]
    mock_cli_path.return_value.exists.return_value = True
    mock_cli_path.return_value.is_file.return_value = True
    mock_cli_path.return_value.is_dir.return_value = False
    mock_builtin_open.return_value = mock_open(read_data=input_content).return_value

    # Act
    result = runner.invoke(cli.cli, ['add', '-f', input_file_str, '-p', playlist_id])

    # Assert
    assert result.exit_code == 0, f"CLI failed with output: {result.output}\nException: {result.exception}"
    mock_add.assert_called_once_with(mock_youtube_service, playlist_id, "vid1")
    mock_echo.assert_any_call("Warning: Could not extract video ID from line 2: 'not a url'", err=True)
    mock_echo.assert_any_call("Warning: Could not extract video ID from line 3: 'https://example.com'", err=True)
    mock_echo.assert_has_calls([
        call("\n--- Summary ---"),
        call("Successfully added: 1 videos."),
        call("Skipped (invalid URL/ID): 2 lines."),
        call("Skipped (duplicate): 0 videos."),
        call("Errors during addition: 0 videos.")
    ], any_order=False)

@patch("youtube_playlist_editor.cli.get_authenticated_service")
@patch("youtube_playlist_editor.cli.verify_playlist_exists")
@patch("youtube_playlist_editor.cli.get_existing_playlist_video_ids")
@patch("youtube_playlist_editor.cli.add_video_to_playlist")
@patch("youtube_playlist_editor.cli.extract_video_id")
@patch("youtube_playlist_editor.cli.Path")
@patch("builtins.open")
@patch("click.echo")
def test_add_command_handles_add_video_errors(
    mock_echo,
    mock_builtin_open,
    mock_cli_path,
    mock_extract,
    mock_add,
    mock_get_existing,
    mock_verify,
    mock_get_auth,
    runner,
    tmp_path
):
    """Test counting errors when add_video_to_playlist returns False."""
    # Arrange
    playlist_id = "PL_add_fail"
    input_content = "https://youtu.be/vid1\nhttps://youtu.be/vid2"
    input_file_path_obj = tmp_path / "videos.txt"
    input_file_path_obj.write_text(input_content)
    input_file_str = str(input_file_path_obj)

    mock_youtube_service = MagicMock()
    mock_get_auth.return_value = mock_youtube_service
    mock_verify.return_value = True
    mock_get_existing.return_value = set()
    mock_add.side_effect = [True, False] # Simulate first add succeeds, second fails
    mock_extract.side_effect = ["vid1", "vid2"]
    mock_cli_path.return_value.exists.return_value = True
    mock_cli_path.return_value.is_file.return_value = True
    mock_cli_path.return_value.is_dir.return_value = False
    mock_builtin_open.return_value = mock_open(read_data=input_content).return_value

    # Act
    result = runner.invoke(cli.cli, ['add', '-f', input_file_str, '-p', playlist_id])

    # Assert
    assert result.exit_code == 0, f"CLI failed with output: {result.output}\nException: {result.exception}"
    mock_add.assert_has_calls([
        call(mock_youtube_service, playlist_id, "vid1"),
        call(mock_youtube_service, playlist_id, "vid2")
    ])
    mock_echo.assert_has_calls([
        call("\n--- Summary ---"),
        call("Successfully added: 1 videos."),
        call("Skipped (invalid URL/ID): 0 lines."),
        call("Skipped (duplicate): 0 videos."),
        call("Errors during addition: 1 videos.")
    ], any_order=False)

@patch("youtube_playlist_editor.cli.get_authenticated_service") # Patch downstream
@patch("youtube_playlist_editor.cli.Path")
def test_add_command_file_not_found(
    mock_cli_path,
    mock_get_auth,
    runner
):
    """Test behavior when the input file does not exist."""
    # Arrange
    playlist_id = "PL_file_fail"
    non_existent_file = "non_existent_videos.txt"

    # Configure Path mock for click.Path check
    mock_cli_path.return_value.exists.return_value = False
    mock_cli_path.return_value.is_file.return_value = False
    mock_cli_path.return_value.is_dir.return_value = False

    # Act
    result = runner.invoke(cli.cli, ['add', '-f', non_existent_file, '-p', playlist_id])

    # Assert
    assert result.exit_code == 2, f"Click should exit with 2 on invalid param. Output: {result.output}\nException: {result.exception}"
    assert "File" in result.output and "does not exist" in result.output
    mock_get_auth.assert_not_called()

@patch("youtube_playlist_editor.cli.get_authenticated_service")
@patch("youtube_playlist_editor.cli.verify_playlist_exists")
@patch("youtube_playlist_editor.cli.get_existing_playlist_video_ids")
@patch("youtube_playlist_editor.cli.Path")
@patch("builtins.open")
@patch("logging.error") # Mock logging
@patch("click.echo")
def test_add_command_file_processing_error(
    mock_echo,
    mock_log_error,
    mock_builtin_open,
    mock_cli_path,
    mock_get_existing,
    mock_verify,
    mock_get_auth,
    runner,
    tmp_path
):
    """Test handling of unexpected errors during file reading."""
    # Arrange
    playlist_id = "PL_read_fail"
    input_file_path_obj = tmp_path / "videos.txt"
    input_file_path_obj.write_text("https://youtu.be/vid1")
    input_file_str = str(input_file_path_obj)

    mock_youtube_service = MagicMock()
    mock_get_auth.return_value = mock_youtube_service
    mock_verify.return_value = True
    mock_get_existing.return_value = set()
    mock_cli_path.return_value.exists.return_value = True
    mock_cli_path.return_value.is_file.return_value = True
    mock_cli_path.return_value.is_dir.return_value = False
    # Mock open to raise error during iteration
    read_error = IOError("Disk read error")
    mock_builtin_open.return_value.__enter__.return_value.__iter__.side_effect = read_error

    # Act
    result = runner.invoke(cli.cli, ['add', '-f', input_file_str, '-p', playlist_id])

    # Assert
    assert result.exit_code == 1, f"CLI should exit with 1 on file read error. Output: {result.output}\nException: {result.exception}"
    mock_log_error.assert_any_call(f"An error occurred processing the file '{input_file_str}': {read_error}", exc_info=True)
    mock_echo.assert_any_call(f"An unexpected error occurred processing the file: {read_error}", err=True)

# This is the end of the file. Ensure no extra lines follow. 