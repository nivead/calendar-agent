import os
import json
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

load_dotenv()

SCOPES = ["https://www.googleapis.com/auth/calendar"]
CREDENTIALS_PATH = os.getenv("GOOGLE_CREDENTIALS_PATH", "./credentials.json")
TOKEN_PATH = os.getenv("GOOGLE_TOKEN_PATH", "./token.json")


def get_credentials() -> Credentials:
    creds = None

    # If a saved token exists, load it
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    # If no valid credentials, run the OAuth flow
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Refreshing expired token...")
            creds.refresh(Request())
        else:
            print("Opening browser for Google login...")
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)

        # Save for next time
        with open(TOKEN_PATH, "w") as f:
            f.write(creds.to_json())
        print(f"Token saved to {TOKEN_PATH}")

    return creds


if __name__ == "__main__":
    creds = get_credentials()
    print("Auth successful! You're ready to go.")
