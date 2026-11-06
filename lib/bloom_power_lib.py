#!/usr/bin/env python3
"""Shared pure helpers for the Darkbloom power + earnings bookkeeping tools (stdlib only).

Used by bloom-power-log.py (sampler), bloom-earnings-archive.py (earnings poller) and
bloom-power-report.py (monthly report). Everything here is pure or takes explicit paths so the
tests can run against temp dirs; nothing here talks to Darkbloom, binds a port or needs sudo.
This is bookkeeping data, not tax advice.
"""
import csv
import datetime as dt
import json
import os
import re
import statistics
from pathlib import Path

HOME_DIR = Path(os.environ.get("BLOOM_POWER_HOME") or Path.home() / ".darkbloom")
POWER_DIRNAME = "power"
ARCHIVE_DIRNAME = "earnings-archive"

POWER_COLUMNS = [
    "ts_utc", "interval_s", "samples", "power_ok", "avg_w", "max_w", "wh",
    "dbk_up", "dbk_state", "inference_active_frac", "requests_delta", "tokens_delta",
    "warm_models", "load_transition_active", "gpu_pct", "other_work", "other_procs", "note",
] + [
    # daemon-state.json snapshot columns (2026-10-30), APPENDED so older readers keep working. A month file whose
    # header predates them keeps its own header (csv_columns_for); the columns start with the next month's file.
    "machine_id", "daemon_started_at", "coordinator_connected", "coordinator_since",
    "requests_served", "tokens_generated", "prompt_tokens_processed", "cached_input_tokens", "reasoning_tokens",
    "usage_gaps", "cancellations_partial_complete", "resident_seconds",
]
DAEMON_STAT_KEYS = ("requests_served", "tokens_generated", "prompt_tokens_processed", "cached_input_tokens",
                    "reasoning_tokens", "usage_gaps", "cancellations_partial_complete")
DAEMON_COLUMNS = POWER_COLUMNS[POWER_COLUMNS.index("machine_id"):]
# Network bytes and sandbox jobs (2026-11-03). The main power-log header does NOT carry these columns (bloom-ledger
# reads them from the sidecar files below, written every minute by bridge_row), so the power-log CSV is unchanged.
# gpu_* = Darkbloom provider service; sandbox_* = Sandbox agent + workers (carry job VM traffic); total_* = en* links.
NET_COLUMNS = ["gpu_bytes_in", "gpu_bytes_out", "sandbox_bytes_in", "sandbox_bytes_out", "total_bytes_in", "total_bytes_out"]
# The Darkbloom Sandbox agent's status file (rewritten by the agent about every 30 s; READ-ONLY for us).
SANDBOX_STATUS = Path(os.environ.get("BLOOM_SANDBOX_STATUS")
                      or "/Volumes/NVMe-Models/DarkbloomSandbox/agent/status.json")
SANDBOX_PLIST = "~/Library/LaunchAgents/io.darkbloom.sandbox.agent.plist"
SANDBOX_HOME_STATUS = "~/DarkbloomSandbox/agent/status.json"
SANDBOX_LEGACY_STATUS = "/Volumes/NVMe-Models/DarkbloomSandbox/agent/status.json"
SANDBOX_WARN_AGE_S = 900.0     # a status older than this (or no file at all) beside an installed agent is an incident
SANDBOX_PROBLEM_NOTE = "sandbox status problem"
SANDBOX_STALE_S = 300.0        # an older status is a stopped agent's last word: its jobs_running is not counted
SANDBOX_BRIDGE = "sandbox-jobs-{month}.csv"     # power dir: ts_utc,sandbox_jobs while the month file lacks the column
SANDBOX_BRIDGE_COLUMNS = ["ts_utc", "sandbox_jobs"]
# Sandbox processes are Darkbloom business, never the operator's other work: the agent and its worker helpers run from
# DarkbloomSandbox.app; each job's VM runs in a Virtualization.framework XPC service (ppid 1, no link to the job).
SANDBOX_PROCS = ("DarkbloomSandbox", "darkbloom-sandbox", "sandbox-linux-worker", "sandbox-macos-worker")
VM_SERVICE = "com.apple.Virtualization.VirtualMachine"
NET_BRIDGE = "net-bytes-{month}.csv"            # power dir: ts_utc + NET_COLUMNS while the month file lacks them
NET_BRIDGE_COLUMNS = ["ts_utc"] + NET_COLUMNS
BRIDGES = ((SANDBOX_BRIDGE, SANDBOX_BRIDGE_COLUMNS), (NET_BRIDGE, NET_BRIDGE_COLUMNS))

# Network bytes (read-only: nettop and netstat, no root). Per-process bytes come from ONE long-running nettop in
# delta mode (bloom-power-log.py NettopReader): each block is every process's bytes since the previous block on
# the given interface types, flows that closed in between included. Loopback is left out (the operator's own requests to
# the provider's 127.0.0.1:8000 are not network traffic). nettop types the Cloudflare WARP tunnel (utun*, where
# app traffic flows while WARP is on) as "undefined" and the physical NICs as "external".
NETTOP_CMD = ["/usr/bin/nettop", "-P", "-x", "-n", "-d", "-L", "0", "-s", "5", "-t", "external", "-t", "undefined",
              "-J", "bytes_in,bytes_out"]
NETSTAT_CMD = ["/usr/sbin/netstat", "-ibn"]   # -n: address-to-name lookups made -ib take 6.7 s (past the 5 s probe timeout)
NET_NAME_MAX = 15              # nettop prints at most 15 characters of a process name ("sandbox-macos-w")
NET_SANDBOX_NAMES = tuple(sorted({p[:NET_NAME_MAX] for p in SANDBOX_PROCS + (VM_SERVICE,)}))
DARKBLOOM_SERVICE_CMDS = ("start", "watchdog")     # the `darkbloom <cmd>` processes that are the provider service
NET_MAX_BPS = 5e9              # 40 Gbit/s, above any link here (en0 is 10GbE): more in a block is a glitch, counts 0
NET_IFACE_RE = re.compile(r"^en\d+$")              # physical Ethernet/Wi-Fi: not lo0, utun* (WARP inner), bridge*, awdl0


