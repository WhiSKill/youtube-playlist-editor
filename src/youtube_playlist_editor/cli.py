import click
import logging
import sys
from pathlib import Path

# Import functions from other modules
from .auth import get_authenticated_service
from .api import get_existing_playlist_video_ids, add_video_to_playlist, verify_playlist_exists
from .utils import extract_video_id

# Configure logging (can be configured once at the top level)
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

@click.group()
def cli():
    """A CLI tool to manage YouTube playlists."""
    pass

@cli.command()
@click.option('--file', '-f', required=True,
              type=click.Path(exists=True, file_okay=True, dir_okay=False, readable=True, path_type=Path),
              help='Path to the file containing YouTube video URLs (one URL per line).')
@click.option('--playlist-id', '-p', required=True, type=str,
              help='The ID of the YouTube playlist to add videos to.')
def add(file: Path, playlist_id: str):
    """Adds videos from a file to a YouTube playlist."""
    logging.info(f"Starting to add videos from '{file}' to playlist '{playlist_id}'.")

    youtube = get_authenticated_service()
    if not youtube:
        click.echo("Failed to authenticate with YouTube API. Exiting.", err=True)
        sys.exit(1)

    logging.info("Successfully authenticated with YouTube API.")

    # Verify playlist exists before proceeding
    if not verify_playlist_exists(youtube, playlist_id):
         # verify_playlist_exists already prints error messages
         sys.exit(1)

    # Fetch Existing Video IDs for Deduplication
    existing_video_ids = get_existing_playlist_video_ids(youtube, playlist_id)
    # Note: If get_existing_playlist_video_ids fails, it returns an empty set and logs errors.
    # The script will continue but won't deduplicate properly if the fetch failed.
    # Consider exiting if the fetch fails catastrophically based on requirements.

    added_count = 0
    skipped_count = 0
    duplicate_count = 0
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
                    # Check for Duplicates
                    if video_id in existing_video_ids:
                        logging.info(f"Skipping duplicate video ID: {video_id} (already in playlist)")
                        duplicate_count += 1
                        continue # Move to the next line

                    logging.info(f"Attempting to add video ID: {video_id} from URL: {url}")
                    if add_video_to_playlist(youtube, playlist_id, video_id):
                        added_count += 1
                        # Add to set locally to prevent duplicates from *within the same file*
                        # if the API call succeeds, even if initial fetch failed.
                        existing_video_ids.add(video_id)
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
        logging.error(f"An error occurred processing the file '{file}': {e}", exc_info=True) # Add traceback
        click.echo(f"An unexpected error occurred processing the file: {e}", err=True)
        sys.exit(1)

    logging.info("Video adding process finished.")
    click.echo("\n--- Summary ---")
    click.echo(f"Successfully added: {added_count} videos.")
    click.echo(f"Skipped (invalid URL/ID): {skipped_count} lines.")
    click.echo(f"Skipped (duplicate): {duplicate_count} videos.")
    click.echo(f"Errors during addition: {error_count} videos.")

    # Provide hint if errors occurred and no videos were added
    if error_count > 0 and added_count == 0:
         click.echo("\nHint: Errors occurred during the process. Please check the log messages above.", err=True)
         click.echo("Common issues include incorrect playlist ID, lack of permissions, or invalid video IDs.", err=True) 