# bloom-ledger

A small self-hosted ledger for people who run [Darkbloom](https://darkbloom.dev) on Macs. It keeps a private, tamper-evident record of what each Mac earned and how much power it used, shows it on a clean dashboard, alerts you when a Mac goes quiet, and works out a tax-year summary (income, power cost, depreciation).

- Reads Darkbloom's files and API. It never changes anything Darkbloom owns.
- Everything stays on your network. No cloud account, no telemetry.
- Python standard library only. One container or one launchd service.

## What you need

| Piece | Where it runs | Needs |
|---|---|---|
| Server | Any machine that stays on: Docker host (amd64 or arm64), or one of your Macs | Docker, or Python 3.9+ on a Mac |
| Client | Each Mac that runs Darkbloom | macOS, Python 3.9+, Darkbloom already running |

BloomGauge is **not** required (see "Optional: BloomGauge").

## 1. Start the server

### Option A: Docker (any machine)

```sh
git clone <this repo> bloom-ledger && cd bloom-ledger
cp .env.example .env            # optional, every setting has a default
docker compose up -d --build
```

Open `http://<that machine>:8787/setup`. Data lives in the `bloom-data` volume. Check health any time:

```sh
docker compose ps                                           # should say "healthy"
docker compose exec bloom-ledger python3 /app/server.py doctor
```

### Option B: host it on one of your Macs

```sh
git clone <this repo> bloom-ledger && cd bloom-ledger
sh deploy/mac/install-server.sh          # --port 8787 --data DIR are optional
```

It starts at login and restarts if it stops. Remove it with `sh deploy/mac/uninstall-server.sh` (your data is kept unless you add `--delete-data`).

## 2. Finish setup in the browser

`/setup` takes three short steps: create a login, set your time zone and electricity price (optional), name your first Mac. It then shows one command to paste on that Mac and waits for data to arrive.

If you open `/setup` from a different machine than the server, it asks for a one-time setup code printed in the server log (`docker compose logs bloom-ledger`).

## 3. Add each Mac

On the Mac, paste the command `/setup` (or Machines) shows you:

```sh
curl -fsSL http://<server>:8787/install.sh | sh -s -- --pair <code>
```

The installer checks it can reach the server, installs a small background client, stores the machine token in your login Keychain, runs `bloom-doctor`, and tells you exactly what to fix if anything is wrong. It is safe to run again. To remove: `sh install.sh --uninstall` (your Darkbloom data is never touched). Flags: `--server URL`, `--earnings`, `--replace-old`, `--bloomgauge` / `--no-bloomgauge`.

The client only **reads** Darkbloom's folder.

## Pages

Home (earnings, power, cost per day) - Status (is every Mac reporting, with a fix for each problem) - Day log - Tax - Machines (add or revoke a Mac) - Accounting and Depreciation settings. Light and dark follow your system; the Theme button overrides it.

## Troubleshooting

Run `doctor` on the server (above) and `python3 "$HOME/Library/Application Support/bloom-ledger/client/bloom-doctor.py"` on a Mac. Each failure prints a `fix:` line. Common ones:

- "Ledger is reachable" fails: the Mac cannot see the server. Use the server's local address or name, same network or VPN.
- "Ledger accepts this Mac's token" fails: make a new pairing code on Machines and rerun the installer.
- Forgot the password: `docker compose exec bloom-ledger python3 /app/server.py reset-admin`, then open `/setup`.

## Settings you can change (environment)

See `.env.example`. Notable: `BLOOM_PORT`, `BLOOM_LEDGER_LAN_URL`, `BLOOM_TIMEZONE`, `BLOOM_AUTH` (`off` only on a trusted network), `BLOOM_ENABLE_EXPORT_API`, `ALERT_WEBHOOK_URL`, Pushover keys. Older variable names still work.

## Backup and update

Back up the `bloom-data` volume (or the data folder on a Mac). Update with `git pull && docker compose up -d --build`; the database migrates itself.

## Optional: BloomGauge

Nothing here needs BloomGauge. If you use it, tick the box in `/setup`, answer yes in the Mac installer, or set `BLOOM_BLOOMGAUGE=1`. Status shows "optional: not set up" until then, and that is never counted as a problem.

## Privacy and security

Writes require login. Reads are open on your network, so do not expose the port to the internet without a reverse proxy or tunnel with its own login. Secrets are never logged.

## Developing

See CONTRIBUTING.md. Tests: `PYTHONPATH=lib python -m pytest ingest`.

Licence: MIT (see LICENSE).
