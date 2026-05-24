"""Env var loading and validation. Fails loudly if a required var is missing."""

from __future__ import annotations

import os
from dataclasses import dataclass

ANTHROPIC_MODEL = "claude-sonnet-4-6"

GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
CALENDAR_SCOPES = ["https://www.googleapis.com/auth/calendar.events.owned"]
# The refresh token in Railway must be minted covering BOTH scopes — see
# forwarder/get_refresh_token.py. Each module uses only the scope it needs.
GMAIL_POLL_INTERVAL_SECONDS = 15 * 60

CALENDAR_EVENT_DURATION_MINUTES = 15
CALENDAR_DEFAULT_TIMEZONE = "America/Denver"

WORKER_BATCH_SIZE = 10
WORKER_POLL_INTERVAL_SECONDS = 5

DIGEST_LOCAL_HOUR = 8
DIGEST_TIMEZONE = "America/Denver"

DEDUP_WINDOW_DAYS = 7
WEBHOOK_REPLAY_WINDOW_SECONDS = 300


@dataclass(frozen=True)
class Settings:
    database_url: str
    notion_token: str
    notion_database_id: str
    notion_leads_database_id: str
    anthropic_api_key: str
    gmail_client_id: str
    gmail_client_secret: str
    gmail_refresh_token: str
    resend_api_key: str
    digest_recipient: str
    digest_from: str
    forwarder_secret: str
    prompt_version: str
    log_level: str


_REQUIRED = (
    "DATABASE_URL",
    "NOTION_TOKEN",
    "NOTION_DATABASE_ID",
    "NOTION_LEADS_DATABASE_ID",
    "ANTHROPIC_API_KEY",
    "GMAIL_CLIENT_ID",
    "GMAIL_CLIENT_SECRET",
    "GMAIL_REFRESH_TOKEN",
    "RESEND_API_KEY",
    "DIGEST_RECIPIENT",
    "FORWARDER_SECRET",
)


def load_settings() -> Settings:
    missing = [k for k in _REQUIRED if not os.environ.get(k)]
    if missing:
        raise RuntimeError("Missing required environment variables: " + ", ".join(missing))
    return Settings(
        database_url=os.environ["DATABASE_URL"],
        notion_token=os.environ["NOTION_TOKEN"],
        notion_database_id=os.environ["NOTION_DATABASE_ID"],
        notion_leads_database_id=os.environ["NOTION_LEADS_DATABASE_ID"],
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
        gmail_client_id=os.environ["GMAIL_CLIENT_ID"],
        gmail_client_secret=os.environ["GMAIL_CLIENT_SECRET"],
        gmail_refresh_token=os.environ["GMAIL_REFRESH_TOKEN"],
        resend_api_key=os.environ["RESEND_API_KEY"],
        digest_recipient=os.environ["DIGEST_RECIPIENT"],
        digest_from=os.environ.get("DIGEST_FROM", "onboarding@resend.dev"),
        forwarder_secret=os.environ["FORWARDER_SECRET"],
        prompt_version=os.environ.get("PROMPT_VERSION", "v1"),
        log_level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    )