# the operator's own LLM work shares this Mac. Its power must NOT be attributed to Darkbloom.
# Patterns are matched against the full command line of running processes.
OTHER_WORK_PATTERNS = [
    r"ollama-worker\.py", r"ollama[ -]runner", r"\bollama runner\b", r"mlx_lm", r"mlx-lm",
    r"code-review-agent\.py", r"llama-server", r"llama\.cpp", r"comfyui", r"pipeline-canary\.py",
    r"darkbloom_chat\.py", r"darkbloom-coldload", r"bakeoff-runner\.py", r"ollama-dispatch-[a-z]+",
]
HEAVY_CPU_PCT = 150.0          # a non-Darkbloom process this busy also counts as "other work"
IGNORE_HEAVY = ("darkbloom", "macmon", "kernel_task", "WindowServer", "bloom-power")
DBK_LOCAL_PORT = 8000


# ---------------------------------------------------------------- time helpers
def utc_iso(ts):
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(s):
    s = str(s).strip().replace("Z", "+00:00")
    d = dt.datetime.fromisoformat(s)
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    return d.astimezone(dt.timezone.utc)


def month_of(ts_utc_str):
    return str(ts_utc_str)[:7]


# ---------------------------------------------------------------- atomic append
def append_line(path, line):
    """One O_APPEND write per record: records never interleave or tear (single write < PIPE_BUF-ish,
    and O_APPEND positions atomically on a local fs). Creates parent dirs."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (line.rstrip("\n") + "\n").encode()
    fd = os.open(str(path), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(fd, data)
    finally:
        os.close(fd)


def append_csv_row(path, columns, row):
    """Append one CSV row; the header goes in the SAME write that creates the file (O_EXCL), so a new
    month's file is never headerless and concurrent writers never double the header."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    def render(cols):
        vals = []
        for c in cols:
            v = row.get(c, "")
            v = "" if v is None else str(v)
            if any(ch in v for ch in ',"\n'):
                v = '"' + v.replace('"', '""') + '"'
            vals.append(v)
        return ",".join(vals) + "\n"

    hdr = ",".join(columns) + "\n"
    try:
        fd = os.open(str(path), os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_EXCL, 0o644)
        data = hdr + render(columns)
    except FileExistsError:
        fd = os.open(str(path), os.O_WRONLY | os.O_APPEND, 0o644)
        if os.fstat(fd).st_size == 0:
            data = hdr + render(columns)
        else:
            data = render(csv_columns_for(path, columns))
    try:
        os.write(fd, data.encode())
    finally:
        os.close(fd)


def power_log_path(base, ts_utc_str):
    return Path(base) / POWER_DIRNAME / f"power-log-{month_of(ts_utc_str)}.csv"


# ---------------------------------------------------------------- Darkbloom state signals
def classify_state(dbk_up, inference_frac, requests_delta, tokens_delta):
    """off = provider process not up; serving = the daemon reported inference_active at any poll in
    the interval OR its served counters advanced; idle = up but neither (online, waiting for work)."""
    if not dbk_up:
        return "off"
    if (inference_frac or 0) > 0 or (requests_delta or 0) > 0 or (tokens_delta or 0) > 0:
        return "serving"
    return "idle"


def counter_delta(prev, cur):
    """Delta of a monotonically growing counter. A reset (provider restart) -> the new value counts
    as the delta; unknown previous -> 0 (no baseline yet)."""
    if prev is None or cur is None:
        return 0
    return cur - prev if cur >= prev else cur


def read_daemon_state(path, now, max_age_s=45.0):
    """Return dict(ok, pid, inference_active, request_work_pending, requests, tokens, warm_models,
    load_transition_active, age_s). ok=False when missing/corrupt/stale (never raises)."""
    try:
        d = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return {"ok": False}
    try:
        age = now - float(d.get("written_at", 0))
    except (TypeError, ValueError):
        age = 1e9
    st = d.get("stats") or {}
    return {
        "ok": age <= max_age_s,
        "age_s": age,
        "pid": d.get("pid"),
        "inference_active": bool(d.get("inference_active")),
        "request_work_pending": bool(d.get("request_work_pending")),
        "requests": st.get("requests_served"),
        "tokens": st.get("tokens_generated"),
        "warm_models": list(d.get("warm_models") or []),
        "load_transition_active": bool(d.get("load_transition_active")),
        "extra": daemon_fields(d),
    }


def daemon_fields(d):
    """The DAEMON_COLUMNS values from one parsed daemon-state.json dict. Never raises; anything missing or of the
    wrong type becomes "" (bool is not a number here)."""
    if not isinstance(d, dict):
        d = {}
    out = {}
    # machine_id
    try:
        mid = d["trust"]["authorization"]["machine_id"]
        out["machine_id"] = mid.strip() if isinstance(mid, str) else ""
    except Exception:
        out["machine_id"] = ""
    # daemon_started_at
    try:
        sa = d["started_at"]
        if isinstance(sa, bool) or not isinstance(sa, (int, float)) or sa <= 0:
            out["daemon_started_at"] = ""
        elif sa > 1e11:
            out["daemon_started_at"] = utc_iso(sa / 1000.0)
        else:
            out["daemon_started_at"] = utc_iso(sa)
    except Exception:
        out["daemon_started_at"] = ""
    # coordinator_connected
    try:
        cc = d["coordinator_connection"]["connected"]
        out["coordinator_connected"] = int(cc) if isinstance(cc, bool) else ""
    except Exception:
        out["coordinator_connected"] = ""
    # coordinator_since
    try:
        cs = d["coordinator_connection"]["since"]
        if isinstance(cs, bool) or not isinstance(cs, (int, float)) or cs <= 0:
            out["coordinator_since"] = ""
        elif cs > 1e11:
            out["coordinator_since"] = utc_iso(cs / 1000.0)
        else:
            out["coordinator_since"] = utc_iso(cs)
    except Exception:
        out["coordinator_since"] = ""
    # DAEMON_STAT_KEYS counters
    for k in DAEMON_STAT_KEYS:
        try:
            v = d["stats"][k]
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                out[k] = ""
            else:
                out[k] = int(v)
        except Exception:
            out[k] = ""
    # resident_seconds
    try:
        rm = d["autopilot_state"]["resident_models"]
        if isinstance(rm, list):
            total = 0
            for item in rm:
                if isinstance(item, dict):
                    rs = item.get("resident_seconds")
                    if isinstance(rs, bool) or not isinstance(rs, (int, float)):
                        pass  # counts as 0
                    else:
                        total += int(rs)
                # non-dict items count as 0
            out["resident_seconds"] = total
        else:
            out["resident_seconds"] = ""
    except Exception:
        out["resident_seconds"] = ""
    return out




