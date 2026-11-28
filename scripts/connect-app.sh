#!/usr/bin/env bash
# Create an API key for another app and write it into that app's env file; the key is never printed.
#   scripts/connect-app.sh <label> <env-file> [VAR_NAME]        (VAR_NAME defaults to BLOOM_LEDGER_TOKEN)
# Run on the Docker host from this checkout. Any older key with the same label is revoked. The env file is
# edited in place (owner and mode kept) after a backup next to it (mode 600).
# DOCKER and COMPOSE_SERVICE can override the docker command and the compose service name.
set -euo pipefail
set +x

label=${1:-}; envfile=${2:-}; var=${3:-BLOOM_LEDGER_TOKEN}
if [ -z "$label" ] || [ -z "$envfile" ]; then
  echo "usage: scripts/connect-app.sh <label> <env-file> [VAR_NAME]" >&2; exit 2
fi
case $var in *[!A-Za-z0-9_]* | [0-9]* | '') echo "VAR_NAME must be letters, digits and underscores" >&2; exit 2;; esac
[ -f "$envfile" ] || { echo "env file not found: $envfile" >&2; exit 1; }
[ -w "$envfile" ] || { echo "env file is not writable: $envfile" >&2; exit 1; }

cd "$(dirname "$0")/.."
key=$(${DOCKER:-docker} compose exec -T "${COMPOSE_SERVICE:-bloom-ledger}" python3 /app/bloom_keys.py create --label "$label" --replace)
case $key in blk_*) ;; *) echo "the ledger did not return a key" >&2; exit 1;; esac

umask 077
backup="$envfile.bak-$(date +%Y%m%d%H%M%S)"
cp "$envfile" "$backup"
chmod 600 "$backup"
tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT
VAR_=$var VAL_=$key awk '
  index($0, ENVIRON["VAR_"] "=") == 1 { if (!done) print ENVIRON["VAR_"] "=" ENVIRON["VAL_"]; done = 1; next }
  { print }
  END { if (!done) print ENVIRON["VAR_"] "=" ENVIRON["VAL_"] }
' "$envfile" > "$tmp"
cat "$tmp" > "$envfile"   # same file, so owner and mode stay
unset key
echo "key '$label' written to $envfile as $var"
