#!/usr/bin/env bash
# One-shot install/update for the bloom-ledger container (Unraid or any Docker host).
#
# Usage:  ./update.sh
#         ./update.sh --no-cache    # rebuild from scratch (slower)
#         ./update.sh --force       # build even if nothing in the image changed
#
# The image is rebuilt only when a file that goes into it changed since the
# last successful build; the container is always recreated.

set -e
cd "$(dirname "$0")"

EXTRA_BUILD_ARGS=""
FORCE_BUILD=""
if [ "${1:-}" = "--no-cache" ]; then
  EXTRA_BUILD_ARGS="--no-cache"
  FORCE_BUILD="--no-cache"
elif [ "${1:-}" = "--force" ]; then
  FORCE_BUILD="--force"
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
  DEF_KEYS=/mnt/user/appdata/bloom-ledger/keys
  DEF_EARN=/mnt/user/data/Docker/bloom-ledger/earnings DEF_UID=99 DEF_GID=100
else
  DEF_DATA=./data DEF_SECRETS=./secrets DEF_KEYS=./data/secrets DEF_EARN=./data/earnings DEF_UID=$(id -u) DEF_GID=$(id -g)
fi
touch .env
for kv in "BLOOM_DATA_DIR=$DEF_DATA" "BLOOM_SECRETS_DIR=$DEF_SECRETS" "BLOOM_KEYS_DIR=$DEF_KEYS" "BLOOM_EARNINGS_DIR=$DEF_EARN" \
          "BLOOM_UID=$DEF_UID" "BLOOM_GID=$DEF_GID"; do
  if ! grep -q "^${kv%%=*}=" .env; then
    [ -z "$(tail -c1 .env)" ] || echo >> .env
    echo "$kv" >> .env
    echo "added to .env: $kv"
  fi
done
set -a; . ./.env; set +a
mkdir -p "${BLOOM_DATA_DIR:-./data}" "${BLOOM_SECRETS_DIR:-./secrets}" "${BLOOM_KEYS_DIR:-./data/secrets}"

# --- build only what changed -------------------------------------------------
# $BUILD_MARKER holds the commit the image was last built from. It is
# gitignored, so `git reset --hard` leaves it alone. It is written only after a
# build succeeded; a skipped run leaves it, so the next diff still starts at the
# last real build.
BUILD_MARKER=.last-built-sha

# is_build_input <path>: succeeds when a change to <path> can change the image.
# This is the list of what the Dockerfile COPYs (plus the Dockerfile, compose
# file and .dockerignore). Anything not listed (README, the ingest tests) never
# reaches the image. Both compose services use this one image.
is_build_input() {
  case "$1" in
    Dockerfile|compose.yaml|.dockerignore|earnings-loop.sh) return 0 ;;
    lib/*|client/*) return 0 ;;
    ingest/server.py|ingest/bloom_*.py|ingest/dashboard.html|ingest/settings.html|ingest/api-keys.html|ingest/static/*) return 0 ;;
  esac
  return 1
}

# decide_build: sets DO_BUILD (1 or 0) and BUILD_WHY. When in doubt: build.
decide_build() {
  DO_BUILD=1
  local new old changed f n=0
  new="$(git rev-parse HEAD)"
  old=""
  if [ -r "$BUILD_MARKER" ]; then old="$(tr -d '[:space:]' < "$BUILD_MARKER" 2>/dev/null || true)"; fi
  if [ -n "$FORCE_BUILD" ]; then BUILD_WHY="$FORCE_BUILD given"; return; fi
  if [ -z "$old" ]; then BUILD_WHY="no build marker yet (first run)"; return; fi
  if ! git cat-file -e "${old}^{commit}" 2>/dev/null; then BUILD_WHY="build marker is not a known commit"; return; fi
  if [ "$old" = "$new" ]; then DO_BUILD=0; BUILD_WHY="no new commits since the last build (${new:0:7})"; return; fi
  if ! changed="$(git diff --relative --no-renames --name-only "$old" "$new" -- 2>/dev/null)"; then
    BUILD_WHY="cannot diff ${old:0:7}..${new:0:7}"; return
  fi
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    if is_build_input "$f"; then BUILD_WHY="image input changed: $f"; return; fi
    n=$((n + 1))
  done <<< "$changed"
  DO_BUILD=0
  BUILD_WHY="${n} file(s) changed since ${old:0:7}, none of them go into the image"
}

# Hard-reset to origin/main: this deploy clone has no local commits, and a
# plain pull fails on divergent history.
echo "=== fetching + hard reset to origin/main ==="
git fetch origin
git reset --hard origin/main

echo "=== last commit ==="
git --no-pager log -1 --pretty='%h %s'

decide_build
if [ "$DO_BUILD" = 1 ]; then
  echo "=== building${EXTRA_BUILD_ARGS:+ (no cache)}: $BUILD_WHY ==="
  $DC build $EXTRA_BUILD_ARGS bloom-ledger
  # Reached only when the build succeeded (set -e).
  git rev-parse HEAD > "$BUILD_MARKER"
else
  echo "=== build skipped: $BUILD_WHY ==="
fi

echo "=== restart ==="
$DC up -d --force-recreate bloom-ledger

echo "=== done ==="
$DC ps
