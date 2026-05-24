"""Notion writer for the Leads database (Web3Forms submissions).

Parallel pipeline to notion_writer — separate database, different schema. Reuses
the existing NOTION_TOKEN integration; that integration must be shared with the
Leads database.

Dedup key: Email + Received-day (UTC). Re-processing the same submission won't
create duplicate rows.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
from email.utils import parseaddr
from typing import Any

from notion_client import Client

from cloud.config import Settings

logger = logging.getLogger(__name__)

# Locked property names — must match the Leads database in Notion exactly.
_NAME_PROP = "Name"
_FIRST_NAME_PROP = "First Name"
_LAST_NAME_PROP = "Last Name"
_PHONE_PROP = "Phone"
_EMAIL_PROP = "Email"
_SERVICE_PROP = "Service"
_SOURCE_MARKET_PROP = "Source Market"
_EVENT_DATE_PROP = "Event Date"
_HEADCOUNT_PROP = "Headcount"
_HEARD_ABOUT_PROP = "Heard About"
_MESSAGE_PROP = "Message"
_LEAD_QUALITY_PROP = "Lead Quality"
_STATUS_PROP = "Status"
_SOURCE_URL_PROP = "Source URL"

_SERVICE_VALUES = {"Private Chef", "Meal Prep", "Catering", "Homepage / General", "Other"}
_LEAD_QUALITY_VALUES = {"Genuine", "Sales / Solicitation", "Unsure", "Job Application"}

_RICH_TEXT_MAX = 1900


def _client(settings: Settings) -> Client:
    return Client(auth=settings.notion_token)


def _rich(content: str | None) -> dict:
    return {"rich_text": [{"text": {"content": (content or "")[:_RICH_TEXT_MAX]}}]}


def _select_or_none(name: str | None, allowed: set[str]) -> dict | None:
    if not name or name not in allowed:
        return None
    return {"select": {"name": name}}


def _date_prop(value: str | None) -> dict | None:
    if not value:
        return None
    try:
        dt.date.fromisoformat(value[:10])
    except ValueError:
        return None
    return {"date": {"start": value[:10]}}


def _resolve_email(msg: dict[str, Any]) -> str | None:
    """Reply-To is authoritative; From is always notify@web3forms.com for Web3Forms."""
    raw = msg.get("reply_to") or ""
    _, addr = parseaddr(raw)
    if addr:
        return addr
    return None


def _coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        try:
            return int(float(s))
        except ValueError:
            return None
    return None


def _compose_name(first: str | None, last: str | None) -> str:
    parts = [(first or "").strip(), (last or "").strip()]
    name = " ".join(p for p in parts if p)
    return name or "(unknown)"


async def is_duplicate_lead(
    settings: Settings, *, email: str, received_at: dt.datetime
) -> bool:
    """Skip if a Leads row with the same Email + same Received-day (UTC) already exists."""
    if not email:
        return False
    day_start = received_at.astimezone(dt.timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    day_end = day_start + dt.timedelta(days=1)

    def _query() -> dict:
        client = _client(settings)
        return client.databases.query(
            database_id=settings.notion_leads_database_id,
            filter={
                "and": [
                    {"property": _EMAIL_PROP, "email": {"equals": email}},
                    {
                        "timestamp": "created_time",
                        "created_time": {"on_or_after": day_start.isoformat()},
                    },
                    {
                        "timestamp": "created_time",
                        "created_time": {"before": day_end.isoformat()},
                    },
                ]
            },
            page_size=5,
        )

    try:
        resp = await asyncio.to_thread(_query)
    except Exception:
        logger.exception("notion lead dedup query failed; treating as non-duplicate")
        return False
    return bool(resp.get("results"))


async def write_lead(
    settings: Settings, *, msg: dict[str, Any], extracted: dict[str, Any]
) -> dict[str, str]:
    """Create a Notion page in the Leads database.

    Returns a dict with ``id`` (page UUID) and ``url`` (canonical Notion URL).
    """
    first = (extracted.get("first_name") or "").strip() or None
    last = (extracted.get("last_name") or "").strip() or None
    title = _compose_name(first, last)
    email = _resolve_email(msg)

    properties: dict[str, Any] = {
        _NAME_PROP: {"title": [{"text": {"content": title[:200]}}]},
        _STATUS_PROP: {"select": {"name": "New"}},
    }
    if first:
        properties[_FIRST_NAME_PROP] = _rich(first)
    if last:
        properties[_LAST_NAME_PROP] = _rich(last)

    phone = (extracted.get("phone") or "").strip()
    if phone:
        properties[_PHONE_PROP] = {"phone_number": phone}

    if email:
        properties[_EMAIL_PROP] = {"email": email}

    service = _select_or_none(extracted.get("service"), _SERVICE_VALUES)
    if service:
        properties[_SERVICE_PROP] = service

    source_market = (extracted.get("source_market") or "").strip()
    if source_market:
        properties[_SOURCE_MARKET_PROP] = _rich(source_market)

    event_date = _date_prop(extracted.get("event_date"))
    if event_date:
        properties[_EVENT_DATE_PROP] = event_date

    headcount = _coerce_int(extracted.get("headcount"))
    if headcount is not None:
        properties[_HEADCOUNT_PROP] = {"number": headcount}

    heard_about = (extracted.get("heard_about") or "").strip()
    if heard_about:
        properties[_HEARD_ABOUT_PROP] = _rich(heard_about)

    message = (extracted.get("message") or "").strip()
    if message:
        properties[_MESSAGE_PROP] = _rich(message)

    quality = _select_or_none(extracted.get("lead_quality"), _LEAD_QUALITY_VALUES)
    if quality:
        properties[_LEAD_QUALITY_PROP] = quality

    source_url = (extracted.get("source_url") or "").strip()
    if source_url.startswith(("http://", "https://")):
        properties[_SOURCE_URL_PROP] = {"url": source_url}

    def _create() -> dict:
        client = _client(settings)
        return client.pages.create(
            parent={"database_id": settings.notion_leads_database_id},
            properties=properties,
        )

    page = await asyncio.to_thread(_create)
    return {"id": page["id"], "url": page.get("url", "")}
