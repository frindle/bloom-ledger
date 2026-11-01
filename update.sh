#!/usr/bin/env bash
# One-shot update for the bloom-ledger container on Unraid.
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

# compose mounts these as secrets and refuses to start if a file is missing.
# bloom_tokens holds the machine tokens and is created by hand (see README);
SECRETS=/mnt/user/appdata/bloom-ledger/secrets
if [ ! -f "$SECRETS/bloom_tokens" ]; then
  echo "missing $SECRETS/bloom_tokens: create it first (see README)" >&2
  exit 1
fi

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
