#!/bin/sh
# bloom-ledger Mac client installer. The ledger serves this file with its own address filled in, so the one-liner
# shown in Settings > Add a machine is all a new Mac needs:
#   curl -fsSL http://<ledger>:8787/install.sh | sh -s -- --pair <code>
# Options:
#   --pair CODE     pair this Mac (the code from Settings; single use, 30 minutes)
#   --earnings      also archive this Mac's Darkbloom earnings (one Mac per Darkbloom account is enough)
#   --replace-old   stop older bloom LaunchAgents (com.*.bloom-*) and move their plists aside (kept, not deleted)
#   --uninstall     stop and remove the bloom-ledger LaunchAgents (logged data in ~/.darkbloom is kept)
# Installs to ~/Library/Application Support/bloom-ledger, stores the machine token in the login Keychain
# (service bloom-ledger-ingest), and writes ~/.darkbloom/ledger.json. Nothing runs as root.
set -eu

BASE="@@LEDGER_BASE@@"
APP="$HOME/Library/Application Support/bloom-ledger"
AGENTS="$HOME/Library/LaunchAgents"
DBK="$HOME/.darkbloom"
PREFIX="dev.bloom-ledger"
JOBS="power archive ship manifest earnings find"
CODE="" EARNINGS=0 REPLACE_OLD=0 UNINSTALL=0

say() { printf '%s\n' "bloom-ledger: $*"; }
die() { printf '%s\n' "bloom-ledger: $*" >&2; exit 1; }

while [ $# -gt 0 ]; do
  case "$1" in
    --pair) [ $# -ge 2 ] || die "--pair needs the code from Settings"; CODE="$2"; shift 2 ;;
    --earnings) EARNINGS=1; shift ;;
    --replace-old) REPLACE_OLD=1; shift ;;
    --uninstall) UNINSTALL=1; shift ;;
    *) die "unknown option $1" ;;
  esac
done

[ "$(uname -s)" = "Darwin" ] || die "this installer is for macOS"
UID_NUM=$(id -u)
[ "$UID_NUM" -ne 0 ] || die "run it as your normal user, not with sudo"

unload() { launchctl bootout "gui/$UID_NUM/$1" >/dev/null 2>&1 || true; }

if [ "$UNINSTALL" = 1 ]; then
  for j in $JOBS; do unload "$PREFIX.$j"; rm -f "$AGENTS/$PREFIX.$j.plist"; done
  say "removed the LaunchAgents. Logged data in $DBK and the Keychain token were kept."
  exit 0
fi

case "$BASE" in http://*|https://*) ;; *) die "download this script from your ledger (Settings > Add a machine)" ;; esac
printf '%s' "$CODE" | grep -Eq '^[A-Za-z0-9_-]{12,64}$' || die "pass --pair <code> from Settings > Add a machine"

# Python 3.9 or newer, by absolute path (LaunchAgents get no shell PATH).
PY=""
for c in /opt/homebrew/bin/python3 /usr/local/bin/python3 /usr/bin/python3; do
  [ -x "$c" ] || continue
  if [ "$c" = /usr/bin/python3 ] && ! xcode-select -p >/dev/null 2>&1; then continue; fi
  if "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then PY="$c"; break; fi
done
[ -n "$PY" ] || die "needs Python 3.9+: run 'xcode-select --install' or 'brew install python', then try again"

# The ledger's literal IP (the shipper only talks to private IP addresses, never DNS names).
IP=$(curl -fsS -o /dev/null -w '%{remote_ip}' "$BASE/v1/hello") || die "can't reach the ledger at $BASE"
PORT=$(printf '%s' "$BASE" | sed -n 's|^[a-z]*://[^/]*:\([0-9][0-9]*\).*|\1|p')
[ -n "$PORT" ] || PORT=80
case "$IP" in *:*) URL="http://[$IP]:$PORT" ;; *) URL="http://$IP:$PORT" ;; esac

say "downloading the client from $BASE"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
curl -fsSL "$BASE/client.tar.gz" -o "$TMP/client.tar.gz" || die "client download failed"
tar -xzf "$TMP/client.tar.gz" -C "$TMP"
[ -f "$TMP/bloom-ledger-client/bloom-ship.py" ] || die "the client bundle looks incomplete"
mkdir -p "$APP" "$APP/logs" "$DBK" "$AGENTS"
rm -rf "$APP/client.new"
mv "$TMP/bloom-ledger-client" "$APP/client.new"
rm -rf "$APP/client"
mv "$APP/client.new" "$APP/client"
BIN="$APP/client"

say "pairing"
curl -fsS -X POST -H 'Content-Type: application/json' --data "{\"code\":\"$CODE\"}" "$BASE/v1/pair" -o "$TMP/pair.json" \
  || die "pairing failed: the code may be used or expired (make a new one with New token in Settings)"
