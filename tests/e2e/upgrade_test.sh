#!/bin/bash
# Upgrade test (CI, needs Docker): an install made by the OLD update.sh (host-folder .env, data in ./data) is updated to this
# branch with the command a user would type, ./update.sh, and must keep serving the data it had.
# Everything happens in a temp dir with a throwaway git "origin"; the real repository is only read.
#   OLD = origin/main (what existing users have), NEW = HEAD of this checkout.
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
wait_up() { for _ in $(seq 1 40); do curl -fsS "$BASE/healthz" >/dev/null 2>&1 && return 0; sleep 2; done; return 1; }

OLD=$(git -C "$REPO" rev-parse origin/main) || exit 2
NEW=$(git -C "$REPO" rev-parse HEAD)
echo "old=$OLD new=$NEW"
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
RESP=$(curl -fsS -X POST $H -H "Origin: $BASE" --data '{"id":"mac-old"}' "$BASE/v1/settings/machines") || { bad "old version adds a machine"; exit 1; }
CODE=$(echo "$RESP" | jget pair_code 2>/dev/null)
TOKEN=$(curl -fsS -X POST $H --data "{\"code\":\"$CODE\"}" "$BASE/v1/pair" | jget token) || { bad "old pairing"; exit 1; }
SAMPLE_NOW=2026-11-15T12:00:00 python3 "$HERE/sample.py" post "$BASE" "$TOKEN" && ok "sample data shipped to the old version" || bad "sample data shipped to the old version"
# the previous release indexes new data every 5 minutes and right after a start: restart it so the test does not wait
docker compose restart bloom-ledger >/dev/null 2>&1; wait_up || bad "old server back after restart"
for _ in $(seq 1 30); do [ "$(curl -fsS "$BASE/v1/earnings/series" | jget total_micro)" -gt 0 ] && break; sleep 2; done
before=$(curl -fsS "$BASE/v1/earnings/series" | jget total_micro)
echo "old logs:"; docker compose logs bloom-ledger 2>&1 | grep -v 'GET /' | tail -25 | cut -c1-300
echo "old series: $(curl -fsS "$BASE/v1/earnings/series" | cut -c1-400)"
echo "old status: $(curl -fsS "$BASE/v1/status" | cut -c1-600)"
echo "old settings: $(curl -fsS "$BASE/v1/settings" 2>&1 | cut -c1-600)"
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
  [ "$(curl -fsS "$BASE/v1/earnings/series" | jget total_micro)" = "$before" ] && ok "$label: earnings unchanged ($before)" || bad "$label: earnings unchanged"
  [ "$(find data/objects -type f | wc -l)" = "$objs_before" ] && ok "$label: same files in data/objects" || bad "$label: same files in data/objects"
  [ "$(curl -fsS -H "Authorization: Bearer $TOKEN" "$BASE/v1/whoami" | jget machine_id)" = mac-old ] && ok "$label: the old Mac's token still works" || bad "$label: the old Mac's token still works"
  curl -fsS "$BASE/v1/status" | jget machines.0.objects | grep -q '^[1-9]' && ok "$label: /status lists the Mac with its files" || bad "$label: /status lists the Mac with its files"
  [ "$(curl -fsS "$BASE/v1/status" | jget timezone)" = America/Los_Angeles ] && ok "$label: old time zone kept" || bad "$label: old time zone kept"
  [ "$(curl -fsS "$BASE/v1/auth/me" | jget mode)" = lan ] && ok "$label: still open to the local network until an admin is made" || bad "$label: auth mode stays lan"
}
check_data "after first update"
grep -q '^DAILY_PUSH_HOUR=7' .env && grep -q '^BLOOM_LEDGER_LAN_URL=http://192.168.1.20:8787' .env && ok ".env keeps the user's own settings" || bad ".env keeps the user's own settings"
docker volume ls --format '{{.Name}}' | grep -q 'bloom-data' && bad "no empty named volume was used" || ok "no empty named volume was used"

echo "== second update (now the new script) and a plain compose up"
./update.sh > update.out 2>&1 && ok "update.sh (second run) finished" || { bad "update.sh (second run) finished"; tail -30 update.out; }
wait_up && check_data "after second update" || bad "server up after second update"
docker compose up -d --build >/dev/null 2>&1 && wait_up && check_data "after plain docker compose up" || bad "plain docker compose up"

echo "== create the admin on the upgraded server, update again, login must survive"
python3 "$HERE/sample.py" setup "$BASE" owner correct-horse-1 "$WORK/cookie" && ok "admin created after upgrade" || bad "admin created after upgrade"
./update.sh > update.out 2>&1 && wait_up && [ "$(curl -fsS "$BASE/v1/auth/me" | jget mode)" = login ] && ok "admin survives another update" || bad "admin survives another update"

echo; echo "failures: $FAILS"
[ "$FAILS" = 0 ]
