# bloom-ledger

Tamper-evident record keeping for Darkbloom provider machines. Machines POST content-addressed objects (power and earnings snapshots) to a small stdlib-only Python server. The server indexes them in SQLite and closes each UTC day into a hash-chained manifest. A web dashboard at `/` shows each machine's last 90 days of manifests, and `/v1/alerts` reports silent machines and stale ring snapshots.

This is bookkeeping data, not tax advice.

## Run (Docker Compose)

```
git clone https://github.com/frindle/bloom-ledger.git
cd bloom-ledger
./update.sh
```

`update.sh` writes a `.env` on first run (git-ignored; edit it to move things), builds the image and starts the container. On Unraid the `.env` points at `/mnt/user/data/Docker/bloom-ledger` for data `/mnt/user/appdata/bloom-ledger/secrets` for optional secret files and `/mnt/user/appdata/bloom-ledger/keys` for keys saved in the web UI; elsewhere it uses `./data` and `./secrets` owned by you. Run `./update.sh` again to update. No secret files are needed to start: machines are added in the web UI.

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

Changes need no password: the server only accepts them from a private (LAN) address with a same-origin request, and refuses anything that arrives through a public proxy. That is a guard, not authentication, so never expose port 8787 to the internet. The page also lets you edit each machine's display name, model, leased-or-purchased label (informational; it does not change accounting) and lease, and links to `/settings/accounting`. Machines added here are stored as token hashes in `/data/machines.json`. An optional legacy `secrets/bloom_tokens` file (one `<machine_id> <sha256 of token>` per line) stays read-only and wins if the same id is in both, until you press **New token** for that machine: the machine then moves to `machines.json` with the new token and its old line is ignored. Darkbloom API keys (optional; Darkbloom does not accept them for live status yet, see Layr-Labs/d-inference#1760) are kept in `BLOOM_KEYS_DIR` (default `data/secrets`, mode 600), never shown again and only sent to Darkbloom over https. Reads are open.

Tunnel access: settings writes that arrive through a public Cloudflare tunnel need a verified Cloudflare Access JWT (RS256). The team domain and the application AUD come from the `BLOOM_ACCESS_TEAM_DOMAIN` and `BLOOM_ACCESS_AUD` environment variables (set them in a git-ignored `.env` next to `compose.yaml`); if either is unset, tunnel writes fail closed. Cloudflare Access must stay in front of the hostname. The token's email claim only has to exist; it is not matched against an allowlist, so the Access policy is the access control. The Access policy and the tunnel configuration live outside this repository.

The optional `bloom-earnings` service archives Darkbloom earnings from the same image (`docker compose --profile earnings up -d`) and needs a `secrets/darkbloom_token` file. Run only one earnings poller per Darkbloom account.

## Monthly tally (for the resell-tracker's books)

Read-only, open on the LAN like the other reads; nothing in it is a token, key or secret.

`GET /v1/tally/monthly?month=YYYY-MM` returns `month`, `timezone`, `day_boundary`, `rounding`, `generated_at`, `final`, `hash`, `balances`, `totals` and `machines`. `machines` has one row per machine that has data or an entry that month (every machine record in Settings, too), plus a row with `"shared": true` and `machine_id: null` for entries with no machine and for pre-tracking pay. Each row has `earnings_cents` (all Darkbloom pay, as the tax report's income), `other_income_cents`, `power_cost_cents` (deductible power under the write-off rules in effect), `depreciation_cents` and `lease_cents` (business share), `entries_deductible_cents` and `entries`. Each entry has `id, kind, date, category, vendor, purpose, business_pct, amount_cents, deductible_cents` and `effect`. An entry of kind `receipt` is money received (other income, Schedule C line 6), not a receipt file: it counts in `other_income_cents`, its `deductible_cents` is 0 and its `effect` is `income`. Hardware entries are `capitalized` (depreciated instead) and electricity entries are `metered_power` (already in the metered power cost), both with `deductible_cents` 0. Voided entries are left out. A column is `null` when the month's total cannot be computed (no rate schedule, an owned machine without a cost); legacy single-machine settings put depreciation and lease on the shared row.

`balances` is the latest Darkbloom totals snapshot at or before the month's end, `{as_of, available_cents, withdrawable_cents}`, or `null`. `final` is true only when the month has ended and the newest earnings poll the ledger holds (latest totals snapshot, the server-side form of `archive_settled_until`) is at least the settle window (`SETTLE_S`, 15 minutes) past the month's end. `hash` is the sha256 of the canonical JSON (sorted keys, no spaces) of `machines` and `balances`; if it changes for a month you already booked, post a correction.

`GET /v1/tally/months` lists the months with data as `{month, final, hash}`, oldest first. A missing or malformed `month` (or any unknown query parameter) is a 400.

Conventions: a month is the local calendar month in the `local_timezone` setting effective on its last day (default America/Los_Angeles), from 00:00 on the 1st to 00:00 on the next 1st, the same day boundary as the tax report and packet; entries use their own date. The write-off rules and other settings are those effective on the month's last day (the tax report uses the year's December 31 settings for the whole year, so the two differ only after a mid-year rule change). Money is integer cents: each column's month total is converted from micro-USD to cents once, rounded down, equal to the report's month figure divided by 10000; the machine rows split that total by largest remainder, so they always add up. Twelve monthly tallies therefore sum to within a cent per month of the tax report's year total.

