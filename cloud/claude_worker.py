"""Background worker: dequeues messages, calls Claude Sonnet 4.6, routes to Notion."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from email.utils import parseaddr
from pathlib import Path
from typing import Any

from anthropic import AsyncAnthropic

from cloud.calendar_writer import create_event, parse_meeting_time
from cloud.config import (
    ANTHROPIC_MODEL,
    Settings,
    WORKER_BATCH_SIZE,
    WORKER_POLL_INTERVAL_SECONDS,
)
from cloud.db import (
    claim_batch,
    mark_done,
    mark_failed,
    mark_skipped,
    set_calendar_event_id,
)
from cloud.lead_writer import is_duplicate_lead, write_lead
from cloud.notion_writer import (
    fetch_recent_feedback_examples,
    is_duplicate,
    write_action_item,
)

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent / "prompts" / "system_prompt.md"
_LEAD_PROMPT_PATH = Path(__file__).parent / "prompts" / "lead_prompt.md"
_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)

_WEB3FORMS_SENDER = "notify@web3forms.com"


def _load_system_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _load_lead_prompt() -> str:
    return _LEAD_PROMPT_PATH.read_text(encoding="utf-8")


def _is_web3forms_lead(msg: dict[str, Any]) -> bool:
    if msg.get("source") != "gmail":
        return False
    _, addr = parseaddr(msg.get("sender") or "")
    return addr.lower() == _WEB3FORMS_SENDER


def _format_examples(examples: list[dict[str, Any]]) -> str:
    if not examples:
        return "(no labeled feedback examples available yet)"
    lines = []
    for e in examples:
        label = e.get("feedback") or "?"
        title = e.get("title") or ""
        sender = e.get("sender") or ""
        snippet = (e.get("snippet") or "")[:200]
        lines.append(
            f"- Feedback: {label}\n  Title: {title}\n  Sender: {sender}\n  Snippet: {snippet}"
        )
    return "\n".join(lines)


def _build_system_prompt(template: str, examples: list[dict[str, Any]]) -> str:
    return template.replace("{{FEEDBACK_EXAMPLES}}", _format_examples(examples))


def _build_user_message(msg: dict[str, Any]) -> str:
    parts = [
        f"Source: {msg['source']}",
        f"Sender: {msg['sender']}",
        f"Received: {msg['received_at'].isoformat()}",
    ]
    if msg.get("subject"):
        parts.append(f"Subject: {msg['subject']}")
    parts.append("Body:")
    parts.append(msg["body"] or "")
    return "\n".join(parts)


def _build_lead_user_message(msg: dict[str, Any]) -> str:
    parts = [
        f"Subject: {msg.get('subject') or ''}",
        f"Received: {msg['received_at'].isoformat()}",
        "Body:",
        msg["body"] or "",
    ]
    return "\n".join(parts)


def _parse_json(text: str) -> dict[str, Any]:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = _JSON_FENCE_RE.search(text)
    if m:
        return json.loads(m.group(1))
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return json.loads(text[start : end + 1])
    raise ValueError("no JSON object found in model output")


async def _extract(
    client: AsyncAnthropic, system_prompt: str, msg: dict[str, Any]
) -> dict[str, Any]:
    resp = await client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=1024,
        system=system_prompt,
        messages=[{"role": "user", "content": _build_user_message(msg)}],
    )
    text = "".join(block.text for block in resp.content if block.type == "text")
    return _parse_json(text)


async def _extract_lead(
    client: AsyncAnthropic, lead_prompt: str, msg: dict[str, Any]
) -> dict[str, Any]:
    resp = await client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=1500,
        system=lead_prompt,
        messages=[{"role": "user", "content": _build_lead_user_message(msg)}],
    )
    text = "".join(block.text for block in resp.content if block.type == "text")
    return _parse_json(text)


async def _process_lead(
    client: AsyncAnthropic,
    settings: Settings,
    lead_prompt: str,
    msg: dict[str, Any],
) -> None:
    try:
        result = await _extract_lead(client, lead_prompt, msg)
    except Exception as e:
        logger.exception("claude lead extraction failed for msg %s", msg["id"])
        await mark_failed(msg["id"], error=f"lead extraction: {e}")
        return

    # Dedup against Leads DB: same Email + same Received-day (UTC).
    _, dedup_email = parseaddr(msg.get("reply_to") or "")
    try:
        duplicate = await is_duplicate_lead(
            settings, email=dedup_email, received_at=msg["received_at"]
        )
    except Exception:
        logger.exception("lead dedup query failed; proceeding without dedup")
        duplicate = False
    if duplicate:
        await mark_skipped(
            msg["id"],
            claude_response=result,
            reason="duplicate lead (Email + same received-day)",
        )
        return

    try:
        page = await write_lead(settings, msg=msg, extracted=result)
    except Exception as e:
        logger.exception("leads notion write failed for msg %s", msg["id"])
        await mark_failed(msg["id"], error=f"leads write: {e}")
        return
    await mark_done(msg["id"], claude_response=result, notion_page_id=page["id"])


async def _process_message(
    client: AsyncAnthropic,
    settings: Settings,
    system_prompt: str,
    lead_prompt: str,
    msg: dict[str, Any],
) -> None:
    # One email = one destination. Web3Forms leads bypass the action-item path
    # entirely — they go to the Leads DB only.
    if _is_web3forms_lead(msg):
        await _process_lead(client, settings, lead_prompt, msg)
        return

    try:
        result = await _extract(client, system_prompt, msg)
    except Exception as e:
        logger.exception("claude extraction failed for msg %s", msg["id"])
        await mark_failed(msg["id"], error=f"extraction: {e}")
        return

    if not result.get("is_action_item"):
        await mark_skipped(msg["id"], claude_response=result, reason="not an action item")
        return

    try:
        duplicate = await is_duplicate(settings, sender=msg["sender"], body=msg["body"])
    except Exception:
        logger.exception("notion dedup query failed; proceeding without dedup")
        duplicate = False
    if duplicate:
        await mark_skipped(msg["id"], claude_response=result, reason="duplicate (Notion 7-day match)")
        return

    try:
        page = await write_action_item(settings, msg=msg, extracted=result)
    except Exception as e:
        logger.exception("notion write failed for msg %s", msg["id"])
        await mark_failed(msg["id"], error=f"notion write: {e}")
        return
    await mark_done(msg["id"], claude_response=result, notion_page_id=page["id"])

    # Calendar event creation — best-effort, runs ONLY after the Notion write
    # already succeeded. A failure here never marks the message failed, since
    # the primary deliverable (the Notion row) is already safe.
    await _maybe_create_calendar_event(settings, msg=msg, extracted=result, notion_url=page.get("url"))


async def _maybe_create_calendar_event(
    settings: Settings,
    *,
    msg: dict[str, Any],
    extracted: dict[str, Any],
    notion_url: str | None,
) -> None:
    if not extracted.get("is_confirmed_meeting"):
        return
    meeting_time = parse_meeting_time(extracted.get("meeting_time"))
    if meeting_time is None:
        logger.info(
            "msg %s flagged is_confirmed_meeting but meeting_time missing/unparseable; skipping calendar",
            msg["id"],
        )
        return
    if msg.get("calendar_event_id"):
        logger.info("msg %s already has calendar_event_id; skipping", msg["id"])
        return
    name = extracted.get("sender") or msg.get("sender") or "Unknown"
    snippet = (extracted.get("snippet") or msg.get("body") or "").strip()[:200]
    gmail_link = msg.get("original_link") if msg.get("source") == "gmail" else None
    try:
        event_id = await create_event(
            settings,
            name=name,
            meeting_time=meeting_time,
            snippet=snippet,
            notion_url=notion_url,
            gmail_link=gmail_link,
        )
    except Exception:
        logger.exception("calendar event creation failed for msg %s (Notion row unaffected)", msg["id"])
        return
    try:
        await set_calendar_event_id(msg["id"], event_id)
        logger.info("msg %s: calendar event %s created at %s", msg["id"], event_id, meeting_time.isoformat())
    except Exception:
        logger.exception(
            "could not persist calendar_event_id=%s for msg %s; event exists in Calendar but DB lost it",
            event_id, msg["id"],
        )


async def run_worker_loop(settings: Settings, stop_event: asyncio.Event) -> None:
    logger.info("claude worker starting (batch=%d, model=%s)", WORKER_BATCH_SIZE, ANTHROPIC_MODEL)
    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    template = _load_system_prompt()
    lead_prompt = _load_lead_prompt()
    while not stop_event.is_set():
        try:
            batch = await claim_batch(WORKER_BATCH_SIZE)
        except Exception as e:
            # Include type + message on the headline line so Railway's
            # log viewer surfaces the cause even if it collapses the
            # traceback that logger.exception() appends.
            logger.exception(
                "worker claim_batch failed: %s: %s", type(e).__name__, e
            )
            await asyncio.sleep(WORKER_POLL_INTERVAL_SECONDS)
            continue
        if not batch:
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=WORKER_POLL_INTERVAL_SECONDS)
            except asyncio.TimeoutError:
                pass
            continue
        try:
            examples = await fetch_recent_feedback_examples(settings, limit=15)
        except Exception:
            logger.exception("failed to fetch feedback examples; using empty set")
            examples = []
        system_prompt = _build_system_prompt(template, examples)
        await asyncio.gather(
            *(_process_message(client, settings, system_prompt, lead_prompt, m) for m in batch)
        )
    logger.info("claude worker stopped")
