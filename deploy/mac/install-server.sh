#!/bin/sh
# Run the bloom-ledger SERVER on this Mac (no Docker). Starts at login, restarts if it stops, runs as you (never root).
#   sh deploy/mac/install-server.sh [--port 8787] [--data DIR]
# Data goes to ~/Library/Application Support/bloom-ledger-server (back it up). Remove with deploy/mac/uninstall-server.sh.
set -eu
PORT=8787
HERE=$(cd "$(dirname "$0")/../.." && pwd)
DATA="$HOME/Library/Application Support/bloom-ledger-server"
LABEL="dev.bloom-ledger.server"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
die() { printf '%s\n' "bloom-ledger: $*" >&2; exit 1; }
while [ $# -gt 0 ]; do
  case "$1" in
    --port) [ $# -ge 2 ] || die "--port needs a number"; PORT="$2"; shift 2 ;;
    --data) [ $# -ge 2 ] || die "--data needs a folder"; DATA="$2"; shift 2 ;;
    *) die "unknown option $1" ;;
  esac
done
[ "$(uname -s)" = "Darwin" ] || die "this script is for macOS. On Linux or Windows use Docker (see the README)."
[ "$(id -u)" -ne 0 ] || die "run it as your normal user, not with sudo"
case "$PORT" in ''|*[!0-9]*) die "the port must be a number" ;; esac
[ -f "$HERE/ingest/server.py" ] || die "run this from a full copy of the project (ingest/server.py not found)"
PY=""
for c in /opt/homebrew/bin/python3 /usr/local/bin/python3 /usr/bin/python3; do
  [ -x "$c" ] || continue
  if [ "$c" = /usr/bin/python3 ] && ! xcode-select -p >/dev/null 2>&1; then continue; fi
  if "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then PY="$c"; break; fi
done
[ -n "$PY" ] || die "needs Python 3.9+: run 'xcode-select --install' or 'brew install python', then try again"
if "$PY" -c "import socket,sys; s=socket.socket(); sys.exit(0 if s.connect_ex(('127.0.0.1',$PORT))==0 else 1)"; then
  launchctl print "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || die "port $PORT is already in use by something else: pick another with --port"
fi
mkdir -p "$DATA" "$DATA/logs" "$HOME/Library/LaunchAgents"
LANIP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || true)
{
  printf '%s\n' '<?xml version="1.0" encoding="UTF-8"?>' \
    '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">' \
    '<plist version="1.0"><dict>' \
    "  <key>Label</key><string>$LABEL</string>" \
    "  <key>ProgramArguments</key><array><string>$PY</string><string>$HERE/ingest/server.py</string></array>" \
    '  <key>EnvironmentVariables</key><dict>' \
    "    <key>BLOOM_DATA</key><string>$DATA</string>" \
    "    <key>BLOOM_PORT</key><string>$PORT</string>" \
    "    <key>BLOOM_LIB_DIR</key><string>$HERE/lib</string>" \
    "    <key>PYTHONPATH</key><string>$HERE/lib:$HERE/ingest</string>"
  [ -z "$LANIP" ] || printf '    <key>BLOOM_LEDGER_LAN_URL</key><string>http://%s:%s</string>\n' "$LANIP" "$PORT"
  printf '%s\n' '    <key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>' \
    '  </dict>' \
    '  <key>KeepAlive</key><true/>' \
    '  <key>RunAtLoad</key><true/>' \
    "  <key>StandardOutPath</key><string>$DATA/logs/server.log</string>" \
    "  <key>StandardErrorPath</key><string>$DATA/logs/server.log</string>" \
    '</dict></plist>'
} > "$PLIST"
if launchctl bootout "gui/$(id -u)/$LABEL" >/dev/null 2>&1; then
  # Running it again (to update): wait until the old process has let go of the port, or the new one cannot start.
  w=0
  while "$PY" -c "import socket,sys; s=socket.socket(); sys.exit(0 if s.connect_ex(('127.0.0.1',$PORT))==0 else 1)"; do
    w=$((w + 1))
    [ "$w" -lt 20 ] || break
    sleep 1
  done
fi
n=0
until launchctl bootstrap "gui/$(id -u)" "$PLIST"; do
  n=$((n + 1))
  [ "$n" -lt 5 ] || die "could not start the service. Look at $DATA/logs/server.log"
  sleep 1
done
i=0
until curl -fsS -m 2 -o /dev/null "http://127.0.0.1:$PORT/healthz" 2>/dev/null; do
  i=$((i + 1))
  if [ "$i" -ge 20 ]; then tail -n 15 "$DATA/logs/server.log" 2>/dev/null >&2 || true; fi
  [ "$i" -lt 20 ] || die "the server did not answer in 20 seconds. Look at $DATA/logs/server.log, then run: PYTHONPATH=$HERE/lib:$HERE/ingest BLOOM_DATA=\"$DATA\" $PY $HERE/ingest/server.py doctor"
  sleep 1
done
printf '%s\n' "bloom-ledger: running. Open http://localhost:$PORT/setup to finish setup." \
  "Other devices: http://${LANIP:-<this-mac-address>}:$PORT/setup" \
  "Check anytime: PYTHONPATH=$HERE/lib:$HERE/ingest BLOOM_DATA=\"$DATA\" BLOOM_PORT=$PORT $PY $HERE/ingest/server.py doctor"
