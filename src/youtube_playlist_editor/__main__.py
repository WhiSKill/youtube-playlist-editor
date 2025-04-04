import sys
import logging
from pathlib import Path
import click

# Assume auth constants might still be defined here or imported from a config module
# For now, keep the check simple, auth module handles the detailed check.
CLIENT_SECRETS_FILE = "client_secrets.json"

def main():
    """Main entry point for the application."""
    # Minimal pre-check for secrets file existence for early user feedback
    # The auth module will perform the definitive check and exit if needed.
    if not Path(CLIENT_SECRETS_FILE).exists():
         # Use logging for internal state, click.echo for user feedback
         logging.warning(f"{CLIENT_SECRETS_FILE} not found in the expected location (project root: {Path().resolve()}). Authentication will likely fail.")
         click.echo(f"Warning: {CLIENT_SECRETS_FILE} not found. Please ensure it is in the project root directory: {Path().resolve()}", err=True)
         click.echo("The application will attempt to proceed, but authentication is required.", err=True)
         # Don't exit here, let the auth module handle the failure gracefully.

    # Import the CLI function *after* the initial check
    try:
        from .cli import cli
        cli()
    except ImportError as e:
        logging.critical(f"Failed to import application components: {e}", exc_info=True)
        click.echo(f"Fatal Error: Could not start the application due to an internal import error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        # Catch any unexpected errors during CLI setup or execution
        logging.critical(f"An unexpected error occurred: {e}", exc_info=True)
        click.echo(f"An unexpected fatal error occurred: {e}", err=True)
        sys.exit(1)

if __name__ == '__main__':
    main() 