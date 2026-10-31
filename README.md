# bloom-ledger

Tamper-evident record keeping for Darkbloom provider machines. Machines POST content-addressed objects (power and earnings snapshots) to a small stdlib-only Python server. The server indexes them in SQLite and closes each UTC day into a hash-chained manifest stamped with OpenTimestamps (Bitcoin). A web dashboard at `/` shows each machine's last 90 days of manifests, and `/v1/alerts` reports silent machines, stale ring snapshots and un-upgraded timestamps.

This is bookkeeping data, not tax advice.

## Run (Docker Compose)

```
git clone https://github.com/frindle/bloom-ledger.git
cd bloom-ledger
mkdir -p secrets data
# one line per machine: "<machine_id> <sha256 hex of its token>" (only hashes are stored)
printf '%s %s\n' mac-1 "$(printf '%s' 'YOUR-LONG-RANDOM-TOKEN' | shasum -a 256 | cut -d' ' -f1)" > secrets/bloom_tokens
chmod 600 secrets/bloom_tokens
```

`compose.yaml` mounts `/mnt/user/data/bloom-ledger` for data and `/mnt/user/appdata/bloom-ledger/secrets/` for secrets (Unraid paths). Edit those paths for your host, then:

```
docker compose up -d --build
```

Open `http://<host>:8787/`. Health check: `GET /healthz`.

The optional `bloom-earnings` service archives Darkbloom earnings from the same image (`docker compose --profile earnings up -d`) and needs a `darkbloom_token` secret file.

## Tests

```
pip install pytest
PYTHONPATH=lib python -m pytest ingest
```
