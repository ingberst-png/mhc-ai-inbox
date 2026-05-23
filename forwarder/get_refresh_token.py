#!/usr/bin/env python3
"""One-time Google OAuth helper - mints a refresh token for the cloud agent.

Setup:
  1. In Google Cloud Console, create an OAuth 2.0 Client ID of type
     "Desktop app". Make sure the consent screen has BOTH of these scopes
     authorized:
        - https://www.googleapis.com/auth/gmail.readonly
        - https://www.googleapis.com/auth/calendar.events.owned
  2. Download the JSON file (commonly named credentials.json).
  3. Run:  python3 get_refresh_token.py path/to/credentials.json

The script opens a browser for consent, then prints GMAIL_CLIENT_ID,
GMAIL_CLIENT_SECRET, and GMAIL_REFRESH_TOKEN to stdout. Paste those three
values into Railway as environment variables for the cloud agent.

The same refresh token covers both Gmail and Calendar APIs. If you minted
a token before the calendar feature shipped, re-run this script to issue
a new token with both scopes; the old gmail-only token will stop working
for calendar writes but stay fine for gmail polls.

Run this locally, not on Railway - the OAuth flow needs a local browser
to complete the redirect.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
except ImportError:
    print("ERROR: google-auth-oauthlib is not installed.", file=sys.stderr)
    print("Install with:  pip install google-auth-oauthlib", file=sys.stderr)
    sys.exit(2)

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.events.owned",
]


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python3 get_refresh_token.py path/to/credentials.json", file=sys.stderr)
        return 2

    creds_path = Path(sys.argv[1]).expanduser()
    if not creds_path.is_file():
        print(f"ERROR: {creds_path} does not exist or is not a file.", file=sys.stderr)
        return 2

    flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")

    if not creds.refresh_token:
        print(
            "ERROR: no refresh_token returned. Revoke the app's access in your "
            "Google account and re-run so Google issues a fresh refresh token.",
            file=sys.stderr,
        )
        return 3

    raw = json.loads(creds_path.read_text(encoding="utf-8"))
    section = raw.get("installed") or raw.get("web") or {}

    print()
    print("=" * 64)
    print("Paste these into Railway as environment variables:")
    print("=" * 64)
    print(f"GMAIL_CLIENT_ID={section.get('client_id', '')}")
    print(f"GMAIL_CLIENT_SECRET={section.get('client_secret', '')}")
    print(f"GMAIL_REFRESH_TOKEN={creds.refresh_token}")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    sys.exit(main())
