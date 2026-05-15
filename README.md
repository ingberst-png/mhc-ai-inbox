# MHC AI Inbox

An action-item extractor for MileHighCook. Reads Steve's Gmail and iMessage,
uses Claude Sonnet 4.6 to surface what actually needs a response or follow-up,
and writes each item to a Notion database called **AI Inbox**. A morning
digest lands at 8 AM MT every day.

## Architecture

Two pieces work together:

- **Mac forwarder** (`forwarder/`) — a Python script that runs every 5 minutes
  via launchd. It reads `~/Library/Messages/chat.db` read-only, applies a
  blocklist, and POSTs new messages to the cloud agent over an HMAC-signed
  webhook. State (last rowid) lives in `~/.mhc_ai_inbox/state.json`.
- **Cloud agent** (`cloud/`) — a FastAPI service on Railway. It polls Gmail
  every 15 minutes, receives iMessage webhooks, queues both into Postgres,
  and a background worker calls Claude Sonnet 4.6 to extract action items.
  Survivors are written to Notion (with a 7-day dedup check) and rolled up
  into a daily digest email sent via Resend.

```
  Mac chat.db ──► forwarder.py ──HMAC POST──┐
                                            ├──► FastAPI ──► Postgres queue
  Gmail API ◄── gmail_poller.py ────────────┘                    │
                                                                 ▼
                                                          claude_worker.py
                                                                 │
                                                                 ▼
                                                          Notion "AI Inbox"
                                                                 │
                                                                 ▼
                                                       digest.py (8 AM MT)
                                                                 │
                                                                 ▼
                                                          Resend email
```

## Notion schema (already exists)

The database is named **AI Inbox**. Properties:

| Property         | Type         | Notes                                            |
|------------------|--------------|--------------------------------------------------|
| Title            | title        |                                                  |
| Source           | select       | Gmail, iMessage                                  |
| Sender           | text         |                                                  |
| Snippet          | text         |                                                  |
| Suggested Action | text         |                                                  |
| Due Date         | date         |                                                  |
| Priority         | select       | High, Medium, Low                                |
| Confidence       | number       | 0–1                                              |
| Feedback         | select       | 👍 Good, 👎 Not a to-do, ✏️ Wrong details        |
| Original Link    | URL          |                                                  |
| Status           | select       | New (default), In Progress, Done                 |
| Created          | created time |                                                  |

## Layout

```
mhc-ai-inbox/
├── README.md
├── .env.example
├── .gitignore
├── requirements.txt
├── Procfile
├── railway.json
├── forwarder/                  # Mac side (launchd)
│   ├── forwarder.py
│   ├── blocklist.json
│   ├── com.milehighcook.aiinbox.plist
│   ├── install.sh
│   └── get_refresh_token.py
└── cloud/                      # Railway side (FastAPI)
    ├── main.py                 # app wiring + /health
    ├── config.py               # env var loading + validation
    ├── db.py                   # Postgres schema + queue
    ├── gmail_poller.py         # 15-min Gmail poll
    ├── webhook.py              # /webhook/imessage
    ├── claude_worker.py        # extraction loop
    ├── notion_writer.py        # Notion page creation + dedup
    ├── digest.py               # 8 AM MT digest
    └── prompts/
        ├── system_prompt.md
        └── digest_prompt.md
```

## Deploy

The phases below mirror the build plan. Each step assumes the prior phase
landed cleanly.

1. **Push to GitHub.** Private repo `mhc-ai-inbox`. Push `main`.
2. **Connect Railway.** New project from GitHub repo. Add the built-in
   Postgres plugin — Railway will set `DATABASE_URL` automatically.
3. **Set env vars in Railway.** Use `.env.example` as the checklist:
   `FORWARDER_SECRET`, `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`,
   `ANTHROPIC_API_KEY`, `NOTION_TOKEN`, `NOTION_DATABASE_ID`,
   `RESEND_API_KEY`, `DIGEST_FROM`, `DIGEST_TO`, `WEBHOOK_URL`.
4. **First deploy.** Watch logs. `/health` should return queue depth and
   last-processed timestamps.
5. **Mint a Gmail refresh token.** Run `python forwarder/get_refresh_token.py`
   locally with `credentials.json` in hand. Paste the printed token into
   Railway as `GMAIL_REFRESH_TOKEN` and redeploy.
6. **Install the forwarder.** `cd forwarder && ./install.sh`. This sets up
   `~/.mhc_ai_inbox/` and loads the launchd agent.
7. **Smoke test.** Send yourself an iMessage; within a few minutes a row
   should land in the AI Inbox Notion database. Gmail flows in on the next
   15-minute tick.

## Local development

```
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env       # then fill in values
uvicorn cloud.main:app --reload
```

The forwarder also supports a dry-run mode that prints what it would send
without POSTing — useful while tuning the blocklist.

## Brand

User-facing copy (digest emails, error messages) follows the MHC voice:
warm, authentic, confident, never pushy. No emojis. Palette: navy `#002854`,
gold `#E2BB46`.
