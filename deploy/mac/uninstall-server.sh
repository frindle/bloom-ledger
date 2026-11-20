#!/bin/sh
# Stop and remove the bloom-ledger server service on this Mac. Your data is kept unless you add --delete-data.
set -eu
LABEL="dev.bloom-ledger.server"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
DATA="$HOME/Library/Application Support/bloom-ledger-server"
launchctl bootout "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || true
rm -f "$PLIST"
if [ "${1:-}" = "--delete-data" ]; then
  rm -rf "$DATA"
  echo "bloom-ledger: service and data removed."
else
  echo "bloom-ledger: service removed. Data kept in $DATA (add --delete-data to erase it)."
fi
