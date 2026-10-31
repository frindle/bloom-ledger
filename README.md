# bloom-ledger

Tamper-evident record keeping for Darkbloom provider machines. Machines POST content-addressed objects (power and earnings snapshots) to a small stdlib-only Python server. The server indexes them in SQLite and closes each UTC day into a hash-chained manifest. A web dashboard at `/` shows each machine's last 90 days of manifests, and `/v1/alerts` reports silent machines and stale ring snapshots.

This is bookkeeping data, not tax advice.

## Run (Docker Compose)

```
git clone https://github.com/frindle/bloom-ledger.git
cd bloom-ledger
mkdir -p secrets data
# one line per machine: "<machine_id> <sha256 hex of its token>" (only hashes are stored)
printf '%s %s\n' mac-1 "$(printf '%s' 'YOUR-LONG-RANDOM-TOKEN' | shasum -a 256 | cut -d' ' -f1)" > secrets/bloom_tokens
chmod 600 secrets/bloom_tokens
# admin token for the Settings page (/settings): without this file the page is read-only
openssl rand -hex 32 > secrets/bloom_admin
chmod 600 secrets/bloom_admin
```

`compose.yaml` mounts `/mnt/user/data/bloom-ledger` for data and `/mnt/user/appdata/bloom-ledger/secrets/` for secrets (Unraid paths). Edit those paths for your host, then:

```
docker compose up -d --build
```

Open `http://<host>:8787/`. Health check: `GET /healthz`.

## Settings page

`http://<host>:8787/settings` lists the machines and the ledger health, and lets you add a machine (shows its token and the onboarding commands once), rotate a token, or remove a token. Removing a machine only revokes its token; its records stay, because history is write-once and hash-chained, so machines cannot be renamed either. A machine can be added before it reports: it shows as "Not reporting yet" and never raises a silent-machine alert.

Changes need the admin token from `secrets/bloom_admin` (the page asks once per browser tab and keeps it in `sessionStorage` only). Without that file every change is refused with 403 and the page says it is read-only. Machines added here are stored as token hashes in `/data/machines.json`; `bloom_tokens` stays read-only and wins if the same id is in both. Treat the port as LAN-only: reads are open.

The optional `bloom-earnings` service archives Darkbloom earnings from the same image (`docker compose --profile earnings up -d`) and needs a `darkbloom_token` secret file.

## Tests

```
pip install pytest
PYTHONPATH=lib python -m pytest ingest
```
