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
# bloom_admin guards the Settings page and is generated here on first run.
SECRETS=/mnt/user/appdata/bloom-ledger/secrets
if [ ! -f "$SECRETS/bloom_tokens" ]; then
  echo "missing $SECRETS/bloom_tokens: create it first (see README)" >&2
  exit 1
fi
if [ ! -f "$SECRETS/bloom_admin" ]; then
  echo "=== creating $SECRETS/bloom_admin ==="
  umask 177
  head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n' > "$SECRETS/bloom_admin"
  chown 99:100 "$SECRETS/bloom_admin" 2>/dev/null || true
  echo "read it with: cat $SECRETS/bloom_admin   (this is the Settings page admin token)"
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
