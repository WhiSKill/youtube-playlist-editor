# Placeholder for api tests 

import pytest
import time
from unittest.mock import MagicMock, call
from googleapiclient.errors import HttpError

# Import functions to test
from youtube_playlist_editor.api import (
    get_existing_playlist_video_ids,
    add_video_to_playlist,
    verify_playlist_exists,
    MAX_RETRIES,
    INITIAL_BACKOFF
)

# --- Mocks and Fixtures ---

@pytest.fixture
def mock_youtube_resource(mocker):
    """Fixture to create a mock googleapiclient.discovery.Resource object."""
    mock_resource = MagicMock()

    # Mock the chainable methods and execute()
    mock_playlistItems = MagicMock()
    mock_resource.playlistItems.return_value = mock_playlistItems
    mock_playlistItems_list = MagicMock()
    mock_playlistItems.list.return_value = mock_playlistItems_list
    mock_playlistItems_list.execute = MagicMock()

    mock_playlistItems_insert = MagicMock()
    mock_playlistItems.insert.return_value = mock_playlistItems_insert
    mock_playlistItems_insert.execute = MagicMock()

    mock_playlists = MagicMock()
    mock_resource.playlists.return_value = mock_playlists
    mock_playlists_list = MagicMock()
    mock_playlists.list.return_value = mock_playlists_list
    mock_playlists_list.execute = MagicMock()

    # Mock time.sleep used in retry logic
    mock_sleep = mocker.patch("time.sleep")

    # Mock logging and click
    mock_log_info = mocker.patch("logging.info")
    mock_log_warning = mocker.patch("logging.warning")
    mock_log_error = mocker.patch("logging.error")
    mock_click_echo = mocker.patch("click.echo")

    # Return the main resource mock and mocks for chained methods/functions
    return {
        "youtube": mock_resource,
        "playlistItems_list_execute": mock_playlistItems_list.execute,
        "playlistItems_insert_execute": mock_playlistItems_insert.execute,
        "playlists_list_execute": mock_playlists_list.execute,
        "sleep": mock_sleep,
        "log_info": mock_log_info,
        "log_warning": mock_log_warning,
        "log_error": mock_log_error,
        "click_echo": mock_click_echo
    }


def create_http_error(status_code: int, content: bytes = b'') -> HttpError:
    """Helper to create HttpError instances for testing."""
    mock_resp = MagicMock()
    mock_resp.status = status_code
    # The HttpError constructor expects response, content, and uri
    return HttpError(resp=mock_resp, content=content, uri='http://example.com')

# --- Tests for verify_playlist_exists ---

def test_verify_playlist_exists_success(mock_youtube_resource):
    """Test verify_playlist_exists successfully finds the playlist."""
    mock_youtube_resource["playlists_list_execute"].return_value = {"items": [{"id": "PL_test"}]}
    playlist_id = "PL_test"

    result = verify_playlist_exists(mock_youtube_resource["youtube"], playlist_id)

    assert result is True
    mock_youtube_resource["youtube"].playlists().list.assert_called_once_with(
        part="id", id=playlist_id, maxResults=1
    )
    mock_youtube_resource["playlists_list_execute"].assert_called_once()
    mock_youtube_resource["log_info"].assert_any_call(f"Playlist ID '{playlist_id}' is valid and accessible.")
    mock_youtube_resource["click_echo"].assert_not_called()

def test_verify_playlist_exists_not_found_empty_items(mock_youtube_resource):
    """Test verify_playlist_exists when API returns empty items list."""
    mock_youtube_resource["playlists_list_execute"].return_value = {"items": []}
    playlist_id = "PL_not_exist"

    result = verify_playlist_exists(mock_youtube_resource["youtube"], playlist_id)

    assert result is False
    mock_youtube_resource["log_error"].assert_any_call(f"Playlist ID '{playlist_id}' not found or user does not have access.")
    mock_youtube_resource["click_echo"].assert_any_call(f"Error: Playlist ID '{playlist_id}' not found or you do not have access to it.", err=True)

