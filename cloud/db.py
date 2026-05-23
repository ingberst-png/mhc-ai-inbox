"""Postgres schema, queue, and state helpers (psycopg 3 async)."""

from __future__ import annotations

import datetime as dt
import json
import logging
from typing import Any

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

logger = logging.getLogger(__name__)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS messages (
    id                 BIGSERIAL PRIMARY KEY,
    source             TEXT NOT NULL CHECK (source IN ('gmail','imessage')),
    external_id        TEXT NOT NULL,
    sender             TEXT NOT NULL,
    subject            TEXT,
    body               TEXT NOT NULL,
    received_at        TIMESTAMPTZ NOT NULL,
    original_link      TEXT,
    status             TEXT NOT NULL DEFAULT 'queued'
                       CHECK (status IN ('queued','processing','done','skipped','failed')),
    claude_response    JSONB,
    notion_page_id     TEXT,
    calendar_event_id  TEXT,
    error              TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (source, external_id)
);

-- Idempotent migration for deployments that pre-date the calendar feature.
ALTER TABLE messages ADD COLUMN IF NOT EXISTS calendar_event_id TEXT;

CREATE INDEX IF NOT EXISTS messages_status_received_idx
    ON messages (status, received_at);

CREATE TABLE IF NOT EXISTS state (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


_pool: AsyncConnectionPool | None = None


async def init_pool(dsn: str) -> AsyncConnectionPool:
    global _pool
    _pool = AsyncConnectionPool(
        dsn,
        min_size=1,
        max_size=5,
        open=False,
        kwargs={"row_factory": dict_row},
    )
    await _pool.open()
    async with _pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(SCHEMA_SQL)
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def pool() -> AsyncConnectionPool:
    if _pool is None:
        raise RuntimeError("DB pool not initialized; call init_pool() first")
    return _pool


async def enqueue_message(
    *,
    source: str,
    external_id: str,
    sender: str,
    subject: str | None,
    body: str,
    received_at: dt.datetime,
    original_link: str | None,
) -> int | None:
    """Insert a new message. Returns id, or None if (source, external_id) already exists."""
    async with pool().connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO messages
                    (source, external_id, sender, subject, body, received_at, original_link)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (source, external_id) DO NOTHING
                RETURNING id
                """,
                (source, external_id, sender, subject, body, received_at, original_link),
            )
            row = await cur.fetchone()
            return row["id"] if row else None


async def claim_batch(limit: int = 10) -> list[dict[str, Any]]:
    """Claim up to `limit` queued messages, marking them 'processing' atomically."""
    async with pool().connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                WITH next AS (
                    SELECT id FROM messages
                    WHERE status = 'queued'
                    ORDER BY received_at
                    LIMIT %s
                    FOR UPDATE SKIP LOCKED
                )
                UPDATE messages
                   SET status = 'processing', updated_at = NOW()
                  FROM next
                 WHERE messages.id = next.id
                RETURNING messages.*
                """,
                (limit,),
            )
            return await cur.fetchall()


async def mark_done(message_id: int, *, claude_response: dict, notion_page_id: str | None) -> None:
    async with pool().connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                UPDATE messages
                   SET status='done', claude_response=%s, notion_page_id=%s,
                       error=NULL, updated_at=NOW()
                 WHERE id=%s
                """,
                (json.dumps(claude_response), notion_page_id, message_id),
            )


async def mark_skipped(message_id: int, *, claude_response: dict | None, reason: str) -> None:
    async with pool().connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                UPDATE messages
                   SET status='skipped', claude_response=%s, error=%s, updated_at=NOW()
                 WHERE id=%s
                """,
                (json.dumps(claude_response) if claude_response else None, reason, message_id),
            )


async def mark_failed(message_id: int, *, error: str) -> None:
    async with pool().connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE messages SET status='failed', error=%s, updated_at=NOW() WHERE id=%s",
                (error, message_id),
            )


async def set_calendar_event_id(message_id: int, event_id: str) -> None:
    """Record a Google Calendar event ID against a previously-processed message.

    Separate from mark_done() because the calendar write is best-effort and
    happens *after* the message is already in 'done' status (Notion-side).
    Does not change status or updated_at semantics.
    """
    async with pool().connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE messages SET calendar_event_id=%s WHERE id=%s",
                (event_id, message_id),
            )


async def queue_depth() -> int:
    async with pool().connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT COUNT(*) AS n FROM messages WHERE status='queued'")
            row = await cur.fetchone()
            return int(row["n"])


async def last_processed_at(source: str) -> dt.datetime | None:
    async with pool().connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT MAX(updated_at) AS t FROM messages
                 WHERE source=%s AND status IN ('done','skipped')
                """,
                (source,),
            )
            row = await cur.fetchone()
            return row["t"]


async def get_state(key: str) -> str | None:
    async with pool().connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT value FROM state WHERE key=%s", (key,))
            row = await cur.fetchone()
            return row["value"] if row else None


async def set_state(key: str, value: str) -> None:
    async with pool().connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO state (key, value, updated_at) VALUES (%s, %s, NOW())
                ON CONFLICT (key) DO UPDATE
                  SET value = EXCLUDED.value, updated_at = NOW()
                """,
                (key, value),
            )


# Sanity check: `python -m cloud.db --check`
if __name__ == "__main__":
    import asyncio
    import sys

    from cloud.config import load_settings

    async def _check() -> None:
        s = load_settings()
        await init_pool(s.database_url)
        async with pool().connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT table_name FROM information_schema.tables
                     WHERE table_schema='public'
                     ORDER BY table_name
                    """
                )
                tables = [r["table_name"] for r in await cur.fetchall()]
        print("tables:", tables)
        print("queue depth:", await queue_depth())
        print("gmail last poll:", await get_state("gmail_last_poll_at"))
        await close_pool()

    if "--check" in sys.argv:
        asyncio.run(_check())
    else:
        print("Usage: python -m cloud.db --check")
        sys.exit(1)
