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
    """Authenticates with the YouTube API using OAuth 2.0.

    Handles token loading, refreshing, and the initial OAuth flow.

    Returns:
        Optional[Resource]: An authenticated YouTube API service object, or None if authentication fails.
    """
    credentials = None # Initialize credentials to None
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

    # Attempt to load existing credentials
    if token_path.exists():
        try:
            with open(token_path, "rb") as token_file:
                loaded_creds = pickle.load(token_file)
            logging.info(f"Loaded credentials from {token_path}")

            # Check validity and expiry *after* loading
            if loaded_creds and loaded_creds.valid:
                credentials = loaded_creds # Use valid credentials

            elif loaded_creds and loaded_creds.expired and loaded_creds.refresh_token:
                try:
                    logging.info("Credentials expired, refreshing...")
                    loaded_creds.refresh(Request())
                    credentials = loaded_creds # Use refreshed credentials
                    # Save refreshed token immediately
                    try:
                        with open(token_path, "wb") as token_file:
                            pickle.dump(credentials, token_file)
                        logging.info(f"Refreshed credentials saved to {token_path}")
                    except Exception as save_e:
                        logging.error(f"Failed to save refreshed token to {token_path}: {save_e}")
                        click.echo(f"Warning: Could not save refreshed credentials to {token_path}: {save_e}", err=True)
                        # Continue with refreshed creds even if save fails

                except Exception as refresh_e:
                    logging.warning(f"Failed to refresh token: {refresh_e}. Re-authenticating by removing token.")
                    # If refresh fails, delete token file and ensure credentials remains None
                    if token_path.exists(): # Check again before unlinking
                        try:
                            token_path.unlink()
                            logging.info(f"Removed invalid token file: {token_path}")
                        except OSError as unlink_e:
                            logging.error(f"Error removing token file {token_path}: {unlink_e}")
                    credentials = None # Explicitly ensure it's None for the next check

            else:
                 # Token file existed but creds were invalid/not refreshable
                 logging.warning(f"Invalid or non-refreshable credentials found in {token_path}. Re-authenticating.")
                 # No need to delete token here, flow will overwrite it
                 credentials = None

        except Exception as load_e:
            logging.warning(f"Could not load token file ({token_path}): {load_e}. Re-authenticating.")
            credentials = None # Ensure re-authentication on load failure

    # If credentials are still None after trying to load/refresh, start flow
    if credentials is None:
        logging.info("No valid credentials available, starting authentication flow.")
        try:
            flow = InstalledAppFlow.from_client_secrets_file(str(secrets_path), SCOPES)
            # Run local server flow opens a browser window for user authorization
            credentials = flow.run_local_server(port=0) # This might be None if flow fails internally? No, usually raises.
            if not credentials:
                 # Should not happen with run_local_server unless user cancels early?
                 logging.error("Authentication flow did not return credentials.")
                 click.echo("Authentication cancelled or failed.", err=True)
                 return None

            # Save the new credentials immediately after successful flow
            try:
                with open(token_path, "wb") as token_file:
                    pickle.dump(credentials, token_file)
                logging.info(f"New credentials saved to {token_path}")
            except Exception as e:
                 logging.error(f"Failed to save new token to {token_path}: {e}")
                 click.echo(f"Warning: Could not save new credentials to {token_path}: {e}", err=True)
                 # Proceed with credentials even if save fails

        except FileNotFoundError:
             # This specific error is already checked above, but good to be explicit
             logging.error(f"Critical: {CLIENT_SECRETS_FILE} not found during flow creation at {secrets_path}")
             click.echo(f"Error: {CLIENT_SECRETS_FILE} not found at expected location: {secrets_path.resolve()}", err=True)
             sys.exit(1) # Exit if secrets file missing during flow
        except Exception as e:
            logging.error(f"Authentication flow failed: {e}", exc_info=True) # Log traceback
            click.echo(f"Error during authentication: {e}", err=True)
            return None # Exit if flow fails for other reasons

    # --- Build Service ---
    # At this point, credentials should be valid (loaded, refreshed, or from new flow)
    # OR None only if the authentication flow itself failed explicitly and returned None above.
    if not credentials:
         # This case should ideally only be hit if flow failed and returned None above
         logging.error("Cannot build service, authentication failed.")
         return None

    try:
        service = build(API_SERVICE_NAME, API_VERSION, credentials=credentials)
        logging.info(f"Successfully built YouTube {API_VERSION} service.")
        return service
    except HttpError as e:
        logging.error(f"Failed to build YouTube service: {e}")
        click.echo(f"Error building YouTube service: {e}", err=True)
        return None
    except Exception as e:
        logging.error(f"An unexpected error occurred building YouTube service: {e}", exc_info=True) # Log traceback
        click.echo(f"An unexpected error occurred: {e}", err=True)
        return None 