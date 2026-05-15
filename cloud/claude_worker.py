"""Background worker: dequeues messages, calls Claude Sonnet 4.6, routes to Notion."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any

from anthropic import AsyncAnthropic

from cloud.config import (
    ANTHROPIC_MODEL,
    Settings,
    WORKER_BATCH_SIZE,
    WORKER_POLL_INTERVAL_SECONDS,
)
from cloud.db import claim_batch, mark_done, mark_failed, mark_skipped
from cloud.notion_writer import (
    fetch_recent_feedback_examples,
    is_duplicate,
    write_action_item,
)

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent / "prompts" / "system_prompt.md"
_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _load_system_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


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


async def _process_message(
    client: AsyncAnthropic,
    settings: Settings,
    system_prompt: str,
    msg: dict[str, Any],
) -> None:
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
        page_id = await write_action_item(settings, msg=msg, extracted=result)
    except Exception as e:
        logger.exception("notion write failed for msg %s", msg["id"])
        await mark_failed(msg["id"], error=f"notion write: {e}")
        return
    await mark_done(msg["id"], claude_response=result, notion_page_id=page_id)


async def run_worker_loop(settings: Settings, stop_event: asyncio.Event) -> None:
    logger.info("claude worker starting (batch=%d, model=%s)", WORKER_BATCH_SIZE, ANTHROPIC_MODEL)
    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    template = _load_system_prompt()
    while not stop_event.is_set():
        try:
            batch = await claim_batch(WORKER_BATCH_SIZE)
        except Exception:
            logger.exception("worker claim_batch failed")
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
            *(_process_message(client, settings, system_prompt, m) for m in batch)
        )
    logger.info("claude worker stopped")
