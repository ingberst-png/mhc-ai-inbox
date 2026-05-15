"""iMessage webhook receiver with HMAC-SHA256 verification and a 5-minute replay window."""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import logging
import time

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from cloud.config import WEBHOOK_REPLAY_WINDOW_SECONDS, Settings
from cloud.db import enqueue_message

logger = logging.getLogger(__name__)


class IMessageItem(BaseModel):
    guid: str
    sender: str
    chat_name: str | None = None
    body: str
    received_at: dt.datetime


class WebhookPayload(BaseModel):
    messages: list[IMessageItem] = Field(default_factory=list)


def _verify(secret: str, body: bytes, timestamp: str | None, signature: str | None) -> None:
    if not timestamp or not signature:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing signature headers")
    try:
        ts_int = int(timestamp)
    except ValueError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid timestamp")
    skew = abs(int(time.time()) - ts_int)
    if skew > WEBHOOK_REPLAY_WINDOW_SECONDS:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, f"Timestamp skew {skew}s exceeds replay window"
        )
    expected = hmac.new(
        secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid signature")


def build_router(settings: Settings) -> APIRouter:
    router = APIRouter()

    @router.post("/webhook/imessage")
    async def receive(
        request: Request,
        x_mhc_timestamp: str | None = Header(default=None),
        x_mhc_signature: str | None = Header(default=None),
    ) -> dict:
        raw = await request.body()
        _verify(settings.forwarder_secret, raw, x_mhc_timestamp, x_mhc_signature)
        try:
            payload = WebhookPayload.model_validate_json(raw)
        except Exception as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Invalid payload: {e}")
        accepted = 0
        for item in payload.messages:
            mid = await enqueue_message(
                source="imessage",
                external_id=item.guid,
                sender=item.sender,
                subject=item.chat_name,
                body=item.body,
                received_at=item.received_at,
                original_link=None,
            )
            if mid is not None:
                accepted += 1
        logger.info(
            "imessage webhook accepted=%d total=%d", accepted, len(payload.messages)
        )
        return {"accepted": accepted, "total": len(payload.messages)}

    return router