def csv_columns_for(path, columns):
    """Columns to use when appending to an EXISTING csv file: the file's own header when its first line is a
    complete, non-empty header (an older, shorter header keeps the file consistent: the newer fields are left out
    until the next month's file starts); otherwise `columns`. Never raises."""
    try:
        with open(path, newline="") as fh:
            first_line = fh.readline()
    except OSError:
        return list(columns)
    if not first_line.endswith("\n"):
        return list(columns)
    header = next(csv.reader([first_line]), [])
    if not header or any(field.strip() == "" for field in header):
        return list(columns)
    return header


# ---------------------------------------------------------------- Darkbloom Sandbox
def sandbox_plist_status(plist=SANDBOX_PLIST):
    """status.json beside the Sandbox agent's config, from the LaunchAgent's ProgramArguments (only that key is read):
    a `--config <path>` / `--config=<path>` argument, else an argument naming agent.json. The Sandbox installer's plist
    is `/bin/sh -c '... --args agent --config "$config"' <exe> <app> <log> <agent.json>`, so there the path only
    appears positionally. None when nothing matches."""
    try:
        import plistlib
        with open(os.path.expanduser(plist), "rb") as fh:
            args = [a for a in (plistlib.load(fh).get("ProgramArguments") or []) if isinstance(a, str)]
        for i, a in enumerate(args):
            if a == "--config" and i + 1 < len(args):
                return Path(os.path.expanduser(args[i + 1])).parent / "status.json"
            if a.startswith("--config="):
                return Path(os.path.expanduser(a[9:])).parent / "status.json"
        for a in reversed(args):
            p = Path(os.path.expanduser(a))
            if p.name == "agent.json":
                return p.parent / "status.json"
    except Exception:
        pass
    return None


def sandbox_status_candidates(env=None, plist=SANDBOX_PLIST):
    """status.json locations in priority order: $BLOOM_SANDBOX_STATUS, the LaunchAgent's --config dir, ~/DarkbloomSandbox, legacy."""
    env = os.environ if env is None else env
    out = [Path(env["BLOOM_SANDBOX_STATUS"])] if env.get("BLOOM_SANDBOX_STATUS") else []
    p = sandbox_plist_status(plist)
    if p:
        out.append(p)
    out += [Path(os.path.expanduser(SANDBOX_HOME_STATUS)), Path(SANDBOX_LEGACY_STATUS)]
    return list(dict.fromkeys(out))


def resolve_sandbox_status(env=None, plist=SANDBOX_PLIST):
    """(path, tried): the first existing candidate (path None when none exists) and every path tried."""
    tried = sandbox_status_candidates(env, plist)
    for c in tried:
        if c.exists():
            return c, tried
    return None, tried


def read_sandbox_auto(now, env=None, plist=SANDBOX_PLIST, max_age_s=SANDBOX_STALE_S):
    """read_sandbox_jobs on the resolved status.json -> (jobs, note). With the Sandbox LaunchAgent plist installed, a
    missing status.json or one older than SANDBOX_WARN_AGE_S gives a note starting SANDBOX_PROBLEM_NOTE (never a silent
    healthy 0). Never raises."""
    try:
        path, tried = resolve_sandbox_status(env, plist)
        installed = os.path.exists(os.path.expanduser(plist))
        if path is None:
            if installed:
                return 0, f"{SANDBOX_PROBLEM_NOTE}: no status.json (tried {', '.join(map(str, tried))})"
            return 0, ""
        jobs, note = read_sandbox_jobs(path, now, max_age_s)
        if installed:
            age = now - path.stat().st_mtime
            if age > SANDBOX_WARN_AGE_S:
                return jobs, f"{SANDBOX_PROBLEM_NOTE}: {path} is {int(age)}s old (tried {', '.join(map(str, tried))})"
        return jobs, note
    except Exception:
        return 0, ""


def read_sandbox_jobs(path, now, max_age_s=SANDBOX_STALE_S):
    """(jobs, note) from the Darkbloom Sandbox agent's status.json (READ-ONLY: the agent rewrites it).
    jobs is its jobs_running, or 0 when the file is missing or unreadable, the value is not a whole
    number >= 0 (bool is not a number here), or the status is older than max_age_s (updated_at, else
    the file's mtime): a stopped agent's last word is not a running job. note is "" except when a
    stale status still claimed jobs. Never raises."""
    try:
        p = Path(path)
        d = json.loads(p.read_text())
        mtime = p.stat().st_mtime
    except Exception:
        return 0, ""
    j = d.get("jobs_running") if isinstance(d, dict) else None
    if isinstance(j, bool) or not isinstance(j, (int, float)) or not 0 <= j < 1e6 or int(j) != j:
        return 0, ""
    j = int(j)
    at = d.get("updated_at")
    if isinstance(at, bool) or not isinstance(at, (int, float)) or not 0 < at < 1e11:
        at = mtime
    if now - at > max_age_s:
        return 0, (f"sandbox status stale ({j} jobs not counted)" if j else "")
    return j, ""


def bridge_row(base, row, columns=POWER_COLUMNS):
    """Append the row's ts_utc and values to each BRIDGES file whose columns the month's power-log header predates
    (csv_columns_for keeps such a header, so the bytes bloom_ledger's manifest covers never change):
    sandbox-jobs-YYYY-MM.csv (ts_utc,sandbox_jobs) and net-bytes-YYYY-MM.csv (ts_utc + NET_COLUMNS).
    -> the bridge paths written, in BRIDGES order ([] when the header has every column). Raises OSError."""
    have = set(csv_columns_for(power_log_path(base, row["ts_utc"]), columns))
    written = []
    for name, cols in BRIDGES:
        if all(c in have for c in cols[1:]):
            continue
        bridge = Path(base) / POWER_DIRNAME / name.format(month=month_of(row["ts_utc"]))
        append_csv_row(bridge, cols, row)
        written.append(bridge)
    return written


