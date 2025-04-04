import click
import logging
import sys
import os
import re
import pickle
from pathlib import Path
from typing import Optional, List, Any

from googleapiclient.discovery import build, Resource
from googleapiclient.errors import HttpError
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# Constants
CLIENT_SECRETS_FILE = "client_secrets.json"
TOKEN_PICKLE_FILE = "token.pickle"
API_SERVICE_NAME = "youtube"
API_VERSION = "v3"
# This scope allows read/write access to YouTube playlists
SCOPES = ["https://www.googleapis.com/auth/youtube"]

# --- YouTube API Authentication ---

def get_authenticated_service() -> Optional[Resource]:
    """Authenticate with YouTube API and return the service resource."""
    credentials = None
    token_path = Path(TOKEN_PICKLE_FILE)
    secrets_path = Path(CLIENT_SECRETS_FILE)

    if not secrets_path.exists():
        logging.error(f"Error: {CLIENT_SECRETS_FILE} not found.")
        click.echo(f"Error: {CLIENT_SECRETS_FILE} not found. Please download it from Google Cloud Console and place it in the project root.", err=True)
        sys.exit(1)

    # Load existing credentials if available
    if token_path.exists():
        try:
            with open(token_path, "rb") as token_file:
                credentials = pickle.load(token_file)
        except Exception as e:
            logging.warning(f"Could not load token file: {e}. Re-authenticating.")
            credentials = None # Force re-authentication

    # If no valid credentials, initiate OAuth flow
    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            try:
                logging.info("Credentials expired, refreshing...")
                credentials.refresh(Request())
            except Exception as e:
                logging.warning(f"Failed to refresh token: {e}. Re-authenticating.")
                # If refresh fails, force re-authentication by deleting token
                if token_path.exists():
                    token_path.unlink()
                credentials = None # Ensure re-authentication flow starts
        else:
            logging.info("No valid credentials found, starting authentication flow.")
            try:
                flow = InstalledAppFlow.from_client_secrets_file(secrets_path, SCOPES)
                # Run local server flow opens a browser window for user authorization
                credentials = flow.run_local_server(port=0)
            except Exception as e:
                logging.error(f"Authentication flow failed: {e}")
                click.echo(f"Error during authentication: {e}", err=True)
                return None

        # Save the credentials for the next run
        try:
            with open(token_path, "wb") as token_file:
                pickle.dump(credentials, token_file)
            logging.info(f"Credentials saved to {token_path}")
        except Exception as e:
             logging.error(f"Failed to save token: {e}")
             click.echo(f"Warning: Could not save credentials to {token_path}: {e}", err=True)


    # Build the YouTube API service
    try:
        return build(API_SERVICE_NAME, API_VERSION, credentials=credentials)
    except HttpError as e:
        logging.error(f"Failed to build YouTube service: {e}")
        click.echo(f"Error building YouTube service: {e}", err=True)
        return None
    except Exception as e:
        logging.error(f"An unexpected error occurred building YouTube service: {e}")
        click.echo(f"An unexpected error occurred: {e}", err=True)
        return None


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

# --- Playlist Management ---

