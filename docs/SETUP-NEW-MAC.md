# Set up a new Mac (Darkbloom + bloom-ledger)

A step-by-step guide to adding one more Mac to a ledger you already run. Follow the steps in order. Every step says what success looks like and what to do if it does not happen. It assumes you work alone, with a keyboard and screen on the new Mac for the first part and a browser on any computer for the ledger part.

Placeholders used below. Replace them with your own values, without the angle brackets:

| Placeholder | Meaning |
|---|---|
| `<LEDGER_URL>` | The address your Macs use to reach the ledger, for example `http://ledger-host:8787`. It must be a private address or a name, not a public IP. |
| `<MACHINE_ID>` | A short name for this Mac: lowercase letters, digits, `-` or `_`, at most 32 characters, starting with a letter or digit. Examples: `studio2`, `m5ultra`. It can never be renamed later. |
| `<PAIR_CODE>` | The one-time code the ledger shows when you add the Mac. Works once, expires after 30 minutes. |
| `<API_KEY>` | Optional: a Darkbloom API key, only for a Mac that belongs to a different Darkbloom account than the one saved in the ledger. Leave it out otherwise. |

What a Mac's credential is: each Mac reports with its own machine token. You never type it. The ledger makes it when you add the machine, and the installer stores it in that Mac's login Keychain. There is no separate key to create per Mac. (Settings > API keys, if your ledger has it, is for other apps that post cost entries. It is not used by Macs.)

## Part 1. Before you start

**1. Collect what you need.**
- `<LEDGER_URL>` and the ledger login (if you created one at `/setup`).
- The Darkbloom account login (a browser approves the Mac later).
- For the cost record: the purchase price, the date the Mac went into service, and the receipt if you have one.
- A name for the Mac: `<MACHINE_ID>`.

**2. Check the ledger is up.** From any computer on the network:

```sh
curl -fsS <LEDGER_URL>/v1/hello
```

Success: one line of JSON containing `"service": "bloom-ledger"`.
If it fails: the server is down or the address is wrong. On the ledger host run `docker compose ps` (it should say `healthy`) and `docker compose exec bloom-ledger python3 /app/server.py doctor`. For a Mac-hosted server, see "Troubleshooting" in the README. Do not continue until this works.

## Part 2. macOS first boot

**3. Finish the setup assistant and update macOS.** Create the user the Mac will run as (use the same user for everything below, never `root`). Then open System Settings > General > Software Update and install updates until it says the Mac is up to date. Darkbloom needs macOS 27 or later to serve.
Success: `sw_vers -productVersion` prints 27 or higher.
If it fails: the Mac may be too old for macOS 27. Darkbloom cannot serve on it.

**4. Never sleep.** Open Terminal and run:

```sh
sudo pmset -a sleep 0 displaysleep 0 disksleep 0 womp 1 autorestart 1
pmset -g | grep -E "^ *(sleep|displaysleep|disksleep|womp|autorestart) "
```

Success: `sleep 0`, `displaysleep 0`, `disksleep 0`, `womp 1` and `autorestart 1` are listed. (`displaysleep 0` is optional: if you would rather the display turn off, leave it out. The Mac itself must still never sleep.)
If a line is missing or different: run the first command again and check you typed your own password.

**5. Start up after a power cut.** Step 4 already set it (`autorestart 1`). Confirm in the settings window too: System Settings > Energy, turn on "Start up automatically after a power failure" (and "Wake for network access"). On some Macs the page is System Settings > Battery > Options or Energy > Options.
Success: both switches are on.
If the switch is missing: your macOS version moved it. Search System Settings for "power failure". The `pmset` value from step 4 is the real setting.