# ---------------------------------------------------------------- network bytes
def parse_nettop_line(line):
    """One line of `nettop -P -x -J bytes_in,bytes_out` CSV -> ("header", None) for a block header (it starts with
    ","), ("row", (name, pid, bytes_in, bytes_out)) for a process row, else (None, None). A process name may hold
    commas, dots and spaces, so a row is read from the right: name.pid,bytes_in,bytes_out, (trailing comma
    optional). A negative count is read as 0. Never raises."""
    s = str(line).rstrip("\r\n")
    if s.startswith(","):
        return "header", None
    f = s.split(",")
    if f and f[-1] == "":
        f = f[:-1]
    if len(f) < 3:
        return None, None
    try:
        b_in, b_out = int(f[-2]), int(f[-1])
    except ValueError:
        return None, None
    name, dot, pid = ",".join(f[:-2]).rpartition(".")
    if not dot or not name or not pid.isdigit():
        return None, None
    return "row", (name, int(pid), max(b_in, 0), max(b_out, 0))


def darkbloom_subcommand(cmd):
    """'start' for '/…/Darkbloom.app/Contents/MacOS/darkbloom start --foreground …' ('' when there is none)."""
    m = re.search(r"(?:^|/)darkbloom\s+([A-Za-z][\w-]*)", cmd or "")
    return m.group(1) if m else ""


def classify_net_proc(name, pid, cmd=None, provider_pid=None):
    """'gpu', 'sandbox' or None (machine total only) for one nettop process row. name is nettop's (at most
    NET_NAME_MAX characters); cmd the process's ps command line, None when unknown (it has exited).
    sandbox: a Sandbox agent or worker helper (SANDBOX_PROCS), or the Virtualization.framework VM service.
    gpu: a `darkbloom` process that is the provider (provider_pid, from daemon-state.json) or runs a
    DARKBLOOM_SERVICE_CMDS subcommand (start, watchdog). A `darkbloom status` or other CLI call (the queue polls
    status every ~10 s) is not the provider, nor is a darkbloom process that exited before ps saw it."""
    name = str(name or "")
    if any(name.startswith(p) for p in NET_SANDBOX_NAMES):
        return "sandbox"
    if name != "darkbloom":
        return None
    try:
        if provider_pid is not None and int(provider_pid) == int(pid):
            return "gpu"
    except (TypeError, ValueError):
        pass
    return "gpu" if darkbloom_subcommand(cmd) in DARKBLOOM_SERVICE_CMDS else None


def net_block_bytes(rows, dt_s, classify):
    """Sum one nettop delta block by class -> ({"gpu": [in, out], "sandbox": [in, out]}, notes). rows are
    parse_nettop_line tuples; classify(name, pid) -> 'gpu' | 'sandbox' | None. A row that moved more than
    NET_MAX_BPS allows in dt_s is a counter glitch, never traffic: it counts 0 and adds a note."""
    out = {"gpu": [0, 0], "sandbox": [0, 0]}
    notes = []
    try:
        cap = NET_MAX_BPS * max(float(dt_s), 1.0)
    except (TypeError, ValueError):
        cap = NET_MAX_BPS
    for name, pid, b_in, b_out in rows:
        cls = classify(name, pid)
        if cls not in out:
            continue
        if b_in > cap or b_out > cap:
            notes.append(f"net spike dropped ({cls}: {name}.{pid})")
            continue
        out[cls][0] += b_in
        out[cls][1] += b_out
    return out, notes


def parse_netstat_ib(text):
    """`netstat -ibn` -> {iface: (ibytes, obytes)} for the physical interfaces (NET_IFACE_RE) from each one's
    <Link#n> row: 64-bit link-layer counters. Columns are read from the right (an interface without a link
    address has no Address column); a down interface's name ends in '*'. Never raises."""
    out = {}
    for ln in str(text or "").splitlines():
        p = ln.split()
        if len(p) < 9 or not p[2].startswith("<Link#"):
            continue
        name = p[0].rstrip("*")
        if not NET_IFACE_RE.match(name) or name in out:
            continue
        try:
            out[name] = (int(p[-5]), int(p[-2]))
        except ValueError:
            continue
    return out


def iface_bytes_delta(prev, cur, dt_s):
    """Bytes the physical interfaces moved between two parse_netstat_ib readings dt_s apart -> (in, out, notes).
    An interface missing from prev counts 0 (no baseline yet); one whose counter went down (reset, re-created)
    counts 0, never a negative; one that moved more than NET_MAX_BPS allows in dt_s counts 0 with a note."""
    t_in = t_out = 0
    notes = []
    try:
        cap = NET_MAX_BPS * max(float(dt_s), 1.0)
    except (TypeError, ValueError):
        cap = NET_MAX_BPS
    for name, (c_in, c_out) in sorted((cur or {}).items()):
        if name not in (prev or {}):
            continue
        p_in, p_out = prev[name]
        d_in, d_out = c_in - p_in, c_out - p_out
        if d_in < 0 or d_out < 0:
            continue
        if d_in > cap or d_out > cap:
            notes.append(f"net spike dropped (total: {name})")
            continue
        t_in += d_in
        t_out += d_out
    return t_in, t_out, notes


# ---------------------------------------------------------------- non-Darkbloom work detection
def detect_other_work(ps_rows, local_clients, patterns=None, sandbox_vms=0):
    """ps_rows: [(pid, pcpu, command)]; local_clients: [(procname, pid)] of non-darkbloom processes
    holding an ESTABLISHED connection to Darkbloom's local endpoint (127.0.0.1:8000: the operator's own
    requests, never network jobs). sandbox_vms: Darkbloom Sandbox jobs running now: that many busy VM_SERVICE
    processes are the sandbox's VMs, not other work; the sandbox's own processes (SANDBOX_PROCS) never are. Returns sorted unique short names."""
    pats = [re.compile(p) for p in (patterns or OTHER_WORK_PATTERNS)]
    names = set()
    try:
        vms_left = max(int(sandbox_vms or 0), 0)
    except (TypeError, ValueError):
        vms_left = 0
    for pid, pcpu, cmd in ps_rows:
        base = os.path.basename(cmd.split(" ")[0]) if cmd else "?"
        hit = None
        for p in pats:
            m = p.search(cmd)
            if m:
                hit = m.group(0)
                break
        if hit:
            names.add(hit.replace("\\", ""))
        elif pcpu >= HEAVY_CPU_PCT and not any(x in cmd for x in IGNORE_HEAVY + SANDBOX_PROCS):
            if vms_left and VM_SERVICE in cmd:
                vms_left -= 1
                continue
            names.add(f"cpu>{int(HEAVY_CPU_PCT)}%:{base}")
    for name, _pid in local_clients:
        names.add(f"local-endpoint-client:{name}")
    return sorted(names)


