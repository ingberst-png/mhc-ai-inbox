#!/usr/bin/env bash
# MHC AI Inbox - Mac forwarder installer.
#
# - Creates ~/.mhc_ai_inbox/ for state, logs, blocklist, and .env.
# - Seeds blocklist.json and .env template (idempotent — never overwrites).
# - Writes the launchd plist (with placeholders substituted) to
#   ~/Library/LaunchAgents/ and bootstraps it.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
STATE_DIR="$HOME/.mhc_ai_inbox"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"

PLIST_LABEL="com.milehighcook.aiinbox"
PLIST_DEST="$LAUNCH_AGENTS_DIR/$PLIST_LABEL.plist"
TEMPLATE_PLIST="$SCRIPT_DIR/$PLIST_LABEL.plist"

FORWARDER_SCRIPT="$SCRIPT_DIR/forwarder.py"
TEMPLATE_BLOCKLIST="$SCRIPT_DIR/blocklist.json"

echo "==> MHC AI Inbox forwarder installer"
echo "    repo dir:       $SCRIPT_DIR"
echo "    state dir:      $STATE_DIR"
echo "    launchd label:  $PLIST_LABEL"
echo

if [[ ! -f "$FORWARDER_SCRIPT" ]]; then
  echo "ERROR: forwarder.py not found at $FORWARDER_SCRIPT" >&2
  exit 1
fi
if [[ ! -f "$TEMPLATE_PLIST" ]]; then
  echo "ERROR: plist template not found at $TEMPLATE_PLIST" >&2
  exit 1
fi

mkdir -p "$STATE_DIR"
mkdir -p "$LAUNCH_AGENTS_DIR"

if [[ ! -f "$STATE_DIR/blocklist.json" ]]; then
  cp "$TEMPLATE_BLOCKLIST" "$STATE_DIR/blocklist.json"
  echo "==> wrote $STATE_DIR/blocklist.json (template)"
else
  echo "==> $STATE_DIR/blocklist.json exists — leaving untouched"
fi

if [[ ! -f "$STATE_DIR/.env" ]]; then
  cat > "$STATE_DIR/.env" <<'EOF'
# MHC AI Inbox - forwarder env vars
# Fill in WEBHOOK_URL (your Railway URL + /webhook/imessage) and the same
# FORWARDER_SECRET you set in Railway, then save.
WEBHOOK_URL=
FORWARDER_SECRET=
EOF
  chmod 600 "$STATE_DIR/.env"
  echo "==> wrote $STATE_DIR/.env (template — fill in before first run)"
else
  echo "==> $STATE_DIR/.env exists — leaving untouched"
fi

sed \
  -e "s|__FORWARDER_SCRIPT__|$FORWARDER_SCRIPT|g" \
  -e "s|__HOME__|$HOME|g" \
  -e "s|__LOG_DIR__|$STATE_DIR|g" \
  "$TEMPLATE_PLIST" > "$PLIST_DEST"
echo "==> wrote $PLIST_DEST"

if launchctl print "gui/$UID/$PLIST_LABEL" &>/dev/null; then
  launchctl bootout "gui/$UID" "$PLIST_DEST" || true
  echo "==> booted out previous agent"
fi
launchctl bootstrap "gui/$UID" "$PLIST_DEST"
echo "==> bootstrapped agent (runs every 300s)"

cat <<EOF

Next steps:
  1. Edit $STATE_DIR/.env — fill in WEBHOOK_URL and FORWARDER_SECRET.
  2. Confirm Full Disk Access is granted to your python3 binary:
       System Settings > Privacy & Security > Full Disk Access
  3. Watch the live log:  tail -f $STATE_DIR/forwarder.log
  4. Send yourself a test iMessage and watch it appear in the Notion AI Inbox.

First-run behavior:
  The agent runs every 300s. The first run after Full Disk Access is granted
  seeds state.json with your current chat.db max ROWID and exits without
  forwarding (so we don't replay your entire iMessage history). The next
  run picks up only genuinely new arrivals.
EOF
