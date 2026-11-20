#!/bin/sh
# Stop and remove the bloom-ledger server service on this Mac. Your data is kept unless you add --delete-data.
# --delete-data erases the data folder the installed service was using (read from its launchd file), not a guessed default.
set -eu
LABEL="dev.bloom-ledger.server"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
DATA=""
[ ! -f "$PLIST" ] || DATA=$(/usr/libexec/PlistBuddy -c "Print :EnvironmentVariables:BLOOM_DATA" "$PLIST" 2>/dev/null || true)
[ -n "$DATA" ] || DATA="$HOME/Library/Application Support/bloom-ledger-server"
if [ "${1:-}" = "--delete-data" ]; then
  # Check before anything is stopped, so a refusal leaves the service as it was.
  case "$DATA" in
    ""|"/"|"$HOME"|"$HOME/") echo "bloom-ledger: refusing to delete '$DATA' (not a bloom-ledger data folder). Nothing was changed." >&2; exit 1 ;;
  esac
  case "$DATA" in /*) ;; *) echo "bloom-ledger: refusing to delete '$DATA' (not an absolute path). Nothing was changed." >&2; exit 1 ;; esac
  # A data folder set by hand could be a folder with other files in it (Documents, say): erase only one the server has used.
  if [ -e "$DATA" ] && [ ! -f "$DATA/index.sqlite" ] && [ ! -f "$DATA/logs/server.log" ]; then
    echo "bloom-ledger: refusing to delete '$DATA': it has no index.sqlite or logs/server.log, so it is not a bloom-ledger data folder. Nothing was changed." >&2; exit 1
  fi
fi
launchctl bootout "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || true
rm -f "$PLIST"
if [ "${1:-}" = "--delete-data" ]; then
  echo "bloom-ledger: deleting $DATA"
  rm -rf "$DATA"
  echo "bloom-ledger: service and data removed."
else
  echo "bloom-ledger: service removed. Data kept in $DATA (add --delete-data to erase it)."
fi
