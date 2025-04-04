import logging
import sys
import pickle
from pathlib import Path
from typing import Optional

import click
from googleapiclient.discovery import build, Resource
from googleapiclient.errors import HttpError
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

# Constants - Consider moving these to a config module or loading from env
CLIENT_SECRETS_FILE = "client_secrets.json" # Path relative to project root
TOKEN_PICKLE_FILE = "token.pickle"           # Path relative to project root
API_SERVICE_NAME = "youtube"
API_VERSION = "v3"
SCOPES = ["https://www.googleapis.com/auth/youtube"]


def get_authenticated_service() -> Optional[Resource]:
    """Authenticate with YouTube API and return the service resource."""
    credentials = None
    # Determine paths relative to the project root or a defined config location
    # For simplicity now, assuming they are in the root where the script might be invoked from
    # Or, more robustly, define them relative to this file's location if structure is fixed
    # Or use environment variables / dedicated config dir
    base_path = Path() # Current working directory assumption - might need adjustment
    token_path = base_path / TOKEN_PICKLE_FILE
    secrets_path = base_path / CLIENT_SECRETS_FILE

    if not secrets_path.exists():
        logging.error(f"Error: {CLIENT_SECRETS_FILE} not found at {secrets_path.resolve()}.")
        click.echo(f"Error: {CLIENT_SECRETS_FILE} not found. Please download it from Google Cloud Console and place it in the project root directory ({base_path.resolve()}).", err=True)
        sys.exit(1)

    # Load existing credentials if available
    if token_path.exists():
        try:
            with open(token_path, "rb") as token_file:
                credentials = pickle.load(token_file)
            logging.info(f"Loaded credentials from {token_path}")
        except Exception as e:
            logging.warning(f"Could not load token file ({token_path}): {e}. Re-authenticating.")
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
                    try:
                        token_path.unlink()
                        logging.info(f"Removed invalid token file: {token_path}")
                    except OSError as unlink_e:
                        logging.error(f"Error removing token file {token_path}: {unlink_e}")
                credentials = None # Ensure re-authentication flow starts
        else:
            if not credentials: # Only log this if we didn't try to refresh
                 logging.info("No valid credentials found, starting authentication flow.")
            try:
                flow = InstalledAppFlow.from_client_secrets_file(str(secrets_path), SCOPES)
                # Run local server flow opens a browser window for user authorization
                credentials = flow.run_local_server(port=0)
            except FileNotFoundError:
                 # This specific error is already checked above, but good to be explicit
                 logging.error(f"Critical: {CLIENT_SECRETS_FILE} not found during flow creation at {secrets_path}")
                 click.echo(f"Error: {CLIENT_SECRETS_FILE} not found at expected location: {secrets_path.resolve()}", err=True)
                 sys.exit(1)
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
             logging.error(f"Failed to save token to {token_path}: {e}")
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