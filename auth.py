import os
import json
import tempfile
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

load_dotenv()

SCOPES        = ["https://www.googleapis.com/auth/calendar"]
TOKEN_PATH    = os.getenv("GOOGLE_TOKEN_PATH", "./token.json")
S3_BUCKET     = os.getenv("TOKEN_S3_BUCKET")
S3_KEY        = os.getenv("TOKEN_S3_KEY", "token.json")
USE_S3        = bool(S3_BUCKET)


def _get_credentials_path() -> str:
    """
    In production: load credentials.json from Secrets Manager,
    write to a temp file and return the path.
    In local dev: use the file path from env/default.
    """
    secret_name = os.getenv("GOOGLE_CREDS_SECRET")
    if secret_name:
        try:
            import boto3
            client = boto3.client(
                "secretsmanager",
                region_name=os.getenv("AWS_REGION", "us-east-1")
            )
            secret = client.get_secret_value(SecretId=secret_name)
            # Write to a temp file — InstalledAppFlow expects a file path
            tmp = tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False
            )
            tmp.write(secret["SecretString"])
            tmp.close()
            print(f"[auth] Loaded Google credentials from Secrets Manager")
            return tmp.name
        except Exception as e:
            print(f"[auth] Warning: could not load credentials from Secrets Manager: {e}")

    return os.getenv("GOOGLE_CREDENTIALS_PATH", "./credentials.json")


def _load_token() -> dict | None:
    if USE_S3:
        try:
            import boto3
            s3 = boto3.client("s3")
            obj = s3.get_object(Bucket=S3_BUCKET, Key=S3_KEY)
            return json.loads(obj["Body"].read())
        except Exception:
            return None
    if os.path.exists(TOKEN_PATH):
        with open(TOKEN_PATH) as f:
            return json.load(f)
    return None


def _save_token(creds: Credentials):
    token_data = creds.to_json()
    if USE_S3:
        import boto3
        boto3.client("s3").put_object(
            Bucket=S3_BUCKET, Key=S3_KEY, Body=token_data
        )
        print(f"[auth] Token saved to s3://{S3_BUCKET}/{S3_KEY}")
    else:
        with open(TOKEN_PATH, "w") as f:
            f.write(token_data)
        print(f"[auth] Token saved to {TOKEN_PATH}")


def get_credentials() -> Credentials:
    creds = None
    token_data = _load_token()

    if token_data:
        creds = Credentials.from_authorized_user_info(token_data, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("[auth] Refreshing expired token...")
            creds.refresh(Request())
            _save_token(creds)
        else:
            # In production this path should never be hit —
            # token.json must be in S3 before first deploy
            print("[auth] Running OAuth flow (local only)...")
            credentials_path = _get_credentials_path()
            flow = InstalledAppFlow.from_client_secrets_file(
                credentials_path, SCOPES
            )
            creds = flow.run_local_server(port=0)
            _save_token(creds)
    else:
        print("[auth] Using valid cached token")

    return creds


if __name__ == "__main__":
    creds = get_credentials()
    print("Auth successful!")