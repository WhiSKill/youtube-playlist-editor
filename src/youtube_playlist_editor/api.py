import logging
import click
import sys
import time # Added for potential backoff
from typing import Optional

from googleapiclient.discovery import Resource
from googleapiclient.errors import HttpError

# Consider using tenacity for more robust retries
# from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

MAX_RETRIES = 3
INITIAL_BACKOFF = 1 # seconds

# --- Playlist Management ---

def get_existing_playlist_video_ids(youtube: Resource, playlist_id: str) -> set[str]:
    """Fetches all video IDs currently in the specified playlist with retry logic."""
    existing_ids = set()
    next_page_token = None
    attempt = 0

    logging.info(f"Fetching existing video IDs from playlist '{playlist_id}'...")

    while attempt < MAX_RETRIES:
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
            wait_time = INITIAL_BACKOFF * (2 ** (attempt - 1)) # Exponential backoff
            logging.warning(f"Attempt {attempt}/{MAX_RETRIES}: API Error fetching existing playlist items: {e}. Retrying in {wait_time}s...")

            if e.resp.status == 404: # Playlist genuinely not found during fetch
                logging.error(f"Playlist '{playlist_id}' not found while fetching existing items.")
                click.echo(f"Error: Playlist ID '{playlist_id}' seems to have become inaccessible after the initial check.", err=True)
                return set()
            elif e.resp.status in [500, 502, 503, 504]: # Common transient errors
                if attempt >= MAX_RETRIES:
                    logging.error(f"Failed to fetch existing playlist items after {MAX_RETRIES} attempts due to API server errors.")
                    click.echo(f"Error: Failed to retrieve existing videos from playlist '{playlist_id}' due to API server errors.", err=True)
                    return set()
                time.sleep(wait_time)
            else: # Non-retryable HTTP error or final attempt failed
                logging.error(f"Failed to fetch existing playlist items after {attempt} attempts due to non-retryable error: {e}")
                click.echo(f"Error: An API error occurred retrieving existing videos from playlist '{playlist_id}'.", err=True)
                return set()

        except Exception as e:
             attempt += 1
             wait_time = INITIAL_BACKOFF * (2 ** (attempt - 1))
             logging.warning(f"Attempt {attempt}/{MAX_RETRIES}: Unexpected error fetching existing playlist items: {e}. Retrying in {wait_time}s...")
             if attempt >= MAX_RETRIES:
                logging.error(f"Failed to fetch existing playlist items after {MAX_RETRIES} attempts due to unexpected error: {e}")
                click.echo(f"Error: An unexpected error occurred retrieving existing videos from playlist '{playlist_id}'.", err=True)
                return set()
             time.sleep(wait_time)


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
                 logging.error(f"Playlist '{playlist_id}' not found when trying to add video '{video_id}'.")
                 click.echo(f"Error: Playlist ID '{playlist_id}' was not found. Please check the ID.", err=True)
             elif "videoNotFound" in str(e.content):
                 logging.warning(f"Video ID '{video_id}' not found or private. Skipping.")
             else:
                 logging.error(f"API Error (404) adding video '{video_id}': {e}")
        elif e.resp.status == 403:
            # Could be quota, permissions, terms of service etc.
            logging.error(f"Permission denied (403) adding video '{video_id}'. Check API key/OAuth scopes, quota, or video/playlist permissions: {e}")
            click.echo(f"Error: Permission denied when adding video '{video_id}'. Check API/OAuth setup or playlist settings.", err=True)
        elif e.resp.status == 409: # Conflict - often means video already in playlist
             # Note: Our deduplication check should prevent this, but API might have edge cases
             logging.warning(f"Video ID '{video_id}' might already be in the playlist '{playlist_id}' (API reported 409 Conflict). Skipping.")
        elif e.resp.status in [500, 502, 503, 504]: # Transient server errors
             logging.warning(f"API Server Error ({e.resp.status}) occurred adding video '{video_id}': {e}. This might resolve on its own later.")
             # Don't necessarily treat as fatal, but report
        else:
            logging.error(f"An unexpected HTTP error occurred adding video '{video_id}': {e}")
        return False
    except Exception as e:
        logging.error(f"An unexpected error occurred adding video '{video_id}': {e}")
        return False

def verify_playlist_exists(youtube: Resource, playlist_id: str) -> bool:
    """Checks if a playlist exists and is accessible."""
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
            # or user lacks permissions
            logging.error(f"Playlist ID '{playlist_id}' not found or user does not have access.")
            click.echo(f"Error: Playlist ID '{playlist_id}' not found or you do not have access to it.", err=True)
            return False
        logging.info(f"Playlist ID '{playlist_id}' is valid and accessible.")
        return True

    except HttpError as e:
        logging.error(f"API Error verifying playlist ID '{playlist_id}': {e}")
        if e.resp.status == 404:
             click.echo(f"Error: Playlist ID '{playlist_id}' was not found. Please check the ID.", err=True)
        elif e.resp.status == 403:
             click.echo(f"Error: Permission denied when trying to access playlist '{playlist_id}'. Check API key/OAuth scopes or playlist permissions.", err=True)
        else:
             click.echo(f"Error: An API error occurred while verifying playlist ID '{playlist_id}': {e}", err=True)
        return False
    except Exception as e:
        logging.error(f"An unexpected error occurred verifying playlist ID '{playlist_id}': {e}")
        click.echo(f"An unexpected error occurred while verifying playlist ID: {e}", err=True)
        return False 