"""FastAPI entrypoint: wires DB, webhook, Gmail poller, Claude worker, and digest."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from cloud.claude_worker import run_worker_loop
from cloud.config import load_settings
from cloud.db import close_pool, get_state, init_pool, last_processed_at, queue_depth
from cloud.digest import run_digest_loop
from cloud.gmail_poller import run_poll_loop
from cloud.webhook import build_router

settings = load_settings()

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_pool(settings.database_url)
    stop_event = asyncio.Event()
    tasks = [
        asyncio.create_task(run_poll_loop(settings, stop_event), name="gmail-poller"),
        asyncio.create_task(run_worker_loop(settings, stop_event), name="claude-worker"),
        asyncio.create_task(run_digest_loop(settings, stop_event), name="digest"),
    ]
    logger.info("startup complete: 3 background tasks running")
    try:
        yield
    finally:
        stop_event.set()
        for t in tasks:
            t.cancel()
        for t in tasks:
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass
        await close_pool()
        logger.info("shutdown complete")


app = FastAPI(title="MHC AI Inbox", lifespan=lifespan)
app.include_router(build_router(settings))


def _iso(value) -> str | None:
    return value.isoformat() if value else None


@app.get("/health")
async def health() -> dict:
    return {
        "ok": True,
        "queue_depth": await queue_depth(),
        "last_gmail_processed": _iso(await last_processed_at("gmail")),
        "last_imessage_processed": _iso(await last_processed_at("imessage")),
        "last_gmail_poll": await get_state("gmail_last_poll_at"),
        "last_digest_sent": await get_state("last_digest_sent_at"),
    }