def test_verify_playlist_exists_http_404(mock_youtube_resource):
    """Test verify_playlist_exists handles 404 HttpError."""
    error_404 = create_http_error(404)
    mock_youtube_resource["playlists_list_execute"].side_effect = error_404
    playlist_id = "PL_404"

    result = verify_playlist_exists(mock_youtube_resource["youtube"], playlist_id)

    assert result is False
    mock_youtube_resource["log_error"].assert_any_call(f"API Error verifying playlist ID '{playlist_id}': {error_404}")
    mock_youtube_resource["click_echo"].assert_any_call(f"Error: Playlist ID '{playlist_id}' was not found. Please check the ID.", err=True)

def test_verify_playlist_exists_http_403(mock_youtube_resource):
    """Test verify_playlist_exists handles 403 HttpError."""
    error_403 = create_http_error(403)
    mock_youtube_resource["playlists_list_execute"].side_effect = error_403
    playlist_id = "PL_403"

    result = verify_playlist_exists(mock_youtube_resource["youtube"], playlist_id)

    assert result is False
    mock_youtube_resource["log_error"].assert_any_call(f"API Error verifying playlist ID '{playlist_id}': {error_403}")
    mock_youtube_resource["click_echo"].assert_any_call(f"Error: Permission denied when trying to access playlist '{playlist_id}'. Check API key/OAuth scopes or playlist permissions.", err=True)

def test_verify_playlist_exists_other_http_error(mock_youtube_resource):
    """Test verify_playlist_exists handles other HttpErrors."""
    error_500 = create_http_error(500)
    mock_youtube_resource["playlists_list_execute"].side_effect = error_500
    playlist_id = "PL_500"

    result = verify_playlist_exists(mock_youtube_resource["youtube"], playlist_id)

    assert result is False
    mock_youtube_resource["log_error"].assert_any_call(f"API Error verifying playlist ID '{playlist_id}': {error_500}")
    mock_youtube_resource["click_echo"].assert_any_call(f"Error: An API error occurred while verifying playlist ID '{playlist_id}': {error_500}", err=True)

def test_verify_playlist_exists_unexpected_error(mock_youtube_resource):
    """Test verify_playlist_exists handles unexpected non-HTTP errors."""
    error_unexpected = Exception("Something broke")
    mock_youtube_resource["playlists_list_execute"].side_effect = error_unexpected
    playlist_id = "PL_broken"

    result = verify_playlist_exists(mock_youtube_resource["youtube"], playlist_id)

    assert result is False
    mock_youtube_resource["log_error"].assert_any_call(f"An unexpected error occurred verifying playlist ID '{playlist_id}': {error_unexpected}")
    mock_youtube_resource["click_echo"].assert_any_call(f"An unexpected error occurred while verifying playlist ID: {error_unexpected}", err=True)


# --- Tests for get_existing_playlist_video_ids ---

def test_get_existing_ids_success_no_pagination(mock_youtube_resource):
    """Test fetching existing IDs successfully with no pagination needed."""
    playlist_id = "PL_test"
    mock_youtube_resource["playlistItems_list_execute"].return_value = {
        "items": [
            {"snippet": {"resourceId": {"videoId": "vid1"}}},
            {"snippet": {"resourceId": {"videoId": "vid2"}}}
        ]
        # No nextPageToken means end of list
    }

    result = get_existing_playlist_video_ids(mock_youtube_resource["youtube"], playlist_id)

    assert result == {"vid1", "vid2"}
    mock_youtube_resource["youtube"].playlistItems().list.assert_called_once_with(
        part="snippet", playlistId=playlist_id, maxResults=50, pageToken=None
    )
    mock_youtube_resource["playlistItems_list_execute"].assert_called_once()
    mock_youtube_resource["log_info"].assert_any_call(f"Found {len(result)} existing video IDs in the playlist.")

