#!/bin/bash
# End-to-end test of the Mac path, walked the way a new user would. GitHub Actions macos runner ONLY: it installs and removes
# launchd jobs, writes the login Keychain and ~/Library, so it refuses to run anywhere that is not a CI runner.
#   1 install the server  2 /setup and the admin  3 install the client with a pairing code  4 data reaches the API
#   5 doctor  6 install again (safe to repeat)  7 uninstall both and prove nothing is left
set -u
[ "${CI:-}" = "true" ] && [ "$(uname -s)" = "Darwin" ] || { echo "refusing to run: this test is for the CI macOS runner only" >&2; exit 2; }
HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/../.." && pwd)
PORT=18787
BASE="http://127.0.0.1:$PORT"
UIDN=$(id -u)
APP="$HOME/Library/Application Support/bloom-ledger"
SDATA="$HOME/Library/Application Support/bloom-ledger-server"
DBK="$HOME/.darkbloom"
WORK=$(mktemp -d)
COOKIE="$WORK/cookie"
FAILS=0
ok() { echo "ok   - $1"; }
bad() { echo "FAIL - $1"; FAILS=$((FAILS + 1)); }
step() { echo; echo "== $1"; }
# must DESC CMD...: run a command, show its output only when it fails.
must() { d="$1"; shift; if out=$("$@" 2>&1); then ok "$d"; else bad "$d"; echo "$out" | tail -20; fi; }
mustnot() { d="$1"; shift; if "$@" >/dev/null 2>&1; then bad "$d"; else ok "$d"; fi; }
dump_logs() {
  echo "---- diagnostics"
  for f in "$SDATA"/logs/server.log "$APP"/logs/*.log; do [ -f "$f" ] && { echo "## $f"; tail -30 "$f"; }; done
  launchctl list 2>/dev/null | grep -i bloom
}
onexit() { code=$?; [ "$FAILS" = 0 ] || dump_logs; exit "$code"; }
trap onexit EXIT

step "0 fake Darkbloom folder (sample data only)"
python3 "$HERE/sample.py" home "$DBK"
ls "$DBK"

step "1 install the server like the README says"
must "install-server.sh --port succeeds" sh "$REPO/deploy/mac/install-server.sh" --port "$PORT"
must "/healthz answers" curl -fsS "$BASE/healthz"
[ "$(stat -f %Lp "$SDATA/logs/server.log")" = 600 ] && ok "server.log is readable by this user only (600)" || bad "server.log is mode 600"
launchctl print "gui/$UIDN/dev.bloom-ledger.server" >/dev/null 2>&1 && ok "server launchd job is loaded" || bad "server launchd job is loaded"
must "install-server.sh a second time, no flags (the README update command), is harmless" sh "$REPO/deploy/mac/install-server.sh"
must "/healthz still answers on the same port (flags were kept)" curl -fsS "$BASE/healthz"

step "2 /setup and the admin"
curl -fsS "$BASE/setup" | grep -qi "setup" && ok "/setup page loads" || bad "/setup page loads"
curl -fsS "$BASE/v1/auth/me" | grep -q '"mode": *"setup"' && ok "fresh server reports setup mode" || bad "fresh server reports setup mode"
grep -q 'Setup code: [0-9a-f]' "$SDATA/logs/server.log" && ok "setup code is in server.log (for remote browsers)" || bad "setup code is in server.log"
must "admin created (local setup needs no code)" python3 "$HERE/sample.py" setup "$BASE" owner "correct-horse-1" "$COOKIE"
[ ! -e "$SDATA/setup-code" ] && ok "setup code rotated after setup (file removed)" || bad "setup code rotated after setup"
CODE=$(python3 "$HERE/sample.py" paircode "$BASE" mac-ci "$COOKIE") && ok "pairing code made" || { bad "pairing code made"; CODE=""; }

step "3 install the client with the pairing code"
curl -fsSL "$BASE/install.sh" -o "$WORK/install.sh" && ok "install.sh is served" || bad "install.sh is served"
grep -q '@@LEDGER_BASE@@' "$WORK/install.sh" && bad "install.sh has its address filled in" || ok "install.sh has its address filled in"
sh "$WORK/install.sh" --pair "$CODE" 2>&1 | tee "$WORK/client-install.txt"
[ "${PIPESTATUS[0]}" = 0 ] && ok "install.sh exit 0" || bad "install.sh exit 0"
for j in power archive ship manifest find; do
  launchctl print "gui/$UIDN/dev.bloom-ledger.$j" >/dev/null 2>&1 && ok "client job $j loaded" || bad "client job $j loaded"
done
security find-generic-password -s bloom-ledger-ingest -a mac-ci >/dev/null 2>&1 && ok "token is in the Keychain" || bad "token is in the Keychain"
grep -q 'machine_id' "$DBK/ledger.json" && ok "ledger.json written" || bad "ledger.json written"
grep -rq "$CODE" "$WORK/client-install.txt" && bad "pairing code not echoed" || ok "pairing code not echoed"
mustnot "the pairing code works only once" curl -fsS -X POST -H 'Content-Type: application/json' --data "{\"code\":\"$CODE\"}" "$BASE/v1/pair"

step "4 data shows up through the API"
must "ledger shows data from the Mac" python3 "$HERE/sample.py" wait "$BASE" mac-ci 240

step "5 doctor"
must "client doctor passes" python3 "$APP/client/bloom-doctor.py"
python3 "$APP/client/bloom-doctor.py" | tee "$WORK/doctor.txt" >/dev/null
grep -q "FAIL" "$WORK/doctor.txt" && bad "client doctor shows no FAIL" || ok "client doctor shows no FAIL"
must "server doctor passes" env BLOOM_DATA="$SDATA" BLOOM_PORT="$PORT" PYTHONPATH="$REPO/lib:$REPO/ingest" python3 "$REPO/ingest/server.py" doctor

step "6 install the client again (safe to repeat)"
NEWCODE=$(python3 "$HERE/sample.py" paircode "$BASE" mac-ci "$COOKIE") || NEWCODE=""
must "install.sh a second time" sh "$WORK/install.sh" --pair "$NEWCODE"
must "client doctor passes after reinstall" python3 "$APP/client/bloom-doctor.py"

step "7 uninstall the client"
mkdir -p "$APP/old-launchagents" && echo keep > "$APP/old-launchagents/com.example.bloom-power-log.plist"
must "install.sh --uninstall" sh "$WORK/install.sh" --uninstall
for j in power archive ship manifest find earnings; do
  launchctl print "gui/$UIDN/dev.bloom-ledger.$j" >/dev/null 2>&1 && bad "client job $j gone" || ok "client job $j gone"
done
# every dev.bloom-ledger.* plist except the server's own (the old glob [!s]* also skipped the ship job's)
left=$(find "$HOME/Library/LaunchAgents" -name 'dev.bloom-ledger.*.plist' ! -name 'dev.bloom-ledger.server.plist' 2>/dev/null)
[ -z "$left" ] && ok "no client plists left" || { bad "no client plists left"; echo "$left"; }
[ -e "$APP/client" ] || [ -e "$APP/logs" ] && bad "client folder removed" || ok "client folder removed"
[ -f "$APP/old-launchagents/com.example.bloom-power-log.plist" ] && ok "old-launchagents kept by uninstall" || bad "old-launchagents kept by uninstall"
rm -rf "$APP"
security find-generic-password -s bloom-ledger-ingest -a mac-ci >/dev/null 2>&1 && bad "Keychain token removed" || ok "Keychain token removed"
[ -e "$DBK/ledger.json" ] && bad "ledger.json removed" || ok "ledger.json removed"
[ -f "$DBK/provider.log" ] && [ -f "$DBK/usage-history.json" ] && ok "Darkbloom's own files untouched" || bad "Darkbloom's own files untouched"
[ -d "$DBK/ledger-spool" ] && ok "unsent spool kept by default" || bad "unsent spool kept by default"
must "install.sh --uninstall --delete-data" sh "$WORK/install.sh" --uninstall --delete-data
[ -e "$DBK/ledger-spool" ] && bad "spool removed with --delete-data" || ok "spool removed with --delete-data"
[ -f "$DBK/provider.log" ] && ok "Darkbloom's own files still untouched" || bad "Darkbloom's own files still untouched"
curl -fsS "$BASE/healthz" >/dev/null && ok "uninstalling the client leaves the server running" || bad "uninstalling the client leaves the server running"

step "8 uninstall the server"
mkdir -p "$SDATA/backups" && echo keep-me > "$SDATA/backups/index-backup.sqlite"
must "uninstall-server.sh" sh "$REPO/deploy/mac/uninstall-server.sh"
launchctl print "gui/$UIDN/dev.bloom-ledger.server" >/dev/null 2>&1 && bad "server job gone" || ok "server job gone"
[ -e "$HOME/Library/LaunchAgents/dev.bloom-ledger.server.plist" ] && bad "server plist removed" || ok "server plist removed"
sleep 2
curl -fsS -m 3 "$BASE/healthz" >/dev/null 2>&1 && bad "server stopped answering" || ok "server stopped answering"
[ -f "$SDATA/index.sqlite" ] && ok "data kept without --delete-data" || bad "data kept without --delete-data"
[ "$(cat "$SDATA/backups/index-backup.sqlite" 2>/dev/null)" = keep-me ] && ok "backups kept without --delete-data" || bad "backups kept without --delete-data"
must "uninstall-server.sh --delete-data" sh "$REPO/deploy/mac/uninstall-server.sh" --delete-data
[ -e "$SDATA" ] && bad "server data removed" || ok "server data removed"
launchctl list 2>/dev/null | grep -qi bloom && bad "no bloom job in launchctl list" || ok "no bloom job in launchctl list"
if find "$HOME/Library/LaunchAgents" -iname '*bloom*' 2>/dev/null | grep -q .; then bad "no bloom file in LaunchAgents"; else ok "no bloom file in LaunchAgents"; fi

step "9 a custom data folder survives a no-flag update and is the one --delete-data erases"
CDATA="$WORK/custom-data"
must "install with --data" sh "$REPO/deploy/mac/install-server.sh" --port "$PORT" --data "$CDATA"
must "update with no flags" sh "$REPO/deploy/mac/install-server.sh"
[ "$(/usr/libexec/PlistBuddy -c 'Print :EnvironmentVariables:BLOOM_DATA' "$HOME/Library/LaunchAgents/dev.bloom-ledger.server.plist")" = "$CDATA" ] && ok "plist still points at the custom folder" || bad "plist still points at the custom folder"
[ -f "$CDATA/index.sqlite" ] && ok "the custom folder holds the database" || bad "the custom folder holds the database"
[ -e "$SDATA" ] && bad "the default folder was not recreated" || ok "the default folder was not recreated"
must "uninstall-server.sh --delete-data" sh "$REPO/deploy/mac/uninstall-server.sh" --delete-data
[ -e "$CDATA" ] && bad "the configured folder was erased" || ok "the configured folder was erased"
FH="$WORK/fakehome"; mkdir -p "$FH/Library/LaunchAgents"
for bad_data in "$FH" "/"; do
  rm -f "$FH/Library/LaunchAgents/dev.bloom-ledger.server.plist"
  /usr/libexec/PlistBuddy -c "Add :EnvironmentVariables dict" -c "Add :EnvironmentVariables:BLOOM_DATA string $bad_data" "$FH/Library/LaunchAgents/dev.bloom-ledger.server.plist" >/dev/null 2>&1
  touch "$FH/keep-me"
  HOME="$FH" sh "$REPO/deploy/mac/uninstall-server.sh" --delete-data >/dev/null 2>&1 && bad "uninstall --delete-data refuses data folder '$bad_data'" || ok "uninstall --delete-data refuses data folder '$bad_data'"
  [ -e "$FH/keep-me" ] && ok "nothing was deleted for '$bad_data'" || bad "nothing was deleted for '$bad_data'"
done

echo; echo "failures: $FAILS"
[ "$FAILS" = 0 ]
