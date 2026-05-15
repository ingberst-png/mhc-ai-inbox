"""Gmail polling task. Filters automated/marketing mail before enqueueing."""

from __future__ import annotations

import asyncio
import base64
import datetime as dt
import logging
import re
from email.utils import parseaddr

from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from cloud.config import GMAIL_POLL_INTERVAL_SECONDS, GMAIL_SCOPES, Settings
from cloud.db import enqueue_message, set_state

logger = logging.getLogger(__name__)

GMAIL_QUERY = "newer_than:1d -in:sent -in:chats -in:spam -in:trash"

# Local-part substring patterns flagged as automated.
_NOREPLY_TOKENS = (
    "noreply",
    "no-reply",
    "donotreply",
    "do-not-reply",
    "notifications",
    "notification",
    "mailer-daemon",
)
_MARKETING_TOKENS = ("newsletter", "marketing", "promo", "offers", "deals", "campaigns")


def _credentials(settings: Settings) -> Credentials:
    return Credentials(
        token=None,
        refresh_token=settings.gmail_refresh_token,
        client_id=settings.gmail_client_id,
        client_secret=settings.gmail_client_secret,
        token_uri="https://oauth2.googleapis.com/token",
        scopes=GMAIL_SCOPES,
    )


def _build_service(settings: Settings):
    creds = _credentials(settings)
    creds.refresh(GoogleRequest())
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def _header(headers: list[dict], name: str) -> str | None:
    name_lower = name.lower()
    for h in headers:
        if h.get("name", "").lower() == name_lower:
            return h.get("value")
    return None


def _is_automated(from_header: str | None, headers: list[dict]) -> tuple[bool, str | None]:
    if _header(headers, "List-Unsubscribe"):
        return True, "list-unsubscribe header"
    if _header(headers, "Precedence") in {"bulk", "list", "junk"}:
        return True, "precedence header"
    _, addr = parseaddr(from_header or "")
    local = addr.split("@", 1)[0].lower() if "@" in addr else addr.lower()
    for token in _NOREPLY_TOKENS:
        if token in local:
            return True, f"noreply pattern '{token}'"
    for token in _MARKETING_TOKENS:
        if re.search(rf"\b{re.escape(token)}\b", local):
            return True, f"marketing pattern '{token}'"
    return False, None


def _extract_body(payload: dict) -> str:
    def _walk(part: dict) -> str | None:
        mime = part.get("mimeType", "")
        data = (part.get("body") or {}).get("data")
        if mime == "text/plain" and data:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
        for sub in part.get("parts") or []:
            found = _walk(sub)
            if found:
                return found
        return None

    text = _walk(payload)
    if text:
        return text
    return payload.get("snippet") or ""


def _fetch_messages(service) -> list[dict]:
    resp = service.users().messages().list(userId="me", q=GMAIL_QUERY, maxResults=50).execute()
    ids = [m["id"] for m in resp.get("messages", [])]
    out: list[dict] = []
    for mid in ids:
        msg = service.users().messages().get(userId="me", id=mid, format="full").execute()
        out.append(msg)
    return out


async def _process_batch(settings: Settings) -> tuple[int, int]:
    """Returns (enqueued, skipped_filter)."""
    service = await asyncio.to_thread(_build_service, settings)
    messages = await asyncio.to_thread(_fetch_messages, service)
    enqueued = 0
    skipped = 0
    for m in messages:
        payload = m.get("payload", {}) or {}
        headers = payload.get("headers", []) or []
        from_header = _header(headers, "From")
        subject = _header(headers, "Subject") or ""
        automated, reason = _is_automated(from_header, headers)
        if automated:
            skipped += 1
            logger.debug("gmail filtered %s (%s)", m.get("id"), reason)
            continue
        body = _extract_body(payload)
        ts = dt.datetime.fromtimestamp(
            int(m["internalDate"]) / 1000, tz=dt.timezone.utc
        )
        thread_id = m.get("threadId") or m["id"]
        link = f"https://mail.google.com/mail/u/0/#inbox/{thread_id}"
        inserted = await enqueue_message(
            source="gmail",
            external_id=m["id"],
            sender=from_header or "unknown",
            subject=subject,
            body=body,
            received_at=ts,
            original_link=link,
        )
        if inserted is not None:
            enqueued += 1
    await set_state("gmail_last_poll_at", dt.datetime.now(dt.timezone.utc).isoformat())
    return enqueued, skipped


async def run_poll_loop(settings: Settings, stop_event: asyncio.Event) -> None:
    logger.info("gmail poller starting (interval=%ds)", GMAIL_POLL_INTERVAL_SECONDS)
    while not stop_event.is_set():
        try:
            enqueued, skipped = await _process_batch(settings)
            if enqueued or skipped:
                logger.info("gmail poll: enqueued=%d filtered=%d", enqueued, skipped)
        except Exception:
            logger.exception("gmail poll failed")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=GMAIL_POLL_INTERVAL_SECONDS)
        except asyncio.TimeoutError:
            continue
    logger.info("gmail poller stopped")
