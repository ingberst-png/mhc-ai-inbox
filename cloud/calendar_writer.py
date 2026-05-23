"""Google Calendar event creation for confirmed meetings.

Best-effort: a failure here is logged and swallowed by the worker so the
Notion write isn't blocked. Reuses the Gmail OAuth refresh token — the
token must be minted covering both ``gmail.readonly`` and
``calendar.events.owned`` scopes (see forwarder/get_refresh_token.py).
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
from zoneinfo import ZoneInfo

from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from cloud.config import (
    CALENDAR_DEFAULT_TIMEZONE,
    CALENDAR_EVENT_DURATION_MINUTES,
    CALENDAR_SCOPES,
    Settings,
)

logger = logging.getLogger(__name__)


def _credentials(settings: Settings) -> Credentials:
    return Credentials(
        token=None,
        refresh_token=settings.gmail_refresh_token,
        client_id=settings.gmail_client_id,
        client_secret=settings.gmail_client_secret,
        token_uri="https://oauth2.googleapis.com/token",
        scopes=CALENDAR_SCOPES,
    )


def _build_service(settings: Settings):
    creds = _credentials(settings)
    creds.refresh(GoogleRequest())
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def parse_meeting_time(value: str | None) -> dt.datetime | None:
    """Parse an ISO 8601 string from Claude's output into a tz-aware datetime.

    Accepts:
      - ``2026-05-20T14:00:00-06:00`` (offset present, used as-is)
      - ``2026-05-20T14:00:00Z`` (Z -> UTC)
      - ``2026-05-20T14:00:00`` (naive -> assume America/Denver)

    Returns None if the value is missing or unparseable.
    """
    if not value or not isinstance(value, str):
        return None
    s = value.strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(s)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo(CALENDAR_DEFAULT_TIMEZONE))
    return parsed


def _build_description(*, snippet: str, notion_url: str | None, gmail_link: str | None) -> str:
    parts: list[str] = []
    snippet_clean = (snippet or "").strip()
    if snippet_clean:
        parts.append(snippet_clean)
    if notion_url:
        parts.append(f"Notion: {notion_url}")
    if gmail_link:
        parts.append(f"Gmail: {gmail_link}")
    return "\n\n".join(parts)


async def create_event(
    settings: Settings,
    *,
    name: str,
    meeting_time: dt.datetime,
    snippet: str,
    notion_url: str | None,
    gmail_link: str | None,
) -> str:
    """Create a 15-minute event on the primary calendar. Returns the event ID."""
    if meeting_time.tzinfo is None:
        meeting_time = meeting_time.replace(tzinfo=ZoneInfo(CALENDAR_DEFAULT_TIMEZONE))
    end = meeting_time + dt.timedelta(minutes=CALENDAR_EVENT_DURATION_MINUTES)
    summary = f"{(name or 'Unknown').strip()} - Lead"
    description = _build_description(
        snippet=snippet, notion_url=notion_url, gmail_link=gmail_link
    )
    body = {
        "summary": summary,
        "description": description,
        "start": {"dateTime": meeting_time.isoformat()},
        "end": {"dateTime": end.isoformat()},
        # No attendees — event is for Steve only; do not send invites.
    }

    def _insert() -> dict:
        service = _build_service(settings)
        return service.events().insert(calendarId="primary", body=body).execute()

    event = await asyncio.to_thread(_insert)
    return event["id"]
