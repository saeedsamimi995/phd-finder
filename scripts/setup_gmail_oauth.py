"""One-time Gmail OAuth setup for saeedsamimi995@gmail.com.

Does NOT use your Google password. You need a Desktop OAuth client JSON from
Google Cloud Console saved as config/gmail_credentials.json first.

Steps this script expects you already did:
  1. https://console.cloud.google.com/ → create/select a project
  2. Enable "Gmail API"
  3. APIs & Services → OAuth consent screen (External, add your Gmail as test user)
  4. Credentials → Create credentials → OAuth client ID → Desktop app → Download JSON
  5. Save that file as: config/gmail_credentials.json

Then run:
  .\\.venv\\Scripts\\python.exe scripts\\setup_gmail_oauth.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from phd_finder.apply.gmail import _credentials_path, _token_path, get_service, gmail_ready


def main() -> int:
    creds = _credentials_path()
    if not creds.exists():
        print("Missing OAuth client file:")
        print(f"  {creds}")
        print()
        print("Create a Desktop OAuth client in Google Cloud Console, download the JSON,")
        print("and save it exactly at that path. Your Gmail password is NOT used here.")
        print("Guide: https://console.cloud.google.com/apis/credentials")
        return 1
    print(f"Found client JSON: {creds}")
    print("Opening browser for Google sign-in (use saeedsamimi995@gmail.com)...")
    # get_service() runs the browser flow if needed and persists data/gmail_token.json.
    # We only request gmail.send, so we cannot call users.getProfile (needs broader scopes).
    service = get_service()
    _ = service  # constructed successfully
    token = _token_path()
    print(f"OK — Gmail send token ready at {token}")
    print("Sender will be saeedsamimi995@gmail.com (GMAIL_SENDER in .env).")
    return 0


if __name__ == "__main__":
    if not gmail_ready():
        # gmail_ready only checks client JSON; message handled in main
        pass
    raise SystemExit(main())