def test_get_existing_ids_success_with_pagination(mock_youtube_resource):
    """Test fetching existing IDs successfully across multiple pages."""
    playlist_id = "PL_paged"
    mock_youtube_resource["playlistItems_list_execute"].side_effect = [
        {
            "items": [{"snippet": {"resourceId": {"videoId": "vid1"}}}],
            "nextPageToken": "page2"
        },
        {
            "items": [{"snippet": {"resourceId": {"videoId": "vid2"}}}],
            # No nextPageToken on the second response
        }
    ]

    result = get_existing_playlist_video_ids(mock_youtube_resource["youtube"], playlist_id)

    assert result == {"vid1", "vid2"}
    # Verify the execute method was called twice (once for each page)
    assert mock_youtube_resource["playlistItems_list_execute"].call_count == 2
    # Check the arguments passed to the list method (optional)
    # expected_list_calls = [
    #     call(part="snippet", playlistId=playlist_id, maxResults=50, pageToken=None),
    #     call(part="snippet", playlistId=playlist_id, maxResults=50, pageToken="page2")
    # ]
    # mock_youtube_resource["youtube"].playlistItems().list.assert_has_calls(expected_list_calls)

    mock_youtube_resource["log_info"].assert_any_call(f"Found {len(result)} existing video IDs in the playlist.")

def test_get_existing_ids_http_500_retry_success(mock_youtube_resource):
    """Test retry logic on 500 error, succeeding on the second attempt."""
    playlist_id = "PL_retry"
    error_500 = create_http_error(500)
    success_response = {"items": [{"snippet": {"resourceId": {"videoId": "vid1"}}}]}

    mock_youtube_resource["playlistItems_list_execute"].side_effect = [error_500, success_response]

    result = get_existing_playlist_video_ids(mock_youtube_resource["youtube"], playlist_id)

    assert result == {"vid1"}
    assert mock_youtube_resource["playlistItems_list_execute"].call_count == 2
    mock_youtube_resource["log_warning"].assert_any_call(f"Attempt 1/{MAX_RETRIES}: API Error fetching existing playlist items: {error_500}. Retrying in {INITIAL_BACKOFF}s...")
    mock_youtube_resource["sleep"].assert_called_once_with(INITIAL_BACKOFF)
    mock_youtube_resource["log_info"].assert_any_call(f"Found {len(result)} existing video IDs in the playlist.")

def test_get_existing_ids_http_404_no_retry(mock_youtube_resource):
    """Test that 404 error during fetch is not retried and returns empty set."""
    playlist_id = "PL_vanished"
    error_404 = create_http_error(404)
    mock_youtube_resource["playlistItems_list_execute"].side_effect = error_404

    result = get_existing_playlist_video_ids(mock_youtube_resource["youtube"], playlist_id)

    assert result == set()
    assert mock_youtube_resource["playlistItems_list_execute"].call_count == 1
    mock_youtube_resource["log_warning"].assert_any_call(f"Attempt 1/{MAX_RETRIES}: API Error fetching existing playlist items: {error_404}. Retrying in {INITIAL_BACKOFF}s...")
    mock_youtube_resource["log_error"].assert_any_call(f"Playlist '{playlist_id}' not found while fetching existing items.")
    mock_youtube_resource["click_echo"].assert_any_call(f"Error: Playlist ID '{playlist_id}' seems to have become inaccessible after the initial check.", err=True)
    mock_youtube_resource["sleep"].assert_not_called()

def test_get_existing_ids_max_retries_fail(mock_youtube_resource):
    """Test that fetching fails after MAX_RETRIES attempts on 503 errors."""
    playlist_id = "PL_persistent_fail"
    error_503 = create_http_error(503)
    mock_youtube_resource["playlistItems_list_execute"].side_effect = [error_503] * MAX_RETRIES

    result = get_existing_playlist_video_ids(mock_youtube_resource["youtube"], playlist_id)

    assert result == set()
    assert mock_youtube_resource["playlistItems_list_execute"].call_count == MAX_RETRIES
    assert mock_youtube_resource["sleep"].call_count == MAX_RETRIES -1 # Sleeps between retries
    mock_youtube_resource["log_error"].assert_any_call(f"Failed to fetch existing playlist items after {MAX_RETRIES} attempts due to API server errors.")
    mock_youtube_resource["click_echo"].assert_any_call(f"Error: Failed to retrieve existing videos from playlist '{playlist_id}' due to API server errors.", err=True)

