#!/bin/sh
# Optional "earnings" service: the Darkbloom earnings archiver on Unraid instead of the Mac LaunchAgent.
# The token comes ONLY from the Docker secret /run/secrets/darkbloom_token (never env, never the repo, never logs).
# bloom-earnings-archive.py reads ~/.darkbloom/auth_token, so HOME=/state and that path is a symlink to the secret.
# Every 15 min: archive; once per UTC day: close yesterday's hash-chained manifest (machine id unraid-earnings).
set -u
export HOME=/state BLOOM_POWER_HOME=/state/.darkbloom BLOOM_MACHINE_ID="${BLOOM_MACHINE_ID:-unraid-earnings}"
mkdir -p /state/.darkbloom
[ -r /run/secrets/darkbloom_token ] || { echo "earnings: /run/secrets/darkbloom_token missing; exiting"; exit 2; }
ln -sf /run/secrets/darkbloom_token /state/.darkbloom/auth_token
last_day=""
while :; do
  python3 /app/bloom-earnings-archive.py --state-dir /state/.darkbloom || echo "earnings: archive rc=$?"
  today=$(date -u +%Y-%m-%d)
  if [ "$today" != "$last_day" ]; then
    python3 /app/bloom-manifest.py daily && last_day="$today"
  fi
  sleep 900
done