def get_existing_playlist_video_ids(youtube: Resource, playlist_id: str) -> set[str]:
    """Fetches all video IDs currently in the specified playlist."""
    existing_ids = set()
    next_page_token = None
    retries = 3 # Simple retry mechanism for potential transient issues
    attempt = 0

    logging.info(f"Fetching existing video IDs from playlist '{playlist_id}'...")

    while attempt < retries:
        try:
            while True:
                request = youtube.playlistItems().list(
                    part="snippet",
                    playlistId=playlist_id,
                    maxResults=50, # Max allowed by API
                    pageToken=next_page_token
                )
                response = request.execute()

                for item in response.get("items", []):
                    video_id = item.get("snippet", {}).get("resourceId", {}).get("videoId")
                    if video_id:
                        existing_ids.add(video_id)

                next_page_token = response.get("nextPageToken")
                if not next_page_token:
                    break # Exit inner loop if no more pages
            # If we successfully break the inner loop, break the outer retry loop
            break
        except HttpError as e:
            attempt += 1
            logging.warning(f"Attempt {attempt}/{retries}: API Error fetching existing playlist items: {e}")
            if e.resp.status == 404: # Playlist genuinely not found during fetch
                logging.error(f"Playlist '{playlist_id}' not found while fetching existing items.")
                click.echo(f"Error: Playlist ID '{playlist_id}' seems to have become inaccessible after the initial check.", err=True)
                # Reset existing_ids as we cannot trust partial results
                return set()
            if attempt >= retries:
                logging.error(f"Failed to fetch existing playlist items after {retries} attempts.")
                click.echo(f"Error: Failed to retrieve existing videos from playlist '{playlist_id}' due to API errors.", err=True)
                # Consider exiting or returning empty set based on desired robustness
                # Returning empty set means duplicates won't be checked if fetch fails
                return set()
            # Wait a bit before retrying (optional)
            # time.sleep(1)
        except Exception as e:
             attempt += 1
             logging.warning(f"Attempt {attempt}/{retries}: Unexpected error fetching existing playlist items: {e}")
             if attempt >= retries:
                logging.error(f"Failed to fetch existing playlist items after {retries} attempts due to unexpected error: {e}")
                click.echo(f"Error: An unexpected error occurred retrieving existing videos from playlist '{playlist_id}'.", err=True)
                return set()


    logging.info(f"Found {len(existing_ids)} existing video IDs in the playlist.")
    return existing_ids

