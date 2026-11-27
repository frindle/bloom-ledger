#!/bin/bash
# Upgrade test (CI, needs Docker) for an install made with plain `docker compose up` BEFORE named volumes: no .env, data in ./data.
# After updating to this branch, compose would start on an empty named volume. It must refuse with a message that says how to keep
# the data, and with the .env lines from that message the old data must be served again. OLD = d667341 (the last commit before the admin login and named volumes), NEW = HEAD.
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
onexit() {
  code=$?
  [ "$FAILS" = 0 ] || (cd "$WORK/deploy" 2>/dev/null && docker compose logs --tail 40 bloom-ledger)
  (cd "$WORK/deploy" 2>/dev/null && docker compose down -v >/dev/null 2>&1)
  exit "$code"
}
trap onexit EXIT
COOKIE="$WORK/cookie"
cget() { curl -fsS -H "Cookie: $(cat "$COOKIE")" "$@"; }
wait_up() { for _ in $(seq 1 40); do curl -fsS "$BASE/healthz" >/dev/null 2>&1 && return 0; sleep 2; done; return 1; }

OLD=$(git -C "$REPO" rev-parse "${OLD_REF:-d667341}") || exit 2
NEW=$(git -C "$REPO" rev-parse HEAD)
git init -q --bare -b main "$WORK/origin.git"
git -C "$REPO" push -q "$WORK/origin.git" "$OLD:refs/heads/main"
git clone -q "$WORK/origin.git" "$WORK/deploy"
cd "$WORK/deploy" || exit 2

echo "== old plain compose install: no .env, ./data on the host"
mkdir data && chmod 777 data      # the old default ran as uid 99; the user made ./data writable for it
[ ! -e .env ] && ok "there is no .env" || bad "there is no .env"
docker compose up -d --build > up.out 2>&1 && wait_up && ok "old stack is up" || { bad "old stack is up"; tail -20 up.out; exit 1; }
H='-H Content-Type:application/json'
# a fresh install starts in first-run setup: create the admin first (from the local network no setup code is needed)
python3 "$HERE/sample.py" setup "$BASE" owner correct-horse-1 "$COOKIE" && ok "admin created on the old install" || { bad "admin created on the old install"; exit 1; }
CODE=$(python3 "$HERE/sample.py" paircode "$BASE" mac-old "$COOKIE") || { bad "old version adds a machine"; exit 1; }
TOKEN=$(curl -fsS -X POST $H --data "{\"code\":\"$CODE\"}" "$BASE/v1/pair" | jget token) || { bad "old pairing"; exit 1; }
SAMPLE_NOW=2026-11-15T12:00:00 python3 "$HERE/sample.py" post "$BASE" "$TOKEN" && ok "sample data shipped" || bad "sample data shipped"
docker compose restart bloom-ledger >/dev/null 2>&1; wait_up
for _ in $(seq 1 30); do [ "$(cget "$BASE/v1/earnings/series" | jget total_micro)" -gt 0 ] && break; sleep 2; done
before=$(cget "$BASE/v1/earnings/series" | jget total_micro)
[ "$before" -gt 0 ] && ok "old version serves earnings ($before)" || bad "old version serves earnings"

echo "== update to this branch and run plain compose again (no .env)"
git -C "$REPO" push -q -f "$WORK/origin.git" "$NEW:refs/heads/main"
git pull -q --ff-only origin main 2>/dev/null || { git fetch -q origin && git reset -q --hard origin/main; }
docker compose up -d --build > up.out 2>&1
sleep 12
LOGS=$(docker compose logs bloom-ledger 2>&1)
echo "$LOGS" | grep -q "refusing to start: found data from an older install" && ok "new container refuses to start and says why" || bad "new container refuses to start and says why"
echo "$LOGS" | grep -q "BLOOM_DATA_DIR=./data" && ok "the message names the .env lines that keep the data" || bad "the message names the .env lines"
curl -fsS -m 3 "$BASE/healthz" >/dev/null 2>&1 && bad "nothing is served from an empty volume" || ok "nothing is served from an empty volume"
[ -f data/index.sqlite ] && ok "the old data was not touched" || bad "the old data was not touched"

echo "== apply the message's fix"
printf 'BLOOM_DATA_DIR=./data\nBLOOM_KEYS_DIR=./data/secrets\nBLOOM_SECRETS_DIR=./secrets\nBLOOM_EARNINGS_DIR=./data/earnings\n' > .env
docker compose up -d >/dev/null 2>&1
wait_up && ok "server is up with the .env lines" || bad "server is up with the .env lines"
[ "$(cget "$BASE/v1/earnings/series" | jget total_micro)" = "$before" ] && ok "earnings unchanged ($before)" || bad "earnings unchanged"
[ "$(curl -fsS -H "Authorization: Bearer $TOKEN" "$BASE/v1/whoami" | jget machine_id)" = mac-old ] && ok "the old Mac's token still works" || bad "the old Mac's token still works"
[ "$(cget "$BASE/v1/auth/me" | jget logged_in)" = True ] && ok "the admin session still works" || bad "the admin session still works"

echo; echo "failures: $FAILS"
[ "$FAILS" = 0 ]