**6. Automatic login.** Darkbloom and the ledger client run as launch agents inside your logged-in desktop session. After a restart with nobody logged in they do not start. Open System Settings > Users & Groups > Automatic login and pick your user.
Success: the pop-up lets you choose the user and asks for the password once.
If "Automatic login" is greyed out or missing: FileVault is on (macOS does not allow both), or the account uses an Apple ID with a password rule. Turn FileVault off in System Settings > Privacy & Security > FileVault, then try again. With FileVault on, someone must type the password at the screen after every restart, and nothing earns until they do. Decide this before you go on.

**7. Remote access, so you can fix the Mac without a screen.** System Settings > General > Sharing: turn on "Remote Login" (SSH) and "Screen Sharing".
Success: from another computer, `ssh <user>@<mac-name>.local` asks for a password.
If it fails: the two Macs are on different networks, or "Allow access for" excludes your user. Add your user in the Remote Login info panel.

**8. Install the command line tools** (this gives you Python 3 and git, which the ledger client needs):

```sh
xcode-select --install
```

Click Install in the pop-up and wait until it finishes.
Success: `python3 --version` prints 3.9 or higher.
If it says the tools are already installed, that is fine. If `python3` is missing or older than 3.9, install Homebrew (step 9) and run `brew install python`.

**9. Install Homebrew and `macmon`** (macmon reads the power sensors; without it the ledger shows "power unavailable"). Get the Homebrew install line from https://brew.sh, paste it into Terminal, and follow what it prints (it ends by telling you to add Homebrew to your PATH: do that). Then:

```sh
brew install macmon
command -v macmon
```

Success: the last command prints a path.
If it fails: close and reopen Terminal so the PATH change applies, then run the two lines again. You can skip this step; the ledger installer in step 18 installs macmon itself if Homebrew is present.

## Part 3. Darkbloom

**10. Install Darkbloom.** This is Darkbloom's own installer. It needs no `sudo`.

```sh
curl -fsSL https://api.darkbloom.dev/install.sh | bash
exec $SHELL -l
darkbloom --version
```

Success: the installer prints its five steps and ends with a version number, and `darkbloom --version` prints it again.
If it fails: read the line it printed. "needs macOS 27" means go back to step 3. A network error means the Mac cannot reach `api.darkbloom.dev` on port 443. If `darkbloom` is "not found" after the install, run `~/.darkbloom/bin/darkbloom --version`; if that works, open a new Terminal window.

**11. Link the Mac to your Darkbloom account and start it.**

```sh
darkbloom login
darkbloom start
```

`login` prints a web address and a short code and opens your browser: sign in and approve it. `start` shows the terms notice (starting accepts them), asks you to pick models, and starts a background service. A first start serves the Darkbloom network and this Mac's own local API.
Success: `start` ends saying the provider is running. If it asks "Link account?" answer `y`.
If it fails: read the message. "No model to serve yet" means download one first with `darkbloom models catalog` and `darkbloom models download <id>`, then run `darkbloom start` again. If it complains the provider is outside the GUI session, you are connected over SSH: run the command in Terminal on the Mac's own desktop (or in Screen Sharing).

**12. Check Darkbloom is healthy.**

```sh
darkbloom status
darkbloom doctor --strict
```

Success: `status` shows the daemon running and connected, and `doctor` shows no failing lines (a check mark for the account link and the trust level). Approval for serving can take a few minutes after the first start; run `doctor` again.
If a line fails: the doctor prints a fix next to it. The usual ones are "log in and enable automatic login" (step 6), "run `darkbloom restart` from the logged-in desktop", and "run `darkbloom login`".

**13. Keep automatic updates on.** Darkbloom updates itself and restarts the provider. Leave that on: do not pin the version and do not turn updates off.

```sh
darkbloom autoupdate status
```

Success: it says automatic updates are enabled. If not, run `darkbloom autoupdate enable`.
What to expect: an update restarts the provider, so anything using it can see errors for a short while. Wait about a minute and it comes back by itself. The ledger client only reads Darkbloom's files and keeps running through an update. If you use Darkbloom's fan helper, run `sudo darkbloom fan enable` after an update, because the updater does not replace the root helper. If a new version misbehaves, `darkbloom update --rollback` goes back one release without turning automatic updates off.

