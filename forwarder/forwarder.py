#!/usr/bin/env python3
"""MHC AI Inbox - Mac iMessage forwarder.

Reads ~/Library/Messages/chat.db read-only, applies a blocklist, and POSTs
new inbound iMessages to the cloud webhook with an HMAC-SHA256 signature.
Persists the last-seen ROWID in ~/.mhc_ai_inbox/state.json and logs to
~/.mhc_ai_inbox/forwarder.log. Invoked every 5 minutes by launchd.

Usage:
    python3 forwarder.py            # normal run
    python3 forwarder.py --dry-run  # print payload, do not POST
    python3 forwarder.py --verbose  # also log to stdout
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import hmac
import json
import logging
import os
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# Seconds between Unix epoch (1970-01-01) and Mac/Cocoa epoch (2001-01-01).
MAC_EPOCH_OFFSET = 978_307_200

HOME = Path.home()
STATE_DIR = HOME / ".mhc_ai_inbox"
STATE_FILE = STATE_DIR / "state.json"
LOG_FILE = STATE_DIR / "forwarder.log"
ENV_FILE = STATE_DIR / ".env"
BLOCKLIST_FILE = STATE_DIR / "blocklist.json"
CHAT_DB = HOME / "Library" / "Messages" / "chat.db"

POST_TIMEOUT_SECONDS = 30.0
BATCH_LIMIT = 200


def _load_env_file(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def _load_blocklist(path: Path) -> dict[str, list[str]]:
    if not path.exists():
        return {"handles": [], "keywords": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        logging.warning("blocklist parse failed (%s); treating as empty", e)
        return {"handles": [], "keywords": []}
    return {
        "handles": [str(h).lower() for h in data.get("handles", []) if h],
        "keywords": [str(k).lower() for k in data.get("keywords", []) if k],
    }


def _load_state(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        return int(json.loads(path.read_text(encoding="utf-8")).get("last_rowid", 0))
    except (json.JSONDecodeError, ValueError, KeyError):
        return 0


def _save_state(path: Path, last_rowid: int) -> None:
    path.write_text(json.dumps({"last_rowid": last_rowid}, indent=2), encoding="utf-8")


def _mac_date_to_iso(mac_ns: int) -> str:
    seconds = mac_ns / 1_000_000_000 + MAC_EPOCH_OFFSET
    return dt.datetime.fromtimestamp(seconds, tz=dt.timezone.utc).isoformat()


_NOISE_RE = re.compile(
    r"^(__k\w+|NS[A-Z]\w*|\$class\w*|WNS\w*|WHttp\w*|streamtyped|Anchored)",
)


def _extract_attributed(body: bytes | None) -> str | None:
    """Extract message text from an NSAttributedString typedstream blob.

    Sonoma+ often stores message content in `attributedBody` with `text`
    NULL. The blob is a Foundation typedstream: each NSString is wrapped as
    ``+ <length> <utf-8 bytes>`` where the length byte indicates 1, 2, or
    4-byte length encoding. We walk every NSString section in order, skip
    those whose decoded value matches a known typedstream metadata key
    (attribute keys like ``__kIMMessagePartAttributeName``, class wrappers
    like ``WNSURL``), and return the first real string we find. Returns
    None when nothing readable is present (pure-attachment messages, etc.).
    """
    if not body:
        return None
    pos = 0
    while True:
        idx = body.find(b"NSString", pos)
        if idx < 0:
            return None
        pos = idx + 8
        scan_end = min(pos + 32, len(body))
        plus_idx = body.find(b"+", pos, scan_end)
        if plus_idx < 0:
            continue
        len_pos = plus_idx + 1
        if len_pos >= len(body):
            continue
        b0 = body[len_pos]
        if b0 < 0x80:
            length = b0
            data_start = len_pos + 1
        elif b0 == 0x81 and len_pos + 2 < len(body):
            length = int.from_bytes(body[len_pos + 1 : len_pos + 3], "little")
            data_start = len_pos + 3
        elif b0 == 0x82 and len_pos + 4 < len(body):
            length = int.from_bytes(body[len_pos + 1 : len_pos + 5], "little")
            data_start = len_pos + 5
        else:
            continue
        if length == 0 or length > 32000 or data_start + length > len(body):
            continue
        text_bytes = body[data_start : data_start + length]
        pos = data_start + length
        text = text_bytes.decode("utf-8", errors="replace")
        clean = text.strip("\ufffc\ufffd \t\r\n")
        if not clean or _NOISE_RE.match(clean):
            continue
        return clean


def _is_blocked(sender: str, body: str, blocklist: dict[str, list[str]]) -> str | None:
    s = (sender or "").lower()
    for h in blocklist["handles"]:
        if h in s:
            return f"handle '{h}'"
    b = (body or "").lower()
    for k in blocklist["keywords"]:
        if k in b:
            return f"keyword '{k}'"
    return None


def _query_messages(con: sqlite3.Connection, last_rowid: int, limit: int) -> list[sqlite3.Row]:
    cur = con.execute(
        """
        SELECT m.ROWID            AS rowid,
               m.guid             AS guid,
               m.text             AS text,
               m.attributedBody   AS attributed_body,
               m.date             AS mac_date,
               h.id               AS handle_id,
               c.display_name     AS chat_name
          FROM message m
          LEFT JOIN handle h               ON h.ROWID  = m.handle_id
          LEFT JOIN chat_message_join cmj  ON cmj.message_id = m.ROWID
          LEFT JOIN chat c                 ON c.ROWID  = cmj.chat_id
         WHERE m.ROWID     > ?
           AND m.is_from_me = 0
         ORDER BY m.ROWID ASC
         LIMIT ?
        """,
        (last_rowid, limit),
    )
    return cur.fetchall()


def _sample_recent_messages(con: sqlite3.Connection, limit: int) -> list[sqlite3.Row]:
    """Most-recent N inbound messages, regardless of state. For --sample dry-runs."""
    cur = con.execute(
        """
        SELECT m.ROWID            AS rowid,
               m.guid             AS guid,
               m.text             AS text,
               m.attributedBody   AS attributed_body,
               m.date             AS mac_date,
               h.id               AS handle_id,
               c.display_name     AS chat_name
          FROM message m
          LEFT JOIN handle h               ON h.ROWID  = m.handle_id
          LEFT JOIN chat_message_join cmj  ON cmj.message_id = m.ROWID
          LEFT JOIN chat c                 ON c.ROWID  = cmj.chat_id
         WHERE m.is_from_me = 0
         ORDER BY m.ROWID DESC
         LIMIT ?
        """,
        (limit,),
    )
    return list(reversed(cur.fetchall()))


def _build_message(row: sqlite3.Row) -> dict | None:
    text = row["text"]
    if not text:
        text = _extract_attributed(row["attributed_body"])
    if not text:
        return None
    sender = row["handle_id"]
    if not sender:
        return None
    return {
        "guid": row["guid"],
        "sender": sender,
        "chat_name": row["chat_name"],
        "body": text,
        "received_at": _mac_date_to_iso(row["mac_date"]),
    }


def _sign(secret: str, body: bytes, timestamp: str) -> str:
    return hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()


def _post(url: str, secret: str, payload: dict) -> tuple[int, str]:
    body = json.dumps(payload).encode("utf-8")
    timestamp = str(int(time.time()))
    signature = _sign(secret, body, timestamp)
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-MHC-Timestamp": timestamp,
            "X-MHC-Signature": signature,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=POST_TIMEOUT_SECONDS) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")


def _setup_logging(verbose: bool) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = [logging.FileHandler(LOG_FILE)]
    if verbose or sys.stdout.isatty():
        handlers.append(logging.StreamHandler(sys.stdout))
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
        handlers=handlers,
        force=True,
    )


def run(dry_run: bool, sample: int | None = None) -> int:
    env = {**_load_env_file(ENV_FILE), **os.environ}
    webhook_url = env.get("WEBHOOK_URL", "").strip()
    secret = env.get("FORWARDER_SECRET", "").strip()
    if not dry_run and (not webhook_url or not secret):
        logging.error(
            "missing WEBHOOK_URL or FORWARDER_SECRET (expected in %s or process env)",
            ENV_FILE,
        )
        return 2

    blocklist = _load_blocklist(BLOCKLIST_FILE)
    last_rowid = _load_state(STATE_FILE)

    if not CHAT_DB.exists():
        logging.error("chat.db not found at %s", CHAT_DB)
        return 3

    try:
        con = sqlite3.connect(f"file:{CHAT_DB}?mode=ro&immutable=1", uri=True, timeout=5)
    except sqlite3.OperationalError as e:
        logging.error(
            "cannot open chat.db read-only (%s). Grant Full Disk Access to your "
            "python3 binary in System Settings > Privacy & Security.",
            e,
        )
        return 4
    con.row_factory = sqlite3.Row

    try:
        if sample is not None:
            rows = _sample_recent_messages(con, sample)
            logging.info("sample mode: %d most-recent inbound messages (state not advanced)", len(rows))
        else:
            rows = _query_messages(con, last_rowid, BATCH_LIMIT)
    except sqlite3.DatabaseError as e:
        logging.error("chat.db query failed (%s); database may be locked or schema changed.", e)
        con.close()
        return 5
    finally:
        con.close()

    new_max_rowid = last_rowid
    accepted: list[dict] = []
    blocked = 0
    unreadable = 0
    for row in rows:
        new_max_rowid = max(new_max_rowid, row["rowid"])
        msg = _build_message(row)
        if msg is None:
            unreadable += 1
            continue
        reason = _is_blocked(msg["sender"], msg["body"], blocklist)
        if reason:
            blocked += 1
            logging.debug("blocked rowid=%d (%s)", row["rowid"], reason)
            continue
        accepted.append(msg)

    if not accepted:
        if rows:
            logging.info(
                "no forwardable messages (rows=%d, blocked=%d, unreadable=%d, new_rowid=%d)",
                len(rows), blocked, unreadable, new_max_rowid,
            )
        if not dry_run and new_max_rowid > last_rowid:
            _save_state(STATE_FILE, new_max_rowid)
        return 0

    payload = {"messages": accepted}

    if dry_run:
        print(json.dumps(payload, indent=2, default=str))
        logging.info(
            "dry-run: would have posted %d message(s) (state NOT advanced)", len(accepted)
        )
        return 0

    try:
        status, body = _post(webhook_url, secret, payload)
    except Exception as e:
        logging.exception("webhook POST failed; will retry on next run: %s", e)
        return 6

    if 200 <= status < 300:
        _save_state(STATE_FILE, new_max_rowid)
        logging.info(
            "forwarded %d message(s) status=%d response=%s",
            len(accepted), status, body[:200],
        )
        return 0
    logging.error("webhook returned status=%d body=%s", status, body[:500])
    return 7


def main() -> int:
    parser = argparse.ArgumentParser(description="MHC AI Inbox - iMessage forwarder")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print payload, do not POST or advance state.",
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=None,
        metavar="N",
        help="Inspect the N most-recent inbound messages instead of using state. Requires --dry-run.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Also log to stdout (DEBUG level).",
    )
    args = parser.parse_args()
    if args.sample is not None and not args.dry_run:
        parser.error("--sample requires --dry-run")
    if args.sample is not None and args.sample <= 0:
        parser.error("--sample N must be positive")
    _setup_logging(args.verbose)
    try:
        return run(dry_run=args.dry_run, sample=args.sample)
    except Exception:
        logging.exception("forwarder crashed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