def parse_lsof_clients(text, port=DBK_LOCAL_PORT):
    """Parse `lsof -nP -iTCP:<port> -sTCP:ESTABLISHED` -> non-darkbloom client (name, pid) list."""
    out, seen = [], set()
    for ln in text.splitlines()[1:]:
        parts = ln.split()
        if len(parts) < 9:
            continue
        name, pid = parts[0], parts[1]
        if name.lower().startswith("darkbloom"):
            continue
        if f"->127.0.0.1:{port}" not in ln and f"->[::1]:{port}" not in ln:
            continue          # only the client end of a connection TO the endpoint
        if (name, pid) not in seen:
            seen.add((name, pid))
            out.append((name, pid))
    return out


# ---------------------------------------------------------------- macmon
def parse_macmon_line(line):
    """-> (all_power_w, gpu_active_ratio) or None for a bad line."""
    try:
        d = json.loads(line)
        w = float(d["all_power"])
        g = d.get("gpu_active_ratio")
        return w, (float(g) if g is not None else None)
    except (ValueError, KeyError, TypeError):
        return None


# ---------------------------------------------------------------- earnings normalisation
ID_KEYS = ("id", "ledger_id", "entry_id", "job_id", "request_id")
TS_KEYS = ("created_at", "timestamp", "time", "created", "ts", "date", "at")
AMT_KEYS = ("amount_micro_usd", "micro_usd", "amount_usd", "amount", "earned_micro_usd", "payout_micro_usd", "total_micro_usd")
MODEL_KEYS = ("model", "type", "kind", "entry_type", "source")
LIST_KEYS = ("earnings", "entries", "ledger", "items", "data", "history", "results")


def extract_entries(payload):
    """Find the list of ledger-entry dicts in an API response (list, or dict holding a list)."""
    if isinstance(payload, list):
        return [e for e in payload if isinstance(e, dict)]
    if isinstance(payload, dict):
        for k in LIST_KEYS:
            if isinstance(payload.get(k), list):
                return [e for e in payload[k] if isinstance(e, dict)]
        for v in payload.values():
            if isinstance(v, list) and v and all(isinstance(e, dict) for e in v):
                return v
    return []


def entry_id(e):
    for k in ID_KEYS:
        v = e.get(k)
        if v not in (None, ""):
            return f"{k}:{v}" if k != "id" else str(v)
    return None


def entry_ts(e):
    for k in TS_KEYS:
        v = e.get(k)
        if v in (None, ""):
            continue
        try:
            if isinstance(v, (int, float)):
                return dt.datetime.fromtimestamp(v / 1000 if v > 1e11 else v, dt.timezone.utc)
            return parse_iso(v)
        except (ValueError, OverflowError, OSError):
            continue
    return None


def entry_usd(e):
    """Gross USD of one entry. Darkbloom amounts are int micro-USD (1 USD = 1,000,000)."""
    for k in AMT_KEYS:
        v = e.get(k)
        if v in (None, ""):
            continue
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        return f if k == "amount_usd" else f / 1e6
    return 0.0


def entry_kind(e):
    """'base' for the per-epoch base reward ledger rows (model == 'base_reward' or job_id floor:*),
    'sandbox' for sandbox entries, else 'job' (per-job inference income)."""
    jid = str(e.get("job_id", ""))
    model = str(e.get("model", ""))
    if model == "base_reward" or jid.startswith("floor:"):
        return "base"
    if model.startswith("sandbox:") or jid.startswith("sandbox:"):
        return "sandbox"
    return "job"


def archive_path(base, ts):
    return Path(base) / ARCHIVE_DIRNAME / f"earnings-{ts.strftime('%Y-%m')}.jsonl"


def load_archive_ids(base):
    ids = set()
    d = Path(base) / ARCHIVE_DIRNAME
    for f in sorted(d.glob("earnings-*.jsonl")) if d.exists() else []:
        for ln in f.read_text().splitlines():
            try:
                i = json.loads(ln).get("_id")
            except ValueError:
                continue          # torn/corrupt line: never prune, never crash
            if i:
                ids.add(i)
    return ids


def merge_into_archive(base, entries, fetched_at):
    """Append entries not yet archived (dedupe by id). Entries with no recognizable id are keyed by a
    stable content hash so they are still kept exactly once. Returns (new_count, no_id_count)."""
    import hashlib
    seen = load_archive_ids(base)
    new = noid = 0
    for e in entries:
        i = entry_id(e)
        if i is None:
            noid += 1
            i = "sha:" + hashlib.sha256(json.dumps(e, sort_keys=True).encode()).hexdigest()[:24]
        if i in seen:
            continue
        seen.add(i)
        ts = entry_ts(e) or fetched_at
        rec = dict(e)
        rec["_id"] = i
        rec["_fetched_at"] = fetched_at.strftime("%Y-%m-%dT%H:%M:%SZ")
        append_line(archive_path(base, ts), json.dumps(rec, sort_keys=True))
        new += 1
    return new, noid


def load_earnings(base, month):
    """All archived entries whose own timestamp falls in `month` (YYYY-MM), deduped by _id."""
    out, seen = [], set()
    d = Path(base) / ARCHIVE_DIRNAME
    for f in sorted(d.glob("earnings-*.jsonl")) if d.exists() else []:
        for ln in f.read_text().splitlines():
            try:
                e = json.loads(ln)
            except ValueError:
                continue
            if e.get("_id") in seen:
                continue
            seen.add(e.get("_id"))
            ts = entry_ts(e)
            if ts is not None and ts.strftime("%Y-%m") == month:
                out.append(e)
    return out


# ---------------------------------------------------------------- report maths
def _f(v):
    try:
        return float(v) if v not in ("", None) else None
    except (TypeError, ValueError):
        return None


def _i(v):
    f = _f(v)
    return int(f) if f is not None else None