**14. Restart test.** Restart the Mac from the Apple menu and do not touch it. Wait five minutes, then from another computer:

```sh
ssh <user>@<mac-name>.local '~/.darkbloom/bin/darkbloom status'
```

Success: the daemon is running and connected, with nobody having logged in by hand.
If it is not running: step 6 (automatic login) did not take, or FileVault is waiting for a password at the screen. Fix that, then check again.

## Part 4. The ledger

**15. Sign in to the ledger.** In a browser on any computer open `<LEDGER_URL>/login` and sign in. (On an older install that never created a login, there is nothing to sign in to: skip this step.)
Success: the Home page opens and you are signed in.
If you forgot the password: Docker: `docker compose exec bloom-ledger python3 /app/server.py reset-admin` on the server, then open `<LEDGER_URL>/setup`. Five wrong passwords lock the login for a minute.

**16. Add the machine.** Open `<LEDGER_URL>/settings`, scroll to "Add a machine", type `<MACHINE_ID>` in "Machine id", and click "Add machine". Leave the Darkbloom API key box empty unless this Mac uses a different Darkbloom account (then paste `<API_KEY>`).
Success: a box appears titled "Token for `<MACHINE_ID>`" with an install command underneath, and the machine shows in the Machines table above.
If it says "That machine id already exists": pick another id, or use New token on the existing row. If it says "No local network address is known": open Settings through the ledger's private address instead of a public name (or ask whoever runs the server to set `BLOOM_LEDGER_LAN_URL`), then add the machine again. If it says the id is not valid: use only lowercase letters, digits, `-` and `_`.

**17. Copy the install command now.** Click "Copy install command". It looks like this:

```sh
curl -fsSL <LEDGER_URL>/install.sh | sh -s -- --pair <PAIR_CODE>
```

It works once and expires after 30 minutes. If you close the box before using it, click New token on that machine's row for a fresh command. Do not click "Done" until you have pasted it on the Mac.
Add `--earnings` at the end of the command only if this Mac should also archive Darkbloom earnings, and only on one Mac per Darkbloom account. If an existing Mac already does, leave it off.

**18. Run the command on the new Mac.** Paste it into Terminal on the Mac. Do not put `sudo` in front of it.
Success: it prints `pairing`, then `installed as machine '<MACHINE_ID>', shipping to <LEDGER_URL>`, then runs the doctor and ends with `done`. macOS may ask once to let `security` use the Keychain: allow it.
If it fails: "can't reach the ledger" means this Mac cannot see the server (check the address, the network or VPN). "pairing failed" means the code was used or older than 30 minutes: get a new one (New token) and rerun. "needs Python 3.9+" means step 8. "is not a private address or a hostname" means the address in the command is a public IP: open Settings through the ledger's private address and copy the command again. The installer is safe to run again.

**19. Run the Mac's own check.**

```sh
python3 "$HOME/Library/Application Support/bloom-ledger/client/bloom-doctor.py"
```

Success: no line fails. The checks cover that the ledger is reachable, that it accepts this Mac's token, that Darkbloom's data is found and that the background jobs are loaded.
If a line fails: it prints a `fix:` line under it. Do what it says and rerun. "Ledger accepts this Mac's token" failing means making a new code (step 17) and running the installer again.

**20. Confirm the ledger sees the Mac.** Open `<LEDGER_URL>/status`. Within about 10 minutes the new machine shows "reporting" with a small "last seen" age.
Success: the page says all Macs are reporting.
If the machine says "silent" or "waiting": wait ten minutes first. Then check the Mac is awake and online, and rerun step 19.

## Part 5. Name the machine and record its cost

