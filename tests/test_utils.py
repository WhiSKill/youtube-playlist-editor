# Placeholder for utils tests 

import pytest
from youtube_playlist_editor.utils import extract_video_id

# Test cases with expected video IDs
VALID_URLS = [
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("http://www.youtube.com/watch?v=dQw4w9WgXcQ&feature=related", "dQw4w9WgXcQ"),
    ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("http://youtu.be/dQw4w9WgXcQ?t=15", "dQw4w9WgXcQ"),
    ("https://www.youtube.com/embed/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("http://www.youtube.com/v/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://www.youtube.com/shorts/AbCdEfGhIjK", "AbCdEfGhIjK"),
    ("http://www.youtube.com/live/lMnKoJx3yXk?si=abc", "lMnKoJx3yXk"),
    ("youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"), # No protocol
    # Add more valid examples if needed
]

# Test cases where no video ID should be found
INVALID_URLS = [
    "https://www.google.com",
    "https://www.youtube.com/watch?v=", # Missing ID
    "https://www.youtube.com/watch?vid=dQw4w9WgXcQ", # Wrong parameter
    "just a string",
    "youtu.be/", # Missing ID
    "https://example.com/dQw4w9WgXcQ",
    "", # Empty string
    # Add more invalid examples if needed
]

@pytest.mark.parametrize("url, expected_id", VALID_URLS)
def test_extract_video_id_valid(url, expected_id):
    """Tests that extract_video_id correctly parses valid URLs."""
    assert extract_video_id(url) == expected_id

@pytest.mark.parametrize("url", INVALID_URLS)
def test_extract_video_id_invalid(url):
    """Tests that extract_video_id returns None for invalid URLs."""
    assert extract_video_id(url) is None

def test_extract_video_id_logging(caplog):
    """Tests that a warning is logged for invalid URLs."""
    import logging
    caplog.set_level(logging.WARNING)
    invalid_url = "https://not_youtube.com/watch?v=invalid"
    extract_video_id(invalid_url)
    assert f"Could not extract video ID from URL: {invalid_url}" in caplog.text 