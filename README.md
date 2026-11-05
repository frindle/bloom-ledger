# bloom-ledger

Tamper-evident record keeping for Darkbloom provider machines. Machines POST content-addressed objects (power and earnings snapshots) to a small stdlib-only Python server. The server indexes them in SQLite and closes each UTC day into a hash-chained manifest. A web dashboard at `/` shows each machine's last 90 days of manifests, and `/v1/alerts` reports silent machines and stale ring snapshots.

This is bookkeeping data, not tax advice.

## Run (Docker Compose)

```
git clone https://github.com/frindle/bloom-ledger.git
cd bloom-ledger
./update.sh
```

`update.sh` writes a `.env` on first run (git-ignored; edit it to move things), builds the image and starts the container. On Unraid the `.env` points at `/mnt/user/data/Docker/bloom-ledger` for data and `/mnt/user/appdata/bloom-ledger/secrets` for optional secret files; elsewhere it uses `./data` and `./secrets` owned by you. Run `./update.sh` again to update. No secret files are needed to start: machines are added in the web UI.

Open `http://<host>:8787/`. Health check: `GET /healthz`. Keep port 8787 on your local network.

## Add a Mac

1. Open `http://<host>:8787/settings`, type a machine id under **Add a machine** (optionally that Mac's Darkbloom API key, when it uses a different account from the one saved on the page) and press **Add machine**.
2. Copy the install command it shows and paste it into Terminal on that Mac:
   ```
   curl -fsSL http://<host>:8787/install.sh | sh -s -- --pair <code>
   ```
   The code works once, for 30 minutes (**New token** on the machine's row makes a fresh one).

The installer needs Python 3.9+ (Xcode command line tools or Homebrew) and installs `macmon` with Homebrew for power readings. It copies the client to `~/Library/Application Support/bloom-ledger`, puts the machine's token in the login Keychain, writes `~/.darkbloom/ledger.json` and loads per-user LaunchAgents (`dev.bloom-ledger.*`): a power logger, the archiver, the shipper, the daily manifest and a finder. Options: `--earnings` also archives that Mac's Darkbloom earnings (one Mac per account), `--replace-old` stops the older `com.*.bloom-{power-log,archive,ship,earnings-archive}` LaunchAgents this client replaces and moves their plists aside (other bloom jobs keep running), `--uninstall` removes the LaunchAgents (logged data stays in `~/.darkbloom`).

If the ledger's address changes, the finder (every 10 minutes) asks the saved address for `/v1/hello`; when that fails it scans the Mac's local /24 for a ledger that answers with the same server id and updates `ledger.json`. It does not use mDNS/Bonjour, which would need host networking for the container. The shipper only talks to private IP addresses.

## Write-off rules

**Settings > Write-off rules** chooses what counts as business use (Darkbloom inference, Sandbox jobs, your own local work, idle time while Darkbloom is online), how power is deducted (metered cost of business-use minutes, the whole bill times the business share, all of it, or none), whether the business share used for depreciation is measured or a fixed percent, and how much of a lease is deducted. Rules are effective-dated: pick the date they apply from and earlier years keep their rules. The defaults count paid Darkbloom and Sandbox minutes only. Reports and the tax packet list the rules they used. Rates and other numbers are on `/settings/accounting`.

## Settings page

`http://<host>:8787/settings` lists the machines and the ledger health, and lets you add a machine (shows its token and the install command once), rotate a token, or remove a machine. Removing a machine revokes its token and hides it; its records stay, because history is write-once and hash-chained, so machines cannot be renamed either. A machine can be added before it reports: it shows as "Not reporting yet" and never raises a silent-machine alert.

Changes need no password: the server only accepts them from a private (LAN) address with a same-origin request, and refuses anything that arrives through a public proxy. That is a guard, not authentication, so never expose port 8787 to the internet. The page also lets you edit each machine's display name, model, leased-or-purchased label (informational; it does not change accounting) and lease, and links to `/settings/accounting`. Machines added here are stored as token hashes in `/data/machines.json`. An optional legacy `secrets/bloom_tokens` file (one `<machine_id> <sha256 of token>` per line) stays read-only and wins if the same id is in both, until you press **New token** for that machine: the machine then moves to `machines.json` with the new token and its old line is ignored. Darkbloom API keys (optional; Darkbloom does not accept them for live status yet, see Layr-Labs/d-inference#1760) are kept under `/data/secrets` (mode 600), never shown again and only sent to Darkbloom over https. Reads are open.

Tunnel access: settings writes that arrive through a public Cloudflare tunnel need a verified Cloudflare Access JWT (RS256). The team domain and the application AUD come from the `BLOOM_ACCESS_TEAM_DOMAIN` and `BLOOM_ACCESS_AUD` environment variables (set them in a git-ignored `.env` next to `compose.yaml`); if either is unset, tunnel writes fail closed. Cloudflare Access must stay in front of the hostname. The token's email claim only has to exist; it is not matched against an allowlist, so the Access policy is the access control. The Access policy and the tunnel configuration live outside this repository.

The optional `bloom-earnings` service archives Darkbloom earnings from the same image (`docker compose --profile earnings up -d`) and needs a `secrets/darkbloom_token` file. Run only one earnings poller per Darkbloom account.

## Tests

```
pip install pytest
PYTHONPATH=lib python -m pytest ingest
```
