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
```

`compose.yaml` mounts `/mnt/user/data/bloom-ledger` for data and `/mnt/user/appdata/bloom-ledger/secrets/` for secrets (Unraid paths). Edit those paths for your host, then:

```
docker compose up -d --build
```

Open `http://<host>:8787/`. Health check: `GET /healthz`.

## Settings page

`http://<host>:8787/settings` lists the machines and the ledger health, and lets you add a machine (shows its token and the onboarding commands once), rotate a token, or remove a machine. Removing a machine revokes its token and hides it; its records stay, because history is write-once and hash-chained, so machines cannot be renamed either. A machine can be added before it reports: it shows as "Not reporting yet" and never raises a silent-machine alert.

Changes need no password: the server only accepts them from a private (LAN) address with a same-origin request, and refuses anything that arrives through a public proxy. That is a guard, not authentication, so never expose port 8787 to the internet. The page also lets you edit each machine's display name, model, leased-or-purchased label (informational; it does not change accounting) and lease, and links to `/settings/accounting`. Machines added here are stored as token hashes in `/data/machines.json`; `bloom_tokens` stays read-only and wins if the same id is in both. Reads are open.

Tunnel access: settings writes that arrive through a public Cloudflare tunnel need a verified Cloudflare Access JWT (RS256). The team domain and the application AUD come from the `BLOOM_ACCESS_TEAM_DOMAIN` and `BLOOM_ACCESS_AUD` environment variables (set them in a git-ignored `.env` next to `compose.yaml`); if either is unset, tunnel writes fail closed. Cloudflare Access must stay in front of the hostname. The token's email claim only has to exist; it is not matched against an allowlist, so the Access policy is the access control. The Access policy and the tunnel configuration live outside this repository.

The optional `bloom-earnings` service archives Darkbloom earnings from the same image (`docker compose --profile earnings up -d`) and needs a `darkbloom_token` secret file.

## Tests

```
pip install pytest
PYTHONPATH=lib python -m pytest ingest
```