## Monthly invoice (for the resell-tracker's side-hustle P&L)

Read-only and open on the LAN like the tally; no secrets in it. `GET /v1/invoice/monthly?month=YYYY-MM` returns a mock invoice built on that month's tally: `invoice_id` (`BL-YYYY-MM`), `issue_date` (the 1st of the next month), `gross_cents`, `lines` (inference, sandbox, base reward, plus "other earlier pay" when the day rows do not carry all of the pay; they always add up to `gross_cents`), `other_income_cents`, `costs` (metered power, depreciation, lease, purchases; an amount is `null` when it cannot be computed and is listed in `costs_unknown`), `net_cents`, `usage` (`tokens`, `jobs`, `inference_minutes`, `sandbox_minutes`), `final` and `hash`. Net = gross - Darkbloom fees - power - depreciation - lease (plus other income, less hand-entered expenses); the Mac is owned, so its depreciation counts, and the lease line is 0 when no lease is set. The ledger stores what Darkbloom paid out (cost minus its fee): Darkbloom keeps 10% of Sandbox cost and nothing on inference, so `fees_cents` is the month's Sandbox payout divided by 9 and `gross_cents` is payout plus fees (the fee is taken off once, so net equals payout - power - depreciation - lease). The earnings feed carries no per-row fee, which is why it is computed. `usage.vcpu_seconds` is always `null` (the earnings feed has no vCPU seconds). The tally (`schema_version` 3) carries the same `fees_cents` column, so the books and the invoice give one net for every month. `GET /v1/invoice/months` lists `{month, final, hash}` for the months with data. The resell-tracker pulls these and keeps one invoice per month.

## Withdrawal requests (read-only)

`GET /v1/withdrawals` lists the Darkbloom withdrawal requests the balance snapshots show: `{key, requested_at, since, amount_cents}`, oldest first. Darkbloom's public API has no payout list, so a request is found the way the API-spend reconcile works: between two consecutive `account_totals` snapshots the withdrawable balance moves by earnings minus the API draws, and a drop the rows do not explain (more than the larger of 5 cents and 2% of earnings plus draws) is money that left, i.e. a withdrawal. If credits (available minus withdrawable) fell by the draws, the draws came out of credits and are not subtracted. Record only: the ledger never calls a Darkbloom write endpoint. Two withdrawals between the same two snapshots read as one, and a card top-up in the same window can make the amount read low; the tracker accepts a hand-entered request for those.

## Earnings graph

The home page's **Earnings over time** section draws `GET /v1/earnings/series` as inline SVG: stacked daily or monthly bars (inference, sandbox, base reward) and a running-total line on the right-hand axis, with a table of the same figures under it. Days are local days in the books' timezone, zero-filled up to today.

## Tests

```
pip install pytest
PYTHONPATH=lib python -m pytest ingest
```

## Darkbloom API spend and the install address

Every 15 minutes the ledger reads `GET /v1/payments/usage` with the account key saved in Settings and stores new rows in `api_spend` (request id is the key; reading stops at the first row already stored). Only rows at or after the `api_spend_from_ts` setting (epoch seconds, set through `/v1/accounting/settings`; env `BLOOM_API_SPEND_FROM_TS` as a fallback) are kept; with neither set nothing is read. A 401/403 is skipped and shown under the key status in Settings. Every usage row is treated as the owner's personal use: an owner draw from the Darkbloom balance, never an expense against Darkbloom income. A card top-up is entered by hand as an entry of type "Card top-up" (kind `contribution`). The monthly tally (`schema_version` 2) adds an `account` block with `api_spend_draw_cents`, `contribution_cents`, items with effect `draw` or `contribution`, and a balance reconcile.

The Add a machine command and `/install.sh` always use a private IPv4 address (10/8, 172.16/12, 192.168/16): the request's Host when it is one, else `BLOOM_LEDGER_LAN_URL`; with neither, a message instead of a command. `install.sh` itself refuses any other address before pairing.