def load_power_rows(base, month):
    p = Path(base) / POWER_DIRNAME / f"power-log-{month}.csv"
    rows = []
    if not p.exists():
        return rows
    with open(p, newline="") as fh:
        for r in csv.DictReader(fh):
            try:
                rows.append({
                    "ts": parse_iso(r["ts_utc"]),
                    "up": r.get("dbk_up", "") in ("1", "True", "true"),
                    "inf": _f(r.get("inference_active_frac")) or 0.0,
                    "req_d": _i(r.get("requests_delta")),
                    "tok_d": _i(r.get("tokens_delta")),
                    "interval_s": float(r["interval_s"] or 0),
                    "power_ok": r["power_ok"] in ("1", "True", "true"),
                    "avg_w": float(r["avg_w"]) if r["avg_w"] not in ("", None) else None,
                    "state": r["dbk_state"] or "off",
                    "other": r["other_work"] in ("1", "True", "true"),
                    "other_procs": r.get("other_procs", ""),
                })
            except (ValueError, KeyError, TypeError):
                continue          # a torn row is a data gap, not a crash
    return rows


def _kwh(rows, cal, off_w):
    return sum(max(0.0, cal * r["avg_w"] + off_w) * r["interval_s"] for r in rows) / 3.6e6


def compute_report(rows, rate, calibration=1.0, offset_w=0.0, baseline_w=None, month=None):
    """Three transparent methods over one month of power rows."""
    ok = [r for r in rows if r["power_ok"] and r["avg_w"] is not None and r["interval_s"] > 0]
    unavailable_s = sum(r["interval_s"] for r in rows if not (r["power_ok"] and r["avg_w"] is not None))
    res = {"rate": rate, "calibration": calibration, "offset_w": offset_w, "rows": len(rows),
           "power_rows": len(ok), "power_unavailable_s": unavailable_s}
    # (a) total
    res["a_total_kwh"] = _kwh(ok, calibration, offset_w)
    res["a_total_cost"] = res["a_total_kwh"] * rate
    res["covered_s"] = sum(r["interval_s"] for r in ok)
    # (b) by Darkbloom state
    b = {}
    for st in ("off", "idle", "serving"):
        sub = [r for r in ok if r["state"] == st]
        k = _kwh(sub, calibration, offset_w)
        k_other = _kwh([r for r in sub if r["other"]], calibration, offset_w)
        b[st] = {"seconds": sum(r["interval_s"] for r in sub), "kwh": k, "cost": k * rate,
                 "kwh_with_other_work": k_other}
    b["online"] = {k: b["idle"][k] + b["serving"][k] for k in ("seconds", "kwh", "cost", "kwh_with_other_work")}
    res["b"] = b
    # (c) incremental over a baseline, own-LLM-work intervals excluded
    clean = [r for r in ok if not r["other"]]
    res["c_excluded_other_s"] = sum(r["interval_s"] for r in ok if r["other"] and r["state"] != "off")
    if baseline_w is not None:
        base, src = float(baseline_w), "configured --baseline-w"
    else:
        off = [calibration * r["avg_w"] + offset_w for r in clean if r["state"] == "off"]
        if len(off) >= 3:
            base, src = statistics.median(off), f"median of {len(off)} Darkbloom-OFF clean intervals"
        else:
            idle = sorted(calibration * r["avg_w"] + offset_w for r in clean if r["state"] == "idle")
            if len(idle) >= 3:
                base = idle[max(0, int(len(idle) * 0.10))]
                src = (f"ESTIMATE: 10th percentile of {len(idle)} online-idle clean intervals (no Darkbloom-off "
                       "data; model residency counts as baseline so incremental is UNDERSTATED)")
            else:
                base, src = 0.0, "NONE: no baseline data; set --baseline-w (incremental == total online clean kWh)"
    res["c_baseline_w"], res["c_baseline_src"] = base, src
    c = {}
    for st in ("idle", "serving"):
        sub = [r for r in clean if r["state"] == st]
        inc = sum((calibration * r["avg_w"] + offset_w - base) * r["interval_s"] for r in sub) / 3.6e6
        c[st] = {"seconds": sum(r["interval_s"] for r in sub), "kwh": inc, "cost": inc * rate}
    c["total"] = {"seconds": c["idle"]["seconds"] + c["serving"]["seconds"],
                  "kwh": c["idle"]["kwh"] + c["serving"]["kwh"],
                  "cost": c["idle"]["cost"] + c["serving"]["cost"]}
    res["c"] = c
    return res


def summarize_earnings(entries):
    by_day, tot = {}, {"base": 0.0, "job": 0.0, "sandbox": 0.0}
    for e in entries:
        ts, usd, kind = entry_ts(e), entry_usd(e), entry_kind(e)
        day = ts.strftime("%Y-%m-%d")
        d = by_day.setdefault(day, {"base": 0.0, "job": 0.0, "sandbox": 0.0, "n": 0})
        d[kind] += usd
        d["n"] += 1
        tot[kind] += usd
    return {"by_day": dict(sorted(by_day.items())), "base": tot["base"], "job": tot["job"],
            "sandbox": tot["sandbox"], "gross": tot["base"] + tot["job"] + tot["sandbox"], "n": len(entries)}


# ====================================================================== own-vs-paid attribution
# Which minutes of Darkbloom "serving" power are PAID network work and which are the operator's OWN work sent
# through Darkbloom's local endpoint (127.0.0.1:8000)? Evidence, strongest first:
#   paid  : daemon-state stats.requests_served / tokens_generated advance (per-minute requests_delta /
#           tokens_delta). Measured on real data: these counters did NOT move for 70+ local-endpoint calls
#           and DID move 1:1 with ledger rows (20 requests = 20 per-job ledger rows;
#           68,848 tokens = the ledger's completion tokens exactly), so they are network-side only.
#   own A : a job window from ollama-worker's dispatch-metrics.jsonl (host 127.0.0.1:8000: exact start/end,
#           completion tokens) or a done queue job in the Darkbloom lane (studio-db): start..log mtime.
#   own B : a non-Darkbloom process had an ESTABLISHED connection to :8000 during the minute
#           (sampler flag local-endpoint-client:*).
#   own C : only the process-name / >150% CPU heuristic (weak: shares the Mac but may not touch Darkbloom).
# inference_active is NOT used as paid evidence: it is also true while Darkbloom runs a LOCAL request.
EARN_TOL_S = 120.0        # an earnings row is matched to a counter-advance minute up to this long after it
SETTLE_S = 900.0          # a counter-advance minute with no ledger row is "unpaid" only after this long
ADJ_GAP_S = 150.0
CLASSES = ("off", "idle", "paid", "own", "both", "unattributed", "network_unpaid")


