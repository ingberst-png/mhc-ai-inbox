"""Notion page creation, dedup against the last 7 days, and feedback-example retrieval."""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
from typing import Any

from notion_client import Client

from cloud.config import DEDUP_WINDOW_DAYS, Settings

logger = logging.getLogger(__name__)

_TITLE_PROP = "Title"
_SOURCE_PROP = "Source"
_SENDER_PROP = "Sender"
_SNIPPET_PROP = "Snippet"
_ACTION_PROP = "Suggested Action"
_DUE_PROP = "Due Date"
_PRIORITY_PROP = "Priority"
_CONFIDENCE_PROP = "Confidence"
_FEEDBACK_PROP = "Feedback"
_LINK_PROP = "Original Link"
_STATUS_PROP = "Status"

_SNIPPET_LEN = 200
_RICH_TEXT_MAX = 1900


def _client(settings: Settings) -> Client:
    return Client(auth=settings.notion_token)


def _snippet(body: str) -> str:
    return (body or "")[:_SNIPPET_LEN]


def _plain(prop: dict | None) -> str:
    if not prop:
        return ""
    for key in ("rich_text", "title"):
        if key in prop:
            return "".join(r.get("plain_text", "") for r in prop[key])
    if "select" in prop and prop["select"]:
        return prop["select"].get("name", "") or ""
    return ""


async def is_duplicate(settings: Settings, *, sender: str, body: str) -> bool:
    """Match if a same-Sender entry created within DEDUP_WINDOW_DAYS shares our 200-char Snippet."""
    target = _snippet(body)
    if not target:
        return False
    cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=DEDUP_WINDOW_DAYS)).isoformat()

    def _query() -> dict:
        client = _client(settings)
        return client.databases.query(
            database_id=settings.notion_database_id,
            filter={
                "and": [
                    {"property": _SENDER_PROP, "rich_text": {"equals": sender}},
                    {"timestamp": "created_time", "created_time": {"on_or_after": cutoff}},
                ]
            },
            page_size=25,
        )

    try:
        resp = await asyncio.to_thread(_query)
    except Exception:
        logger.exception("notion dedup query failed; treating as non-duplicate")
        return False

    for page in resp.get("results", []):
        props = page.get("properties", {})
        existing_snippet = _plain(props.get(_SNIPPET_PROP))
        if existing_snippet[:_SNIPPET_LEN] == target:
            return True
    return False


def _date_prop(value: str | None) -> dict | None:
    if not value:
        return None
    try:
        dt.date.fromisoformat(value[:10])
    except ValueError:
        return None
    return {"date": {"start": value[:10]}}


def _select_or_none(name: str | None, allowed: set[str]) -> dict | None:
    if not name or name not in allowed:
        return None
    return {"select": {"name": name}}


def _rich(content: str) -> dict:
    return {"rich_text": [{"text": {"content": content[:_RICH_TEXT_MAX]}}]}


async def write_action_item(
    settings: Settings, *, msg: dict[str, Any], extracted: dict[str, Any]
) -> str:
    title = (extracted.get("title") or msg.get("subject") or "(untitled)").strip()[:200]
    source = "Gmail" if msg["source"] == "gmail" else "iMessage"
    sender = extracted.get("sender") or msg["sender"]
    snippet = (extracted.get("snippet") or _snippet(msg["body"])).strip()
    suggested_action = (extracted.get("suggested_action") or "").strip()

    confidence_raw = extracted.get("confidence")
    try:
        confidence = max(0.0, min(1.0, float(confidence_raw)))
    except (TypeError, ValueError):
        confidence = 0.0

    properties: dict[str, Any] = {
        _TITLE_PROP: {"title": [{"text": {"content": title}}]},
        _SOURCE_PROP: {"select": {"name": source}},
        _SENDER_PROP: _rich(sender),
        _SNIPPET_PROP: _rich(snippet),
        _ACTION_PROP: _rich(suggested_action),
        _CONFIDENCE_PROP: {"number": confidence},
        _STATUS_PROP: {"select": {"name": "New"}},
    }
    if msg.get("original_link"):
        properties[_LINK_PROP] = {"url": msg["original_link"]}
    pr = _select_or_none(extracted.get("priority"), {"High", "Medium", "Low"})
    if pr:
        properties[_PRIORITY_PROP] = pr
    due = _date_prop(extracted.get("due_date"))
    if due:
        properties[_DUE_PROP] = due

    def _create() -> dict:
        client = _client(settings)
        return client.pages.create(
            parent={"database_id": settings.notion_database_id},
            properties=properties,
        )

    page = await asyncio.to_thread(_create)
    return page["id"]


async def fetch_recent_feedback_examples(
    settings: Settings, *, limit: int = 15
) -> list[dict[str, Any]]:
    """Most recent items with any Feedback label, returned oldest -> newest."""

    def _query() -> dict:
        client = _client(settings)
        return client.databases.query(
            database_id=settings.notion_database_id,
            filter={"property": _FEEDBACK_PROP, "select": {"is_not_empty": True}},
            sorts=[{"timestamp": "created_time", "direction": "descending"}],
            page_size=limit,
        )

    try:
        resp = await asyncio.to_thread(_query)
    except Exception:
        logger.exception("notion feedback fetch failed; using empty set")
        return []
    out = []
    for page in resp.get("results", []):
        props = page.get("properties", {})
        out.append(
            {
                "title": _plain(props.get(_TITLE_PROP)),
                "source": _plain(props.get(_SOURCE_PROP)),
                "sender": _plain(props.get(_SENDER_PROP)),
                "snippet": _plain(props.get(_SNIPPET_PROP)),
                "feedback": _plain(props.get(_FEEDBACK_PROP)),
            }
        )
    return list(reversed(out))


async def query_recent_items(settings: Settings, *, hours: int) -> list[dict[str, Any]]:
    """For the digest: every page created in the last `hours`."""
    cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours)).isoformat()

    def _query() -> dict:
        client = _client(settings)
        return client.databases.query(
            database_id=settings.notion_database_id,
            filter={"timestamp": "created_time", "created_time": {"on_or_after": cutoff}},
            sorts=[{"timestamp": "created_time", "direction": "descending"}],
            page_size=100,
        )

    resp = await asyncio.to_thread(_query)
    out = []
    for page in resp.get("results", []):
        props = page.get("properties", {})
        out.append(
            {
                "url": page.get("url"),
                "title": _plain(props.get(_TITLE_PROP)),
                "source": _plain(props.get(_SOURCE_PROP)),
                "sender": _plain(props.get(_SENDER_PROP)),
                "suggested_action": _plain(props.get(_ACTION_PROP)),
                "priority": _plain(props.get(_PRIORITY_PROP)),
                "confidence": (props.get(_CONFIDENCE_PROP) or {}).get("number"),
            }
        )
    return out