def test_get_existing_ids_non_retryable_http_error(mock_youtube_resource):
    """Test fetching fails immediately on non-retryable HTTP error (e.g., 403)."""
    playlist_id = "PL_forbidden"
    error_403 = create_http_error(403)
    mock_youtube_resource["playlistItems_list_execute"].side_effect = error_403

    result = get_existing_playlist_video_ids(mock_youtube_resource["youtube"], playlist_id)

    assert result == set()
    assert mock_youtube_resource["playlistItems_list_execute"].call_count == 1
    mock_youtube_resource["log_error"].assert_any_call(f"Failed to fetch existing playlist items after 1 attempts due to non-retryable error: {error_403}")
    mock_youtube_resource["click_echo"].assert_any_call(f"Error: An API error occurred retrieving existing videos from playlist '{playlist_id}'.", err=True)
    mock_youtube_resource["sleep"].assert_not_called()

def test_get_existing_ids_unexpected_error_retry_fail(mock_youtube_resource):
    """Test retry logic fails on unexpected errors after max attempts."""
    playlist_id = "PL_unexpected"
    unexpected_error = Exception("Something else broke")
    mock_youtube_resource["playlistItems_list_execute"].side_effect = [unexpected_error] * MAX_RETRIES

    result = get_existing_playlist_video_ids(mock_youtube_resource["youtube"], playlist_id)

    assert result == set()
    assert mock_youtube_resource["playlistItems_list_execute"].call_count == MAX_RETRIES
    assert mock_youtube_resource["sleep"].call_count == MAX_RETRIES -1
    mock_youtube_resource["log_error"].assert_any_call(f"Failed to fetch existing playlist items after {MAX_RETRIES} attempts due to unexpected error: {unexpected_error}")
    mock_youtube_resource["click_echo"].assert_any_call(f"Error: An unexpected error occurred retrieving existing videos from playlist '{playlist_id}'.", err=True)

# --- Tests for add_video_to_playlist ---

def test_add_video_success(mock_youtube_resource):
    """Test successfully adding a video."""
    playlist_id = "PL_add_test"
    video_id = "vid_add"
    mock_response = {"id": "playlistItemId_123"}
    mock_youtube_resource["playlistItems_insert_execute"].return_value = mock_response

    result = add_video_to_playlist(mock_youtube_resource["youtube"], playlist_id, video_id)

    assert result is True
    mock_youtube_resource["youtube"].playlistItems().insert.assert_called_once_with(
        part="snippet",
        body={
            "snippet": {
                "playlistId": playlist_id,
                "resourceId": {
                    "kind": "youtube#video",
                    "videoId": video_id
                }
            }
        }
    )
    mock_youtube_resource["playlistItems_insert_execute"].assert_called_once()
    mock_youtube_resource["log_info"].assert_any_call(f"Successfully added video ID '{video_id}' to playlist '{playlist_id}'. Response: {mock_response.get('id')}")
    mock_youtube_resource["click_echo"].assert_not_called()

def test_add_video_http_404_playlist_not_found(mock_youtube_resource):
    """Test add_video handles 404 error indicating playlist not found."""
    playlist_id = "PL_add_404_pl"
    video_id = "vid_add_404"
    error_404_playlist = create_http_error(404, b'{"error": {"errors": [{"reason": "playlistNotFound"}]}}')
    mock_youtube_resource["playlistItems_insert_execute"].side_effect = error_404_playlist

    result = add_video_to_playlist(mock_youtube_resource["youtube"], playlist_id, video_id)

    assert result is False
    mock_youtube_resource["log_error"].assert_any_call(f"Playlist '{playlist_id}' not found when trying to add video '{video_id}'.")
    mock_youtube_resource["click_echo"].assert_any_call(f"Error: Playlist ID '{playlist_id}' was not found. Please check the ID.", err=True)