def worker_metrics_path():
    return Path(os.environ.get("BLOOM_WORKER_METRICS") or Path.home() / "bin" / "ollama-worker-logs" / "dispatch-metrics.jsonl")


def queue_state_path():
    return Path(os.environ.get("BLOOM_QUEUE_STATE") or Path.home() / "bin" / "ollama-queue-state.json")


def load_own_windows(month, metrics_path=None, queue_path=None):
    """Windows in which the operator's own jobs used Darkbloom's local endpoint. [{start,end,tokens,model,source}]
    (datetimes UTC; tokens = completion tokens or None). Missing/corrupt files give [] (never raises)."""
    out = []
    mp = Path(metrics_path) if metrics_path else worker_metrics_path()
    try:
        fh = open(mp)
    except OSError:
        fh = None
    if fh:
        with fh:
            for ln in fh:
                if month not in ln[:60]:          # "timestamp" is the first key of a metrics row
                    continue
                try:
                    d = json.loads(ln)
                    if f":{DBK_LOCAL_PORT}" not in str(d.get("host", "")):
                        continue
                    end = parse_iso(d["timestamp"])
                    wall = float(d.get("wall_time_s") or 0)
                    tok = d.get("sum_completion_tokens")
                    out.append({"start": end - dt.timedelta(seconds=wall), "end": end, "model": d.get("model"),
                                "tokens": int(float(tok)) if tok not in (None, "None", "") else None, "source": "metrics"})
                except (ValueError, KeyError, TypeError):
                    continue
    qp = Path(queue_path) if queue_path else queue_state_path()
    try:
        jobs = json.loads(qp.read_text()).get("jobs", [])
    except (OSError, ValueError, AttributeError):
        jobs = []
    for j in jobs:
        try:
            if j.get("status") != "done" or "studio-db" not in (j.get("lane"), j.get("host_pref")):
                continue
            lp = j.get("log_path") or j.get("live_log_path")
            st = parse_iso(j["launched_at"])
            en = dt.datetime.fromtimestamp(os.path.getmtime(lp), dt.timezone.utc)
            if en > st and st.strftime("%Y-%m") <= month <= en.strftime("%Y-%m"):
                out.append({"start": st, "end": en, "model": j.get("model"), "tokens": None, "source": "queue"})
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return sorted(out, key=lambda w: w["start"])


def paid_entries_from(entries):
    """Per-job (non-base) ledger rows as plain dicts for matching."""
    out = []
    for e in entries:
        if entry_kind(e) != "job":
            continue
        ts = entry_ts(e)
        if ts is None:
            continue
        out.append({"ts": ts, "ctok": int(e.get("completion_tokens") or 0), "ptok": int(e.get("prompt_tokens") or 0),
                    "usd": entry_usd(e), "model": e.get("model")})
    return sorted(out, key=lambda x: x["ts"])


def archive_settled_until(base):
    """Latest time the earnings archive was fetched (rows settled before it are in the archive)."""
    best = None
    d = Path(base) / ARCHIVE_DIRNAME
    for f in sorted(d.glob("earnings-*.jsonl")) if d.exists() else []:
        try:
            lines = f.read_text().splitlines()
        except OSError:
            continue
        for ln in lines[-50:]:
            try:
                t = parse_iso(json.loads(ln).get("_fetched_at"))
            except (ValueError, TypeError, AttributeError):
                continue
            if best is None or t > best:
                best = t
    return best


def _bounds(r):
    iv = r["interval_s"] if r["interval_s"] and r["interval_s"] > 0 else 1.0
    return r["ts"] - dt.timedelta(seconds=iv), r["ts"]


def _overlap(a0, a1, b0, b1):
    return max(0.0, (min(a1, b1) - max(a0, b0)).total_seconds())


def match_entries_to_minutes(rows, paid_entries, paid_idx, tol_s=EARN_TOL_S):
    """Assign each ledger row to exactly ONE counter-advance minute: the one whose interval contains the row's
    timestamp (measured: ledger stamps land within seconds of the counter advance), else the latest one that ended
    before it within tol_s. Returns {row_index: [entries]}, orphans list."""
    import bisect
    ends = [rows[i]["ts"].timestamp() for i in paid_idx]
    out, orphans = {}, []
    for e in paid_entries:
        t = e["ts"].timestamp()
        k = bisect.bisect_left(ends, t)            # first counter minute ending at/after t
        hit = None
        if k < len(paid_idx) and _bounds(rows[paid_idx[k]])[0].timestamp() <= t:
            hit = paid_idx[k]                      # contained
        elif k > 0 and t <= ends[k - 1] + tol_s:
            hit = paid_idx[k - 1]                  # settled shortly after the minute ended
        if hit is None:
            orphans.append(e)
        else:
            out.setdefault(hit, []).append(e)
    return out, orphans


