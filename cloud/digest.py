"""Morning digest sent at 8:00 America/Denver via Resend."""

from __future__ import annotations

import asyncio
import datetime as dt
import html
import json
import logging
from pathlib import Path
from zoneinfo import ZoneInfo

import resend
from anthropic import AsyncAnthropic

from cloud.config import ANTHROPIC_MODEL, DIGEST_LOCAL_HOUR, DIGEST_TIMEZONE, Settings
from cloud.db import set_state
from cloud.notion_writer import query_recent_items

logger = logging.getLogger(__name__)

NAVY = "#002854"
GOLD = "#E2BB46"

_DIGEST_PROMPT_PATH = Path(__file__).parent / "prompts" / "digest_prompt.md"
_FALLBACK_SUMMARY = "Here's what came in over the last 24 hours."
_EMPTY_SUMMARY = "Nothing new in the last 24 hours."


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


def _render_html(items: list[dict], date_label: str, summary: str) -> str:
    summary_html = (
        f"<p style='font-size:15px;line-height:1.55;color:#333;margin:0 0 18px 0;'>"
        f"{html.escape(summary)}</p>"
    )
    if not items:
        body = summary_html
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
            summary_html
            + "<table role='presentation' width='100%' cellpadding='0' cellspacing='0'>"
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
          Generated overnight by MileHighCook's AI Inbox.
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""


def _items_for_summary(items: list[dict]) -> list[dict]:
    """Trim Notion item dicts to the fields the digest prompt expects."""
    out = []
    for i in items:
        compact = {
            "Title": i.get("title"),
            "Source": i.get("source"),
            "Sender": i.get("sender"),
            "Snippet": i.get("snippet"),
            "Suggested Action": i.get("suggested_action"),
            "Priority": i.get("priority"),
        }
        out.append({k: v for k, v in compact.items() if v})
    return out


async def _summary_paragraph(settings: Settings, items: list[dict]) -> str:
    """Ask Claude for a 2-3 sentence overview. Falls back gracefully on any error."""
    if not items:
        return _EMPTY_SUMMARY
    try:
        system_prompt = _DIGEST_PROMPT_PATH.read_text(encoding="utf-8")
        client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        user_content = json.dumps(_items_for_summary(items), ensure_ascii=False)
        resp = await client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=300,
            system=system_prompt,
            messages=[{"role": "user", "content": user_content}],
        )
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        return text or _FALLBACK_SUMMARY
    except Exception:
        logger.exception("digest summary generation failed; using fallback")
        return _FALLBACK_SUMMARY


async def _send_digest(settings: Settings) -> None:
    items = await query_recent_items(settings, hours=24)
    summary = await _summary_paragraph(settings, items)
    tz = ZoneInfo(DIGEST_TIMEZONE)
    date_label = dt.datetime.now(tz).strftime("%A, %B %-d")
    html_body = _render_html(items, date_label, summary)
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