def test_add_video_http_404_video_not_found(mock_youtube_resource):
    """Test add_video handles 404 error indicating video not found/private."""
    playlist_id = "PL_add_404_vid"
    video_id = "vid_private"
    # Note: The error content might vary, checking for 'videoNotFound' is key
    error_404_video = create_http_error(404, b'Some error content mentioning videoNotFound')
    mock_youtube_resource["playlistItems_insert_execute"].side_effect = error_404_video

    result = add_video_to_playlist(mock_youtube_resource["youtube"], playlist_id, video_id)

    assert result is False
    mock_youtube_resource["log_warning"].assert_any_call(f"Video ID '{video_id}' not found or private. Skipping.")
    mock_youtube_resource["click_echo"].assert_not_called() # Should not show user error for skippable video

def test_add_video_http_403_permission_denied(mock_youtube_resource):
    """Test add_video handles 403 permission denied error."""
    playlist_id = "PL_add_403"
    video_id = "vid_add_403"
    error_403 = create_http_error(403)
    mock_youtube_resource["playlistItems_insert_execute"].side_effect = error_403

    result = add_video_to_playlist(mock_youtube_resource["youtube"], playlist_id, video_id)

    assert result is False
    mock_youtube_resource["log_error"].assert_any_call(f"Permission denied (403) adding video '{video_id}'. Check API key/OAuth scopes, quota, or video/playlist permissions: {error_403}")
    mock_youtube_resource["click_echo"].assert_any_call(f"Error: Permission denied when adding video '{video_id}'. Check API/OAuth setup or playlist settings.", err=True)

def test_add_video_http_409_conflict(mock_youtube_resource):
    """Test add_video handles 409 conflict (e.g., video already exists)."""
    playlist_id = "PL_add_409"
    video_id = "vid_add_409"
    error_409 = create_http_error(409)
    mock_youtube_resource["playlistItems_insert_execute"].side_effect = error_409

    result = add_video_to_playlist(mock_youtube_resource["youtube"], playlist_id, video_id)

    assert result is False # Treats conflict as skippable/non-fatal
    mock_youtube_resource["log_warning"].assert_any_call(f"Video ID '{video_id}' might already be in the playlist '{playlist_id}' (API reported 409 Conflict). Skipping.")
    mock_youtube_resource["click_echo"].assert_not_called()

def test_add_video_http_500_server_error(mock_youtube_resource):
    """Test add_video handles 5xx server errors (non-fatal warning)."""
    playlist_id = "PL_add_500"
    video_id = "vid_add_500"
    error_500 = create_http_error(500)
    mock_youtube_resource["playlistItems_insert_execute"].side_effect = error_500

    result = add_video_to_playlist(mock_youtube_resource["youtube"], playlist_id, video_id)

    assert result is False
    mock_youtube_resource["log_warning"].assert_any_call(f"API Server Error ({error_500.resp.status}) occurred adding video '{video_id}': {error_500}. This might resolve on its own later.")
    mock_youtube_resource["click_echo"].assert_not_called()

def test_add_video_unexpected_error(mock_youtube_resource):
    """Test add_video handles unexpected non-HTTP errors."""
    playlist_id = "PL_add_broken"
    video_id = "vid_add_broken"
    error_unexpected = Exception("Something broke")
    mock_youtube_resource["playlistItems_insert_execute"].side_effect = error_unexpected

    result = add_video_to_playlist(mock_youtube_resource["youtube"], playlist_id, video_id)

    assert result is False
    mock_youtube_resource["log_error"].assert_any_call(f"An unexpected error occurred adding video '{video_id}': {error_unexpected}")
    mock_youtube_resource["click_echo"].assert_not_called() # Should log internally, maybe not echo for every unexpected add failure 