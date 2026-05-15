"""Morning digest sent at 8:00 America/Denver via Resend."""

from __future__ import annotations

import asyncio
import datetime as dt
import html
import logging
from zoneinfo import ZoneInfo

import resend

from cloud.config import DIGEST_LOCAL_HOUR, DIGEST_TIMEZONE, Settings
from cloud.db import set_state
from cloud.notion_writer import query_recent_items

logger = logging.getLogger(__name__)

NAVY = "#002854"
GOLD = "#E2BB46"


def _next_run(now_utc: dt.datetime) -> dt.datetime:
    tz = ZoneInfo(DIGEST_TIMEZONE)
    local = now_utc.astimezone(tz)
    target = local.replace(hour=DIGEST_LOCAL_HOUR, minute=0, second=0, microsecond=0)
    if local >= target:
        target = target + dt.timedelta(days=1)
    return target.astimezone(dt.timezone.utc)


def _priority_order(items: list[dict]) -> list[dict]:
    rank = {"High": 0, "Medium": 1, "Low": 2}
    return sorted(items, key=lambda i: rank.get(i.get("priority") or "", 3))


def _render_html(items: list[dict], date_label: str) -> str:
    if not items:
        body = (
            "<p style='color:#444;font-size:15px;line-height:1.5;margin:0;'>"
            "Nothing new in the last 24 hours. Enjoy the quiet."
            "</p>"
        )
    else:
        rows = []
        for item in _priority_order(items):
            title = html.escape(item.get("title") or "(untitled)")
            source = html.escape(item.get("source") or "")
            sender = html.escape(item.get("sender") or "")
            action = html.escape(item.get("suggested_action") or "")
            priority = html.escape(item.get("priority") or "")
            url = html.escape(item.get("url") or "#")
            priority_chip = (
                f' &middot; <span style="color:{GOLD};font-weight:600;">{priority}</span>'
                if priority
                else ""
            )
            rows.append(
                f"""
                <tr>
                  <td style="padding:14px 0;border-bottom:1px solid #eee;">
                    <div style="font-size:16px;font-weight:600;color:{NAVY};">
                      <a href="{url}" style="color:{NAVY};text-decoration:none;">{title}</a>
                    </div>
                    <div style="font-size:13px;color:#666;margin-top:2px;">
                      {source} &middot; {sender}{priority_chip}
                    </div>
                    <div style="font-size:14px;color:#333;margin-top:6px;">{action}</div>
                  </td>
                </tr>
                """
            )
        body = (
            "<table role='presentation' width='100%' cellpadding='0' cellspacing='0'>"
            + "".join(rows)
            + "</table>"
        )
    return f"""<!doctype html>
<html><body style="margin:0;padding:0;background:#fafafa;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#fafafa;padding:24px 0;">
    <tr><td align="center">
      <table role="presentation" width="600" cellpadding="0" cellspacing="0"
             style="background:#ffffff;border-top:4px solid {GOLD};
                    font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;">
        <tr><td style="padding:28px 28px 8px 28px;">
          <div style="font-size:13px;letter-spacing:0.12em;text-transform:uppercase;color:{GOLD};">
            MHC AI Inbox
          </div>
          <div style="font-size:22px;font-weight:600;color:{NAVY};margin-top:6px;">
            Your day at a glance &middot; {html.escape(date_label)}
          </div>
        </td></tr>
        <tr><td style="padding:8px 28px 28px 28px;">{body}</td></tr>
        <tr><td style="padding:0 28px 24px 28px;font-size:12px;color:#888;">
          Generated overnight by MileHighCook's AI Inbox. Quiet, on the side.
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""


async def _send_digest(settings: Settings) -> None:
    items = await query_recent_items(settings, hours=24)
    tz = ZoneInfo(DIGEST_TIMEZONE)
    date_label = dt.datetime.now(tz).strftime("%A, %B %-d")
    html_body = _render_html(items, date_label)
    plural = "s" if len(items) != 1 else ""
    subject = f"MHC AI Inbox — {date_label} ({len(items)} item{plural})"

    def _send() -> dict:
        resend.api_key = settings.resend_api_key
        return resend.Emails.send(
            {
                "from": settings.digest_from,
                "to": [settings.digest_recipient],
                "subject": subject,
                "html": html_body,
            }
        )

    await asyncio.to_thread(_send)
    await set_state("last_digest_sent_at", dt.datetime.now(dt.timezone.utc).isoformat())
    logger.info("digest sent: %d items", len(items))


async def run_digest_loop(settings: Settings, stop_event: asyncio.Event) -> None:
    logger.info(
        "digest scheduler starting (%02d:00 %s)", DIGEST_LOCAL_HOUR, DIGEST_TIMEZONE
    )
    while not stop_event.is_set():
        now = dt.datetime.now(dt.timezone.utc)
        target = _next_run(now)
        sleep_seconds = max(60.0, (target - now).total_seconds())
        logger.info("next digest at %s (in %ds)", target.isoformat(), int(sleep_seconds))
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=sleep_seconds)
            break
        except asyncio.TimeoutError:
            pass
        try:
            await _send_digest(settings)
        except Exception:
            logger.exception("digest send failed")
    logger.info("digest scheduler stopped")
