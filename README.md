# bloom-ledger

A small self-hosted ledger for people who run Darkbloom on Macs. It keeps a private, tamper-evident record of what each Mac earned and how much power it used, shows it on a clean dashboard, alerts you when a Mac goes quiet, and works out a tax-year summary (income, power cost, depreciation).

- Reads Darkbloom's files and API. It never changes anything Darkbloom owns.
- Everything stays on your network. No cloud account, no telemetry.
- Python standard library only. One container or one launchd service.

## What you need

| Piece | Where it runs | Needs |
|---|---|---|
| Server | Any machine that stays on: a Docker host (amd64 or arm64), or one of your Macs | Docker with Compose v2 and git, or on a Mac: git and Python 3.9+ (`xcode-select --install` gives you both) |
| Client | Each Mac that runs Darkbloom | macOS, Python 3.9+, Darkbloom already running, same network (or VPN) as the server |

BloomGauge is **not** required (see "Optional: BloomGauge"). Port 8787 must be free on the server (change it with `BLOOM_PORT`, see Troubleshooting).

## 1. Start the server

### Option A: Docker (any machine)

```sh
git clone https://github.com/frindle/bloom-ledger.git && cd bloom-ledger
docker compose up -d --build
```

The first build takes a minute or two. Then open `http://localhost:8787/setup` (on another computer use the server's network address instead of `localhost`, for example `http://192.168.1.20:8787/setup`). Check health any time:

```sh
docker compose ps                                           # should say "healthy"
docker compose exec bloom-ledger python3 /app/server.py doctor
```

Optional settings go in a file named `.env` next to `compose.yaml` (copy `.env.example`). Nothing is needed to start.

### Option B: host it on one of your Macs

```sh
git clone https://github.com/frindle/bloom-ledger.git && cd bloom-ledger
sh deploy/mac/install-server.sh          # --port 8787 --data DIR are optional
```

It starts at login and restarts if it stops. **Keep the `bloom-ledger` folder where it is**: the service runs the code from it. Remove it with `sh deploy/mac/uninstall-server.sh` (your data is kept unless you add `--delete-data`).

## 2. Finish setup in the browser

Open `/setup`. It takes three short steps: create a login, set your time zone and electricity price (optional), name your first Mac. It then shows one command to paste on that Mac and waits for data to arrive. Visiting the home page of a brand-new server sends you there by itself.

First setup from your own network needs no code. A browser that reaches the server from outside the local network is asked for a one-time setup code, printed in the server log on the line "Setup code" (`docker compose logs bloom-ledger`, or `~/Library/Application Support/bloom-ledger-server/logs/server.log` on a Mac install; also the file `setup-code` in the data folder). It stops working once the login exists, and setup can never be run again after that.

On a server that already holds history, the setup page shows your time zone and price fields empty: leave them empty to keep what you have. A change made there applies from today on. Tick "Apply to past days too" only if you want past figures recalculated.

The command it shows uses the address you opened the page with. If that was `localhost`, the command only works on the server itself: to add a different Mac, open `/setup` (or Machines) using the server's network address and copy the command from there.

## 3. Add each Mac

On the Mac, paste the command `/setup` (or Machines) shows you:

```sh
curl -fsSL http://<server>:8787/install.sh | sh -s -- --pair <code>
```

The installer checks it can reach the server, installs a small background client, stores the machine token in your login Keychain, installs `macmon` with Homebrew if you have it (for power readings), runs `bloom-doctor`, and tells you exactly what to fix if anything is wrong. It is safe to run again (get a fresh code first: Machines > New token). The code works once and expires after 30 minutes.

To remove the client from a Mac: `curl -fsSL http://<server>:8787/install.sh | sh -s -- --uninstall`. That removes the background jobs, the client folder, the Keychain token and the pairing file. Darkbloom's own files are never touched; the not-yet-sent copy in `~/.darkbloom/ledger-spool` is kept unless you add `--delete-data`. Remove the Mac from the ledger's list with Machines > Remove.

Flags: `--server URL`, `--earnings`, `--replace-old`, `--bloomgauge` / `--no-bloomgauge`. The client only **reads** Darkbloom's folder.

## Pages

Home (earnings, power, cost per day) - Status (is every Mac reporting, with a fix for each problem) - Day log - Tax - Machines (add or revoke a Mac) - Accounting and Depreciation settings. Light and dark follow your system; the Theme button overrides it.

## Troubleshooting

Run `doctor` on the server (above) and `python3 "$HOME/Library/Application Support/bloom-ledger/client/bloom-doctor.py"` on a Mac. Each failure prints a `fix:` line. Common ones:

- "port is already allocated" (Docker) or "port 8787 is already in use" (Mac): something else uses 8787. Put `BLOOM_PORT=8788` in `.env` and run `docker compose up -d` again, or use `--port 8788` with the Mac script.
- "Cannot connect to the Docker daemon": start Docker Desktop (or the Docker service) and rerun.
- "Ledger is reachable" fails: the Mac cannot see the server. Use the server's local address or name, same network or VPN.
- "Ledger accepts this Mac's token" fails: make a new pairing code on Machines and rerun the installer.
- "pairing failed" in the installer: the code was already used or is older than 30 minutes. Make a new one in Machines > New token.
- Forgot the password: Docker: `docker compose exec bloom-ledger python3 /app/server.py reset-admin`. Mac server: `BLOOM_DATA="$HOME/Library/Application Support/bloom-ledger-server" PYTHONPATH=lib:ingest python3 ingest/server.py reset-admin` from the project folder. Then open `/setup`.
- Five wrong passwords lock the login for a minute; wait and try again.

## Settings you can change (environment)

See `.env.example`. Notable: `BLOOM_PORT`, `BLOOM_LEDGER_LAN_URL`, `BLOOM_TIMEZONE` (electricity time-of-use prices only; days and months are always UTC), `BLOOM_AUTH` (`off` only on a trusted network), `BLOOM_ENABLE_EXPORT_API`, `ALERT_WEBHOOK_URL`, Pushover keys, `DAILY_PUSH_HOUR` (an hour of the UTC day, default 9). Older variable names still work.

## Backup and update

Back up the Docker volumes `bloom-data` and `bloom-keys` (or the data folder on a Mac). Check what exists with `docker volume ls`.

**Update, new install (started with `docker compose up`):** `git pull && docker compose up -d --build`. The database migrates itself.

**Update, install made with `./update.sh` (a `.env` that names `BLOOM_DATA_DIR` and friends, for example on Unraid):** run `./update.sh`. Your data stays in the folders named in `.env`; nothing is copied or moved. `./update.sh` is also safe to run twice. (A plain `git pull && docker compose up -d --build` also keeps those folders now, because compose reads them from `.env`.)

**Update, server on a Mac:** `git pull && sh deploy/mac/install-server.sh` (it restarts the service, data is kept). Macs running the client update themselves by rerunning their install command with a fresh code.

## Connect another app

Another app on your network can add cost entries without a browser login by using an API key.

1. Open **Settings**, then **API keys** (`/settings/api-keys`), type a label and press **Create key**. The full key (it starts with `blk_`) is shown once; copy it then. The server stores only a hash. **Revoke** removes a key at any time.
2. The app sends it as a header: `Authorization: Bearer blk_...`.

Or skip the browser: on the Docker host, from this checkout, run `scripts/connect-app.sh <label> <env-file> [VAR_NAME]`. It creates a key (replacing any older key with the same label), writes `VAR_NAME=<key>` into that app's env file (default name `BLOOM_LEDGER_TOKEN`; a backup is saved next to it) and never prints the key. `python3 /app/bloom_keys.py list` and `revoke --label <label>` run inside the container.

A key can only call these routes, and every other route refuses it with 403:

- `POST /v1/accounting/entries` adds an entry; `POST /v1/accounting/entries/void` voids one; `POST /v1/accounting/entries/<id>/receipt` attaches a receipt.
- `GET /v1/settings` returns the machine list, to pick a `machine_id`.

An unknown or revoked key gets 401. Add an optional `"ref"` (up to 100 characters) to an entry so a retry cannot create it twice: posting a `ref` that is already live returns 200 with `{"id": <existing id>, "existing": true}` and adds nothing. After an entry is voided, its `ref` can be used again.

Keep keys off the public internet like the rest of this service, and use one key per app.

## Optional: BloomGauge

Nothing here needs BloomGauge. If you use it, tick the box in `/setup`, answer yes in the Mac installer, or set `BLOOM_BLOOMGAUGE=1`. Status shows "optional: not set up" until then, and that is never counted as a problem.

## Privacy and security

Writes require login. Reads are open on your network, so do not expose the port to the internet without a reverse proxy or tunnel with its own login. Secrets are never logged.

## Developing

See CONTRIBUTING.md. Tests: `PYTHONPATH=lib python -m pytest ingest`.

Licence: MIT (see LICENSE).