def add_video_to_playlist(youtube: Resource, playlist_id: str, video_id: str) -> bool:
    """Adds a single video to the specified playlist."""
    try:
        request = youtube.playlistItems().insert(
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
        response = request.execute()
        logging.info(f"Successfully added video ID '{video_id}' to playlist '{playlist_id}'. Response: {response.get('id')}")
        return True
    except HttpError as e:
        # Handle common API errors
        if e.resp.status == 404:
             if "playlistNotFound" in str(e.content):
                 logging.error(f"Playlist '{playlist_id}' not found.")
                 click.echo(f"Error: Playlist ID '{playlist_id}' was not found. Please check the ID.", err=True)
             elif "videoNotFound" in str(e.content):
                 logging.warning(f"Video ID '{video_id}' not found or private. Skipping.")
             else:
                 logging.error(f"API Error adding video '{video_id}': {e}")
        elif e.resp.status == 403:
            logging.error(f"Permission denied adding video '{video_id}'. Check API key/OAuth scopes or quota: {e}")
        elif e.resp.status == 409: # Conflict - often means video already in playlist
             logging.warning(f"Video ID '{video_id}' might already be in the playlist '{playlist_id}'. Skipping.")
        else:
            logging.error(f"An HTTP error occurred adding video '{video_id}': {e}")
        return False
    except Exception as e:
        logging.error(f"An unexpected error occurred adding video '{video_id}': {e}")
        return False

# --- CLI Commands ---

@click.group()
def cli():
    """A CLI tool to manage YouTube playlists."""
    pass

@cli.command()
@click.option('--file', '-f', required=True, type=click.Path(exists=True, file_okay=True, dir_okay=False, readable=True, path_type=Path), help='Path to the file containing YouTube video URLs (one URL per line).')
@click.option('--playlist-id', '-p', required=True, type=str, help='The ID of the YouTube playlist to add videos to.')
def add(file: Path, playlist_id: str):
    """Adds videos from a file to a YouTube playlist."""
    logging.info(f"Starting to add videos from '{file}' to playlist '{playlist_id}'.")

    youtube = get_authenticated_service()
    if not youtube:
        click.echo("Failed to authenticate with YouTube API. Exiting.", err=True)
        sys.exit(1)

    logging.info("Successfully authenticated with YouTube API.")

    # --- Add Playlist ID Validity Check ---
    logging.info(f"Verifying playlist ID: {playlist_id}")
    try:
        request = youtube.playlists().list(
            part="id",
            id=playlist_id,
            maxResults=1
        )
        response = request.execute()
        if not response.get("items"):
            # This case might occur if the ID has a valid format but doesn't exist
            logging.error(f"Playlist ID '{playlist_id}' not found or user does not have access.")
            click.echo(f"Error: Playlist ID '{playlist_id}' not found or you do not have access to it.", err=True)
            sys.exit(1)
        logging.info(f"Playlist ID '{playlist_id}' is valid and accessible.")

    except HttpError as e:
        logging.error(f"API Error verifying playlist ID '{playlist_id}': {e}")
        if e.resp.status == 404:
             click.echo(f"Error: Playlist ID '{playlist_id}' was not found. Please check the ID.", err=True)
        elif e.resp.status == 403:
             click.echo(f"Error: Permission denied when trying to access playlist '{playlist_id}'. Check API key/OAuth scopes or playlist permissions.", err=True)
        else:
             click.echo(f"Error: An API error occurred while verifying playlist ID '{playlist_id}': {e}", err=True)
        sys.exit(1)
    except Exception as e:
        logging.error(f"An unexpected error occurred verifying playlist ID '{playlist_id}': {e}")
        click.echo(f"An unexpected error occurred while verifying playlist ID: {e}", err=True)
        sys.exit(1)
    # --- End Playlist ID Validity Check ---

    # --- Fetch Existing Video IDs for Deduplication ---
    existing_video_ids = get_existing_playlist_video_ids(youtube, playlist_id)

    # --- End Fetch Existing Video IDs ---

    added_count = 0
    skipped_count = 0
    duplicate_count = 0 # New counter for duplicates
    error_count = 0
    line_num = 0

    try:
        with open(file, 'r') as f:
            for line_num, line in enumerate(f, 1):
                url = line.strip()
                if not url or url.startswith("#"): # Skip empty lines and comments
                    continue

                video_id = extract_video_id(url)
                if video_id:
                    # --- Check for Duplicates ---
                    if video_id in existing_video_ids:
                        logging.info(f"Skipping duplicate video ID: {video_id} (already in playlist)")
                        duplicate_count += 1
                        continue # Move to the next line
                    # --- End Check for Duplicates ---

                    logging.info(f"Attempting to add video ID: {video_id} from URL: {url}")
                    if add_video_to_playlist(youtube, playlist_id, video_id):
                        added_count += 1
                        # Optionally add successfully added ID to the set to prevent adding duplicates from the *same file*
                        # existing_video_ids.add(video_id)
                    else:
                        # Error logging is handled within add_video_to_playlist
                        error_count += 1
                else:
                    click.echo(f"Warning: Could not extract video ID from line {line_num}: '{url}'", err=True)
                    skipped_count += 1

    except FileNotFoundError:
        logging.error(f"Input file not found: {file}")
        click.echo(f"Error: Input file not found: {file}", err=True)
        sys.exit(1)
    except Exception as e:
        logging.error(f"An error occurred processing the file: {e}")
        click.echo(f"An error occurred processing the file: {e}", err=True)
        sys.exit(1)

    logging.info("Video adding process finished.")
    click.echo("\n--- Summary ---")
    click.echo(f"Successfully added: {added_count} videos.")
    click.echo(f"Skipped (invalid URL/ID): {skipped_count} lines.")
    click.echo(f"Skipped (duplicate): {duplicate_count} videos.") # Added duplicate info
    click.echo(f"Errors during addition: {error_count} videos.")

    # Check if the last API call failed due to playlist not found (error_count > 0)
    # We can't be certain this was the *only* error, but it's a common case.
    if error_count > 0 and added_count == 0 and skipped_count == 0:
         click.echo("Consider checking if the playlist ID is correct or if the playlist exists.", err=True)


def main():
    # Check if client_secrets.json exists before running the CLI
    # Authentication function will handle detailed error message if missing.
    if not Path(CLIENT_SECRETS_FILE).exists():
         click.echo(f"Warning: {CLIENT_SECRETS_FILE} not found. Authentication will fail.", err=True)
         click.echo(f"Please download it from Google Cloud Console and place it in the project root: {Path().resolve()}", err=True)
         # Allow CLI to proceed, get_authenticated_service will exit if needed
    cli()

if __name__ == '__main__':
    main() 