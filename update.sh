#!/usr/bin/env bash
# One-shot install/update for the bloom-ledger container (Unraid or any Docker host).
#
# Usage:  ./update.sh
#         ./update.sh --no-cache    # rebuild from scratch (slower)

set -e
cd "$(dirname "$0")"

EXTRA_BUILD_ARGS=""
if [ "${1:-}" = "--no-cache" ]; then
  EXTRA_BUILD_ARGS="--no-cache"
fi

if docker compose version >/dev/null 2>&1; then
  DC="docker compose"
else
  DC="docker-compose"
fi

# Make sure .env names this host's paths (kept across updates; edit it to move things). Only missing keys are added,
# so an existing .env (e.g. with the Cloudflare Access settings) keeps its values.
if [ -d /mnt/user ]; then
  DEF_DATA=/mnt/user/data/Docker/bloom-ledger DEF_SECRETS=/mnt/user/appdata/bloom-ledger/secrets
  DEF_EARN=/mnt/user/data/Docker/bloom-ledger/earnings DEF_UID=99 DEF_GID=100
else
  DEF_DATA=./data DEF_SECRETS=./secrets DEF_EARN=./data/earnings DEF_UID=$(id -u) DEF_GID=$(id -g)
fi
touch .env
for kv in "BLOOM_DATA_DIR=$DEF_DATA" "BLOOM_SECRETS_DIR=$DEF_SECRETS" "BLOOM_EARNINGS_DIR=$DEF_EARN" \
          "BLOOM_UID=$DEF_UID" "BLOOM_GID=$DEF_GID"; do
  if ! grep -q "^${kv%%=*}=" .env; then
    [ -z "$(tail -c1 .env)" ] || echo >> .env
    echo "$kv" >> .env
    echo "added to .env: $kv"
  fi
done
set -a; . ./.env; set +a
mkdir -p "${BLOOM_DATA_DIR:-./data}" "${BLOOM_SECRETS_DIR:-./secrets}"

# Hard-reset to origin/main: this deploy clone has no local commits, and a
# plain pull fails on divergent history.
echo "=== fetching + hard reset to origin/main ==="
git fetch origin
git reset --hard origin/main

echo "=== last commit ==="
git --no-pager log -1 --pretty='%h %s'

echo "=== building${EXTRA_BUILD_ARGS:+ (no cache)} ==="
$DC build $EXTRA_BUILD_ARGS bloom-ledger

echo "=== restart ==="
$DC up -d --force-recreate bloom-ledger

echo "=== done ==="
$DC ps