# Token goes to the Keychain through stdin (never a command-line argument) and is never printed.
MID=$("$PY" - "$TMP/pair.json" "$DBK/ledger.json" "$URL" <<'PYEOF'
import json, os, re, subprocess, sys
pair, cfg_path, url = sys.argv[1], sys.argv[2], sys.argv[3]
d = json.load(open(pair))
mid, token, sid = d.get("machine_id"), d.get("token"), d.get("server_id")
if not (isinstance(mid, str) and re.fullmatch(r"[A-Za-z0-9._-]{1,64}", mid)
        and isinstance(token, str) and re.fullmatch(r"[A-Za-z0-9._~+/=-]{16,512}", token)):
    sys.exit("bloom-ledger: the ledger's pairing reply was not understood")
r = subprocess.run(["/usr/bin/security", "-i"], text=True, capture_output=True,
                   input="add-generic-password -U -s bloom-ledger-ingest -a %s -w %s\n" % (mid, token))
if r.returncode != 0:
    sys.exit("bloom-ledger: could not save the token to the login Keychain")
try:
    cfg = json.load(open(cfg_path))
    cfg = cfg if isinstance(cfg, dict) else {}
except (OSError, ValueError):
    cfg = {}
cfg.update(machine_id=mid, ingest_url=url)
if isinstance(sid, str):
    cfg["server_id"] = sid
tmp = cfg_path + ".tmp"
with open(tmp, "w") as f:
    json.dump(cfg, f, indent=2, sort_keys=True)
    f.write("\n")
os.replace(tmp, cfg_path)
print(mid)
PYEOF
) || exit 1
rm -f "$TMP/pair.json"

if ! command -v macmon >/dev/null 2>&1 && [ ! -x /opt/homebrew/bin/macmon ] && [ ! -x /usr/local/bin/macmon ]; then
  if command -v brew >/dev/null 2>&1; then
    say "installing macmon (power sensor reader) with Homebrew"
    brew install macmon || say "macmon install failed: power rows will say 'power unavailable' until it is installed"
  else
    say "macmon not found and Homebrew is missing: install macmon for power readings (brew install macmon)"
  fi
fi

if [ "$REPLACE_OLD" = 1 ]; then
  mkdir -p "$APP/old-launchagents"
  for p in "$AGENTS"/com.*.bloom-*.plist; do
    [ -f "$p" ] || continue
    unload "$(basename "$p" .plist)"
    mv "$p" "$APP/old-launchagents/"
    say "stopped $(basename "$p" .plist) (plist kept in $APP/old-launchagents)"
  done
elif ls "$AGENTS"/com.*.bloom-power-log.plist >/dev/null 2>&1; then
  say "older bloom LaunchAgents are installed: rerun with --replace-old so power isn't logged twice"
fi

# plist <job> <interval|keepalive|daily> <script> [args...]
plist() {
  job="$1" kind="$2" script="$3"; shift 3
  f="$AGENTS/$PREFIX.$job.plist"
  {
    printf '%s\n' '<?xml version="1.0" encoding="UTF-8"?>' \
      '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">' \
      '<plist version="1.0"><dict>' \
      "  <key>Label</key><string>$PREFIX.$job</string>" \
      '  <key>ProgramArguments</key><array>' \
      "    <string>$PY</string><string>$BIN/$script</string>"
    for a in "$@"; do printf '    <string>%s</string>\n' "$a"; done
    printf '%s\n' '  </array>' \
      '  <key>EnvironmentVariables</key><dict><key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string></dict>'
    case "$kind" in
      keepalive) printf '%s\n' '  <key>KeepAlive</key><true/>' ;;
      daily) printf '%s\n' '  <key>StartCalendarInterval</key><dict><key>Hour</key><integer>1</integer><key>Minute</key><integer>5</integer></dict>' ;;
      *) printf '  <key>StartInterval</key><integer>%s</integer>\n' "$kind" ;;
    esac
    printf '%s\n' '  <key>RunAtLoad</key><true/>' \
      '  <key>ProcessType</key><string>Background</string>' \
      "  <key>StandardOutPath</key><string>$APP/logs/$job.log</string>" \
      "  <key>StandardErrorPath</key><string>$APP/logs/$job.log</string>" \
      '</dict></plist>'
  } > "$f"
  unload "$PREFIX.$job"
  launchctl bootstrap "gui/$UID_NUM" "$f" || die "could not load $PREFIX.$job"
}

plist power keepalive bloom-power-log.py
plist archive 900 bloom-archive.py
plist ship 60 bloom-ship.py
plist manifest daily bloom-manifest.py daily
plist find 600 bloom-find.py
if [ "$EARNINGS" = 1 ]; then
  plist earnings 900 bloom-earnings-archive.py
else
  unload "$PREFIX.earnings"; rm -f "$AGENTS/$PREFIX.earnings.plist"
fi

say "installed as machine '$MID', shipping to $URL"
"$PY" "$BIN/bloom-ship.py" --check || true
say "done. Power minutes appear on the ledger within a few minutes. Uninstall: rerun with --uninstall"
