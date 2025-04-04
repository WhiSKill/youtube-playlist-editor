import re
import logging
from typing import Optional

# --- URL Parsing ---

def extract_video_id(url: str) -> Optional[str]:
    """Extracts YouTube video ID from various URL formats."""
    # Regex patterns to match YouTube video IDs
    patterns = [
        r'(?:https?:\/\/)?(?:www\.)?youtube\.com\/watch\?v=([a-zA-Z0-9_-]{11})',        # Standard watch URL
        r'(?:https?:\/\/)?(?:www\.)?youtu\.be\/([a-zA-Z0-9_-]{11})',                 # Shortened youtu.be URL
        r'(?:https?:\/\/)?(?:www\.)?youtube\.com\/embed\/([a-zA-Z0-9_-]{11})',       # Embed URL
        r'(?:https?:\/\/)?(?:www\.)?youtube\.com\/v\/([a-zA-Z0-9_-]{11})',           # v/ URL
        r'(?:https?:\/\/)?(?:www\.)?youtube\.com\/shorts\/([a-zA-Z0-9_-]{11})',     # Shorts URL
        r'(?:https?:\/\/)?(?:www\.)?youtube\.com\/live\/([a-zA-Z0-9_-]{11})'         # Live URL
        # Add more patterns if needed
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    logging.warning(f"Could not extract video ID from URL: {url}")
    return None 