**21. Fill in the machine row.** On `<LEDGER_URL>/settings`, find the new row in the Machines table and fill in:
- Display name (for example "Mac Studio M5 Ultra 512GB").
- Model.
- Acquired: Purchased (or Leased, with the lease start and the amount per month).
- In service: the date the Mac started working for Darkbloom.
- Purchase price: the total in dollars.

Click Save on that row.
Success: "Saved." appears next to the button.
If it shows an error: the price must be a positive number and the date must be a real date. Set Acquired first, then the date and price, then Save.

**22. Check the cost counts.** Open `<LEDGER_URL>/settings/depreciation`.
Success: the new machine is listed with a basis equal to the purchase price and a schedule underneath.
If it says "no purchase price or hardware cost entry, so nothing to depreciate yet": step 21 was not saved, or Acquired is still Leased. Fix the row and save again.
The machine row is the hardware cost. Do not also enter the same purchase as a Hardware entry on the Home page "Add entry" form: a hardware entry is depreciated as its own asset, so entering both can count it twice.

## Part 6. Verify the first earnings report

**23. Wait for data.** The client sends data every minute and seals a day's record once a day. Power minutes show within a few minutes. Earnings appear after Darkbloom credits the Mac and the Mac that has `--earnings` archives them (every five minutes).

**24. Look at the Home page.** Open `<LEDGER_URL>/` and choose the new Mac in the Machine drop-down (or compare "All machines" before and after).
Success: the Mac shows power use today, and, once Darkbloom has paid it, earnings for the day.
If power shows but earnings stay at zero for over a day: first check Darkbloom itself (`darkbloom status`, and the earnings on your Darkbloom account page). If Darkbloom shows earnings and the ledger does not, make sure exactly one Mac has the earnings job: on that Mac run `launchctl list | grep bloom-ledger` and look for `dev.bloom-ledger.earnings`. If it is missing, rerun that Mac's install command with a fresh code and `--earnings`.

**25. Check the day seals.** The next day, open `<LEDGER_URL>/settings` and look at the Machines table.
Success: the Mac's "Days sealed" count has gone up by one.
If it has not: the daily seal runs at 01:05 Mac time. Check the Mac was awake then and run step 19.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `bloom-doctor` says power is unavailable | `brew install macmon`, then wait a few minutes. |
| Ledger says a Mac is silent | Wake the Mac, check it is online, then run step 19 on it. |
| After a power cut nothing runs until you log in | Automatic login is off (step 6) or FileVault is on. |
| Darkbloom shows offline right after an update | Wait a minute. If it stays down: `darkbloom restart` from the desktop session, then `darkbloom doctor`. |
| Installer says "port is already in use" or "Cannot connect to the Docker daemon" | These are server-side messages: see Troubleshooting in the README. |
| You added the wrong id | An id cannot be renamed. Run Machines > Remove on that row (its history is kept), then add the machine again with the right id. |
| You want the Mac out of the ledger | `curl -fsSL <LEDGER_URL>/install.sh \| sh -s -- --uninstall` on the Mac, then Machines > Remove in the ledger. |

## Checklist

- [ ] Ledger answers `/v1/hello` (step 2)
- [ ] macOS 27 or later, up to date (3)
- [ ] Never sleeps, restarts after power loss (4, 5)
- [ ] Automatic login on, FileVault decision made (6)
- [ ] Remote Login and Screen Sharing on (7)
- [ ] Python 3.9+ and `macmon` installed (8, 9)
- [ ] Darkbloom installed, logged in, started, `doctor` clean (10 to 12)
- [ ] Automatic updates still enabled (13)
- [ ] Survived a restart with nobody logging in (14)
- [ ] Machine added in the ledger and install command run (16 to 18)
- [ ] `bloom-doctor` passes and `/status` shows "reporting" (19, 20)
- [ ] Machine row saved with price and in-service date (21)
- [ ] Depreciation page shows the machine with a basis (22)
- [ ] First power and earnings visible (24), day sealed next day (25)
