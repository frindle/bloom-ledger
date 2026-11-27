#!/bin/bash
# Upgrade test (CI, needs Docker): an install made by the OLD update.sh (host-folder .env, data in ./data) is updated to this
# branch with the command a user would type, ./update.sh, and must keep serving the data it had.
# Everything happens in a temp dir with a throwaway git "origin"; the real repository is only read.
#   OLD = origin/main (what existing users have), NEW = HEAD of this checkout.
#   OLD_REF=<commit> tests the legacy path instead: an install from before the admin login existed (open to the local network until
#   an admin is made). Without it, the old install gets its admin first and the update must keep that login.
set -u
[ "${CI:-}" = "true" ] || { echo "refusing to run outside CI (it starts containers on port 8787)" >&2; exit 2; }
HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/../.." && pwd)
BASE=http://127.0.0.1:8787
WORK=$(mktemp -d)
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null GIT_TERMINAL_PROMPT=0
FAILS=0
ok() { echo "ok   - $1"; }
bad() { echo "FAIL - $1"; FAILS=$((FAILS + 1)); }
jget() { python3 -c "import json,sys; d=json.load(sys.stdin)
for k in sys.argv[1].split('.'): d=d[int(k)] if k.isdigit() else d[k]
print(d)" "$1"; }
dump() { echo "---- diagnostics"; (cd "$WORK/deploy" 2>/dev/null && docker compose logs --tail 40 bloom-ledger; cat update.out 2>/dev/null | tail -40); }
onexit() {
  code=$?
  [ "$FAILS" = 0 ] || dump
  (cd "$WORK/deploy" 2>/dev/null && docker compose down -v >/dev/null 2>&1)
  exit "$code"
}
trap onexit EXIT
COOKIE="$WORK/cookie"
# GET with the admin session cookie once there is one
cget() { if [ -s "$COOKIE" ]; then curl -fsS -H "Cookie: $(cat "$COOKIE")" "$@"; else curl -fsS "$@"; fi; }
wait_up() { for _ in $(seq 1 40); do curl -fsS "$BASE/healthz" >/dev/null 2>&1 && return 0; sleep 2; done; return 1; }

LEGACY=0; [ -n "${OLD_REF:-}" ] && LEGACY=1
OLD=$(git -C "$REPO" rev-parse "${OLD_REF:-origin/main}") || exit 2
NEW=$(git -C "$REPO" rev-parse HEAD)
echo "old=$OLD new=$NEW legacy=$LEGACY"
git init -q --bare -b main "$WORK/origin.git"
git -C "$REPO" push -q "$WORK/origin.git" "$OLD:refs/heads/main"
git clone -q "$WORK/origin.git" "$WORK/deploy"
cd "$WORK/deploy" || exit 2
git config user.email t@example.com; git config user.name t

echo "== install the OLD version the way existing users did"
./update.sh > update.out 2>&1 && ok "old update.sh ran" || { bad "old update.sh ran"; tail -30 update.out; exit 1; }
grep -q '^BLOOM_DATA_DIR=' .env && ok "old update.sh wrote host-path variables to .env" || bad "old .env has BLOOM_DATA_DIR"
echo "DAILY_PUSH_HOUR=7" >> .env
echo "BLOOM_LEDGER_LAN_URL=http://192.168.1.20:8787" >> .env
wait_up && ok "old server is up" || { bad "old server is up"; exit 1; }

echo "== write data on the old version (fake Mac, sample data)"
H='-H Content-Type:application/json'
if [ "$LEGACY" = 0 ]; then
  # a fresh install starts in first-run setup: create the admin (from the local network no setup code is needed), then add the Mac
  python3 "$HERE/sample.py" setup "$BASE" owner correct-horse-1 "$COOKIE" && ok "admin created on the old install" || { bad "admin created on the old install"; exit 1; }
  CODE=$(python3 "$HERE/sample.py" paircode "$BASE" mac-old "$COOKIE") || { bad "old version adds a machine"; exit 1; }
else
  RESP=$(curl -fsS -X POST $H -H "Origin: $BASE" --data '{"id":"mac-old"}' "$BASE/v1/settings/machines") || { bad "old version adds a machine"; exit 1; }
  CODE=$(echo "$RESP" | jget pair_code 2>/dev/null)
fi
TOKEN=$(curl -fsS -X POST $H --data "{\"code\":\"$CODE\"}" "$BASE/v1/pair" | jget token) || { bad "old pairing"; exit 1; }
SAMPLE_NOW=2026-11-15T12:00:00 python3 "$HERE/sample.py" post "$BASE" "$TOKEN" && ok "sample data shipped to the old version" || bad "sample data shipped to the old version"
# the previous release indexes new data every 5 minutes and right after a start: restart it so the test does not wait
docker compose restart bloom-ledger >/dev/null 2>&1; wait_up || bad "old server back after restart"
for _ in $(seq 1 30); do [ "$(cget "$BASE/v1/earnings/series" | jget total_micro)" -gt 0 ] && break; sleep 2; done
before=$(cget "$BASE/v1/earnings/series" | jget total_micro)
echo "old logs:"; docker compose logs bloom-ledger 2>&1 | grep -v 'GET /' | tail -25 | cut -c1-300
echo "old series: $(cget "$BASE/v1/earnings/series" | cut -c1-400)"
echo "old status: $(cget "$BASE/v1/status" | cut -c1-600)"
echo "old settings: $(cget "$BASE/v1/settings" 2>&1 | cut -c1-600)"
objs_before=$(find data/objects -type f | wc -l)
[ "$before" -gt 0 ] && ok "old version serves earnings ($before micro-USD)" || bad "old version serves earnings"
echo "files in data/objects before: $objs_before"

echo "== upgrade exactly as the README says: ./update.sh"
git -C "$REPO" push -q -f "$WORK/origin.git" "$NEW:refs/heads/main"
./update.sh > update.out 2>&1 && ok "update.sh (first run, still the old script) finished" || { bad "update.sh (first run) finished"; tail -30 update.out; }
wait_up && ok "server is up after the update" || bad "server is up after the update"
git log -1 --format=%H | grep -q "$NEW" && ok "checkout is now at the new version" || bad "checkout is now at the new version"
check_data() {
  local label=$1
  [ "$(cget "$BASE/v1/earnings/series" | jget total_micro)" = "$before" ] && ok "$label: earnings unchanged ($before)" || bad "$label: earnings unchanged"
  [ "$(find data/objects -type f | wc -l)" = "$objs_before" ] && ok "$label: same files in data/objects" || bad "$label: same files in data/objects"
  [ "$(curl -fsS -H "Authorization: Bearer $TOKEN" "$BASE/v1/whoami" | jget machine_id)" = mac-old ] && ok "$label: the old Mac's token still works" || bad "$label: the old Mac's token still works"
  cget "$BASE/v1/status" | jget machines.0.objects | grep -q '^[1-9]' && ok "$label: /status lists the Mac with its files" || bad "$label: /status lists the Mac with its files"
  if [ "$LEGACY" = 1 ]; then
    [ "$(cget "$BASE/v1/accounting/day?date=2020-01-15" | jget tz)" = UTC ] && ok "$label: days are UTC, also past days" || bad "$label: days are UTC, also past days"
    [ "$(cget "$BASE/v1/auth/me" | jget mode)" = lan ] && ok "$label: still open to the local network until an admin is made" || bad "$label: auth mode stays lan"
  else
    [ "$(cget "$BASE/v1/auth/me" | jget mode)" = login ] && ok "$label: login mode kept" || bad "$label: login mode kept"
    [ "$(cget "$BASE/v1/auth/me" | jget logged_in)" = True ] && ok "$label: the admin session still works" || bad "$label: the admin session still works"
    [ "$(cget "$BASE/v1/status" | jget timezone)" = UTC ] && ok "$label: status reports UTC days" || bad "$label: status reports UTC days"
    [ "$(cget "$BASE/v1/status" | jget rate_timezone)" = America/Chicago ] && ok "$label: time zone chosen at setup kept (electricity rates)" || bad "$label: time zone chosen at setup kept (electricity rates)"
  fi
}
check_data "after first update"
grep -q '^DAILY_PUSH_HOUR=7' .env && grep -q '^BLOOM_LEDGER_LAN_URL=http://192.168.1.20:8787' .env && ok ".env keeps the user's own settings" || bad ".env keeps the user's own settings"
docker volume ls --format '{{.Name}}' | grep -q 'bloom-data' && bad "no empty named volume was used" || ok "no empty named volume was used"

echo "== second update (now the new script) and a plain compose up"
./update.sh > update.out 2>&1 && ok "update.sh (second run) finished" || { bad "update.sh (second run) finished"; tail -30 update.out; }
wait_up && check_data "after second update" || bad "server up after second update"
docker compose up -d --build >/dev/null 2>&1 && wait_up && check_data "after plain docker compose up" || bad "plain docker compose up"

if [ "$LEGACY" = 1 ]; then
echo "== create the admin on the upgraded server, update again, login must survive"
python3 "$HERE/sample.py" setup "$BASE" owner correct-horse-1 "$COOKIE" && ok "admin created after upgrade (from the local network, no code needed)" || bad "admin created after upgrade"
[ "$(cget "$BASE/v1/status" | jget timezone)" = UTC ] && ok "days stay UTC after setup" || bad "days stay UTC after setup"
[ "$(cget "$BASE/v1/status" | jget rate_timezone)" = America/Chicago ] && ok "time zone chosen at setup applies to electricity rates" || bad "time zone chosen at setup applies to electricity rates"
[ "$(cget "$BASE/v1/accounting/day?date=2020-01-15" | jget tz)" = UTC ] && ok "past days stay UTC (setup did not rewrite history)" || bad "past days stay UTC"
[ "$(cget "$BASE/v1/earnings/series" | jget total_micro)" = "$before" ] && ok "earnings unchanged after setup" || bad "earnings unchanged after setup"
fi
echo "== one more update: the admin login must survive"
./update.sh > update.out 2>&1 && wait_up && [ "$(cget "$BASE/v1/auth/me" | jget mode)" = login ] && [ "$(cget "$BASE/v1/auth/me" | jget logged_in)" = True ] && ok "admin survives another update" || bad "admin survives another update"

echo; echo "failures: $FAILS"
[ "$FAILS" = 0 ]
