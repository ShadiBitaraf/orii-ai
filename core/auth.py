# Google OAuth (from credential_utils.py)

"""
Credential utilities for Google Calendar API.
"""

import os
import sys
import json
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# If modifying these scopes, delete the file token.json.
SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
]


def setup_oauth_flow():
    """Run the OAuth flow to set up credentials.

    This function starts the OAuth flow, opens a browser window for user consent,
    and then saves the credentials to a .env file.
    """
    print("\n=== Setting up Google Calendar OAuth ===")
    print("This will open a browser window for you to log in and authorize access.")

    # Check if we have client ID and secret in environment
    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")

    if not client_id or not client_secret:
        print(
            "ERROR: GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set in your .env file"
        )
        print("Please add these values to your .env file and try again.")
        return False

    try:
        # Create client config dict
        client_config = {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"],
            }
        }

        # Create flow
        flow = InstalledAppFlow.from_client_config(
            client_config, SCOPES, redirect_uri="http://localhost:0"
        )

        # Run local server flow
        creds = flow.run_local_server(port=0)

        # Get the refresh token and update .env file
        refresh_token = creds.refresh_token

        if refresh_token:
            # Read existing .env file
            env_path = ".env"
            env_vars = {}

            if os.path.exists(env_path):
                with open(env_path, "r") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        key, value = line.split("=", 1)
                        env_vars[key] = value

            # Update with refresh token
            env_vars["GOOGLE_REFRESH_TOKEN"] = refresh_token

            # Write back to .env file
            with open(env_path, "w") as f:
                for key, value in env_vars.items():
                    f.write(f"{key}={value}\n")

            print(f"Success! Refresh token saved to your .env file.")
            return True
        else:
            print("Error: No refresh token received")
            return False

    except Exception as e:
        print(f"Error during OAuth flow: {e}")
        return False


def get_credentials():
    """Get or refresh Google Calendar API credentials from environment variables.

    Returns:
        Credentials object for the Google Calendar API
    """
    # Use environment variables instead of credentials.json
    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
    refresh_token = os.environ.get("GOOGLE_REFRESH_TOKEN")

    if not client_id or not client_secret:
        print("[ERROR] Google API credentials not found in environment variables")
        print("[ERROR] Please set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET")
        print(
            "[INFO] You can run the OAuth setup flow by running: python -m app.cli.credential_utils"
        )
        return None

    creds = None

    # Create credentials from environment variables if refresh token exists
    if refresh_token:
        creds = Credentials(
            None,  # No access token initially
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
            scopes=SCOPES,
        )

    # If there are no valid credentials but we have client ID/secret, we can proceed with local flow
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())

            # Save the refresh token back to environment for next time
            # This is just for demonstration - in a real app you might want to persist this differently
            os.environ["GOOGLE_REFRESH_TOKEN"] = creds.refresh_token
        else:
            print("[ERROR] No refresh token available in environment")
            print(
                "[INFO] You can run the OAuth setup flow by running: python -m app.cli.credential_utils"
            )
            return None

    return creds


if __name__ == "__main__":
    # Run the OAuth setup flow if this file is executed directly
    if setup_oauth_flow():
        print("OAuth setup completed successfully!")
    else:
        print("OAuth setup failed.")
    sys.exit(0)