def classify_minutes(rows, windows, paid_entries, settled_until=None, tol_s=EARN_TOL_S):
    """Per-minute paid / own / both / idle / off / unattributed / network_unpaid. Returns a list parallel to rows of
    dict(cls, paid_frac, tier, basis, own_tok, paid_tok, n_earn). paid_frac = share of the minute's energy that is
    paid network work (1.0 paid, 0.0 otherwise, token share for 'both')."""
    res = []
    P = [bool((r.get("req_d") or 0) > 0 or (r.get("tok_d") or 0) > 0) for r in rows]
    for i, r in enumerate(rows):
        st, en = _bounds(r)
        a = False
        own_tok = 0.0
        for w in windows:
            ov = _overlap(st, en, w["start"], w["end"])
            if ov <= 0:
                continue
            a = True
            if w.get("tokens") and w["source"] == "metrics":
                span = max(1.0, (w["end"] - w["start"]).total_seconds())
                own_tok += w["tokens"] * ov / span
        b = "local-endpoint-client" in (r.get("other_procs") or "")
        c = bool(r.get("other"))
        tier = "A" if a else "B" if b else "C" if c else "-"
        res.append({"cls": None, "paid_frac": 0.0, "tier": tier, "basis": "", "own_tok": own_tok,
                    "paid_tok": r.get("tok_d") or 0, "n_earn": 0})
    paid_idx = [i for i, p in enumerate(P) if p]
    matched, _orph = match_entries_to_minutes(rows, paid_entries, paid_idx, tol_s)
    for i, r in enumerate(rows):
        x = res[i]
        st, en = _bounds(r)
        strong_own = x["tier"] in ("A", "B")
        x["n_earn"] = len(matched.get(i, []))
        if not r.get("up", r["state"] != "off") or r["state"] == "off":
            x["cls"], x["basis"] = "off", "provider not running"
            continue
        active = (r.get("inf") or 0) > 0
        if P[i]:
            unpaid = (not x["n_earn"]) and settled_until is not None and en + dt.timedelta(seconds=SETTLE_S) <= settled_until
            if unpaid:
                x["cls"], x["paid_frac"], x["basis"] = "network_unpaid", 0.0, "network counters advanced but no ledger row after settle window"
            elif strong_own:
                tok = r.get("tok_d") or 0
                if tok > 0 and x["own_tok"] > 0:
                    x["cls"], x["paid_frac"] = "both", tok / (tok + x["own_tok"])
                    x["basis"] = "network counters + own job window; split by completion-token share"
                else:
                    x["cls"], x["paid_frac"] = "unattributed", 0.0
                    x["basis"] = "network counters AND own endpoint use, no token data to split"
            else:
                x["cls"], x["paid_frac"] = "paid", 1.0
                x["basis"] = "network counters advanced" + ("" if x["n_earn"] else " (ledger row not yet settled)")
                if x["tier"] == "C":
                    x["basis"] += "; weak own-process heuristic also present"
        elif strong_own:
            x["cls"], x["basis"] = "own", "own endpoint use (" + ("job window" if x["tier"] == "A" else "local connection") + ")"
        elif active:
            adj = False
            for j in (i - 1, i + 1):
                if 0 <= j < len(rows) and P[j] and res[j]["tier"] not in ("A", "B") \
                        and abs((rows[j]["ts"] - r["ts"]).total_seconds()) <= ADJ_GAP_S:
                    adj = True
            if adj:
                x["cls"], x["paid_frac"], x["basis"] = "paid", 1.0, "inference active, adjacent minute has network counters (long request)"
            else:
                x["cls"], x["basis"] = "unattributed", "inference active but no counters, no own evidence"
        elif x["tier"] == "C":
            x["cls"], x["basis"] = "own", "weak: own-process heuristic only"
        else:
            x["cls"], x["basis"] = "idle", "provider up, no work seen"
    return res


def attribution_report(rows, cls, rate, calibration=1.0, offset_w=0.0, baseline_w=0.0):
    """kWh per class and the four offset options. Option 1 = paid minutes with NO own-work signal at all, watts above
    baseline; 2 = paid (incl. weak-heuristic overlap + paid share of 'both') above baseline; 3 = paid gross watts;
    4 = 3 + online-idle (readiness)."""
    out = {"hours": {c: 0.0 for c in CLASSES}, "kwh": {c: 0.0 for c in CLASSES}, "minutes": {c: 0 for c in CLASSES}}
    o1 = o2 = o3 = 0.0
    for r, x in zip(rows, cls):
        if not (r["power_ok"] and r["avg_w"] is not None and r["interval_s"] > 0):
            continue
        w = max(0.0, calibration * r["avg_w"] + offset_w)
        k = w * r["interval_s"] / 3.6e6
        c = x["cls"]
        out["hours"][c] += r["interval_s"] / 3600
        out["kwh"][c] += k
        out["minutes"][c] += 1
        f = x["paid_frac"]
        if f > 0:
            inc = (w - baseline_w) * r["interval_s"] / 3.6e6 * f
            o2 += inc
            o3 += k * f
            if x["tier"] == "-":
                o1 += inc
    out["opt"] = {1: o1, 2: o2, 3: o3, 4: o3 + out["kwh"]["idle"]}
    out["opt_cost"] = {k: v * rate for k, v in out["opt"].items()}
    return out


def matching_qa(rows, cls, paid_entries, windows, tol_s=EARN_TOL_S):
    """How well do the signals agree? Everything here is measured on the rows given."""
    import statistics as st_
    P = [i for i, r in enumerate(rows) if (r.get("req_d") or 0) > 0 or (r.get("tok_d") or 0) > 0]
    matched, orph = match_entries_to_minutes(rows, paid_entries, P, tol_s)
    qa = {"minutes": len(rows), "counter_minutes": len(P), "counter_minutes_with_ledger": sum(1 for i in P if matched.get(i)),
          "ledger_rows_total": len(paid_entries)}
    if rows:
        lo = _bounds(rows[0])[0]
        hi = rows[-1]["ts"] + dt.timedelta(seconds=tol_s)
        cov = [e for e in paid_entries if lo <= e["ts"] <= hi]
    else:
        cov = []
    qa["ledger_rows_in_power_coverage"] = len(cov)
    qa["ledger_rows_matched"] = sum(len(v) for v in matched.values())
    qa["ledger_rows_orphan_in_coverage"] = sum(1 for e in orph if e in cov)
    tok_c = sum(rows[i].get("tok_d") or 0 for i in P if matched.get(i))
    tok_l = sum(e["ctok"] for i in P for e in matched.get(i, []))
    qa["tokens_counter_matched_minutes"], qa["tokens_ledger_matched_minutes"] = tok_c, tok_l
    lags = [(e["ts"] - rows[i]["ts"]).total_seconds() for i in P for e in matched.get(i, [])]
    qa["ledger_lag_median_s"] = st_.median(lags) if lags else None
    qa["ledger_lag_max_s"] = max(lags) if lags else None
    a_min = [i for i, x in enumerate(cls) if x["tier"] == "A"]
    qa["own_windows"] = len(windows)
    qa["minutes_with_own_window"] = len(a_min)
    qa["own_window_minutes_with_sampler_flag"] = sum(1 for i in a_min if rows[i].get("other"))
    qa["flag_only_minutes"] = sum(1 for x in cls if x["tier"] == "C")
    qa["active_own_only_minutes"] = sum(1 for r, x in zip(rows, cls) if (r.get("inf") or 0) > 0 and x["cls"] == "own")
    qa["unattributed_minutes"] = sum(1 for x in cls if x["cls"] == "unattributed")
    qa["network_unpaid_minutes"] = sum(1 for x in cls if x["cls"] == "network_unpaid")
    qa["both_minutes"] = sum(1 for x in cls if x["cls"] == "both")
    return qa
