#!/usr/bin/env python3
"""Darkbloom power + state sampler (stdlib only; user LaunchAgent, no sudo, no listener).

Every minute appends ONE row to ~/.darkbloom/power/power-log-YYYY-MM.csv (new file each month):
  system watts from `macmon pipe` (SMC whole-system sensor, no sudo; RAW, calibration is applied only
  by bloom-power-report.py), interval Wh, and the Darkbloom state needed to tie energy to "running":
    dbk_up                provider process alive AND daemon-state.json fresh
    dbk_state             off | idle (online, waiting) | serving
    inference_active_frac share of 5 s polls where daemon-state.json said inference_active=true
    requests_delta/tokens_delta   change of stats.requests_served / tokens_generated
    warm_models, load_transition_active, gpu_pct (macmon gpu_active_ratio)
    other_work/other_procs  the operator's own LLM work (ollama-worker, ollama runner, mlx, local-endpoint
                          clients of 127.0.0.1:8000, any non-Darkbloom process >150% CPU). Those
                          intervals are excluded from the incremental method. Darkbloom Sandbox
                          processes, and one busy VM per running sandbox job, are not other work.
    sandbox_jobs, gpu/sandbox/total_bytes_in/out   NOT in the power-log header: written to the sidecars
                          power/sandbox-jobs-YYYY-MM.csv and power/net-bytes-YYYY-MM.csv (L.bridge_row).
                          Bytes come from one long-running nettop (NettopReader) and netstat -ibn (NetProbe).
    L.USAGE_COLUMNS       NOT in the header either: power/usage-YYYY-MM.csv. Per-process CPU time and energy
                          (proc_pid_rusage, the operator's own processes, no root) and per-client GPU time (ioreg
                          AGXDeviceUserClient), snapshotted each row (UsageProbe) and split into Darkbloom /
                          Sandbox / own / system, plus macmon's whole-CPU and whole-GPU energy for the row.
READ-ONLY toward Darkbloom: reads daemon-state.json, the sandbox status.json, lsof/ps/nettop/netstat; never calls the
darkbloom CLI or writes provider.toml; ioreg and proc_pid_rusage only read counters. macmon missing/crashing never exits the loop: rows say power_ok=0
note='power unavailable'; nettop/netstat missing leave the byte columns "".

Usage: bloom-power-log.py            run forever (launchd KeepAlive)
       bloom-power-log.py --once [--seconds N]   sample N s (default 20), write one row, print it"""
import argparse
import ctypes
import os
import pty
import queue
import select
import shutil
import signal
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bloom_power_lib as L  # noqa: E402

POLL_S = 5.0
ROW_S = 60.0
MAX_DT = 5.0           # a gap between macmon samples longer than this is sleep/stall, not measured energy


def find_macmon():
    p = os.environ.get("BLOOM_MACMON")
    if p:
        return p if os.access(p, os.X_OK) else None
    return shutil.which("macmon") or ("/opt/homebrew/bin/macmon" if os.access("/opt/homebrew/bin/macmon", os.X_OK) else None)


class Window:
    """Accumulates one row's worth of observations. Pure: no IO."""

    def __init__(self, start_ts):
        self.start = start_ts
        self.samples = []            # (ts, watts, gpu)
        self.last_sample_ts = None
        self.energy_ws = 0.0         # watt-seconds, trapezoid-free: watts * capped dt
        self.covered_s = 0.0
        self.polls = 0
        self.active_polls = 0
        self.up_polls = 0
        self.other = set()
        self.warm = None
        self.load_transition = False
        self.counters_first = None
        self.counters_last = None
        self.extra = None            # last fresh daemon-state snapshot columns (L.DAEMON_COLUMNS)
        self.notes = set()
        self.sandbox_jobs = 0        # most Darkbloom Sandbox jobs running at any poll
        self.net = None              # [gpu_in, gpu_out, sandbox_in, sandbox_out]; None = no nettop block came
        self.net_covered_s = 0.0
        self.net_total = None        # [in, out] on the physical interfaces; None = not measured
        self.cpu_ws = 0.0            # macmon cpu_power / gpu_power integrated like energy_ws (joules)
        self.gpu_ws = 0.0
        self.parts_s = 0.0           # seconds those two cover (0 = macmon gave no cpu/gpu power)

    def add_power(self, ts, watts, gpu, parts=None):
        dt = 1.0 if self.last_sample_ts is None else min(max(ts - self.last_sample_ts, 0.0), MAX_DT)
        if self.last_sample_ts is not None and ts - self.last_sample_ts > MAX_DT * 2:
            self.notes.add("power gap (sleep/stall)")
        self.last_sample_ts = ts
        self.samples.append((ts, watts, gpu))
        self.energy_ws += watts * dt
        self.covered_s += dt
        if parts:                    # (cpu_w, gpu_w) from L.parse_macmon_parts
            self.cpu_ws += parts[0] * dt
            self.gpu_ws += parts[1] * dt
            self.parts_s += dt

    def add_poll(self, up, ds, other_names, sandbox=None):
        self.polls += 1
        if sandbox:                  # (jobs, note) from L.read_sandbox_jobs
            self.sandbox_jobs = max(self.sandbox_jobs, sandbox[0])
            if sandbox[1]:
                self.notes.add(sandbox[1])
        if up:
            self.up_polls += 1
            if ds.get("ok"):
                if ds.get("inference_active"):
                    self.active_polls += 1
                self.warm = ds.get("warm_models")
                self.load_transition = self.load_transition or ds.get("load_transition_active", False)
                c = (ds.get("requests"), ds.get("tokens"))
                self.counters_first = self.counters_first or c
                self.counters_last = c
                self.extra = ds.get("extra") or self.extra
            else:
                self.notes.add("daemon-state stale/missing")
        self.other.update(other_names)


    def add_net_block(self, dt_s, by_class):
        """One nettop delta block's bytes (L.net_block_bytes) covering dt_s seconds."""
        if self.net is None:
            self.net = [0, 0, 0, 0]
        for i, v in enumerate(by_class["gpu"] + by_class["sandbox"]):
            self.net[i] += int(v)
        self.net_covered_s += max(float(dt_s), 0.0)

    def add_net_total(self, b_in, b_out):
        """Bytes the physical interfaces moved since the previous netstat reading (L.iface_bytes_delta)."""
        if self.net_total is None:
            self.net_total = [0, 0]
        self.net_total[0] += int(b_in)
        self.net_total[1] += int(b_out)

    def row(self, end_ts, prev_counters):
        n = len(self.samples)
        up = self.up_polls * 2 >= max(self.polls, 1) and self.up_polls > 0
        frac = (self.active_polls / self.up_polls) if self.up_polls else 0.0
        c_last = self.counters_last
        rd = td = 0
        if c_last and prev_counters:
            rd = L.counter_delta(prev_counters[0], c_last[0])
            td = L.counter_delta(prev_counters[1], c_last[1])
        elif c_last and self.counters_first:       # no previous window yet: delta within this window
            rd = L.counter_delta(self.counters_first[0], c_last[0])
            td = L.counter_delta(self.counters_first[1], c_last[1])
        notes = set(self.notes)
        span = end_ts - self.start
        if self.net is not None and span >= 30 and self.net_covered_s < 0.75 * span:
            notes.add(f"net bytes partial ({self.net_covered_s:.0f}s of {span:.0f}s)")
        net = self.net or [""] * 4
        tot = self.net_total or [""] * 2
        if n:
            ws = [s[1] for s in self.samples]
            gs = [s[2] for s in self.samples if s[2] is not None]
            r_avg, r_max = sum(ws) / n, max(ws)
            gpu = round(100 * sum(gs) / len(gs), 1) if gs else ""
            wh = self.energy_ws / 3600.0
            power_ok = 1
        else:
            r_avg = r_max = wh = gpu = ""
            power_ok = 0
            notes.add("power unavailable")
        other = sorted(self.other)
        extra = {c: (self.extra or {}).get(c, "") for c in L.DAEMON_COLUMNS}
        return {
            **extra,
            "ts_utc": L.utc_iso(end_ts),
            "interval_s": round(self.covered_s, 1) if power_ok else round(end_ts - self.start, 1),
            "samples": n,
            "power_ok": power_ok,
            "avg_w": round(r_avg, 2) if power_ok else "",
            "max_w": round(r_max, 2) if power_ok else "",
            "wh": round(wh, 4) if power_ok else "",
            "dbk_up": int(up),
            "dbk_state": L.classify_state(up, frac, rd, td),
            "inference_active_frac": round(frac, 3),
            "requests_delta": rd,
            "tokens_delta": td,
            "warm_models": ";".join(self.warm or []),
            "load_transition_active": int(self.load_transition),
            "gpu_pct": gpu,
            "other_work": int(bool(other)),
            "other_procs": ";".join(other),
            "note": "; ".join(sorted(notes)),
            "sandbox_jobs": self.sandbox_jobs,
            "gpu_bytes_in": net[0],
            "gpu_bytes_out": net[1],
            "sandbox_bytes_in": net[2],
            "sandbox_bytes_out": net[3],
            "total_bytes_in": tot[0],
            "total_bytes_out": tot[1],
            "cpu_mj": int(round(self.cpu_ws * 1000)) if self.parts_s else "",
            "gpu_mj": int(round(self.gpu_ws * 1000)) if self.parts_s else "",
            "dbk_local": int(any(o.startswith("local-endpoint-client:") for o in other)),
        }


# ---------------------------------------------------------------- environment probes (all read-only)
def _run(cmd, timeout=5):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def dbk_process_up(ds_pid):
    """Provider process alive: pid from daemon-state.json (or provider.pid) and the pid exists."""
    pids = []
    if ds_pid:
        pids.append(int(ds_pid))
    try:
        pids.append(int((L.HOME_DIR / "provider.pid").read_text().strip()))
    except (OSError, ValueError):
        pass
    for pid in pids:
        try:
            os.kill(pid, 0)
            return True
        except PermissionError:
            return True
        except (OSError, ProcessLookupError):
            continue
    return False


_PS = {"cmds": {}}     # pid -> command line from the latest probe_other_work ps run (NetProbe classifies with it)


def probe_other_work(sandbox_vms=0):
    rows = []
    for ln in _run(["ps", "-axo", "pid=,pcpu=,command="]).splitlines():
        parts = ln.strip().split(None, 2)
        if len(parts) == 3:
            try:
                rows.append((int(parts[0]), float(parts[1]), parts[2]))
            except ValueError:
                pass
    mine = os.getpid()
    rows = [r for r in rows if r[0] != mine]
    if rows:
        _PS["cmds"] = {r[0]: r[2] for r in rows}
    clients = L.parse_lsof_clients(_run(["lsof", "-nP", f"-iTCP:{L.DBK_LOCAL_PORT}", "-sTCP:ESTABLISHED"]))
    return L.detect_other_work(rows, clients, sandbox_vms=sandbox_vms)


class MacmonReader:
    """Keeps `macmon pipe` running in a background thread; restarts it with backoff; never raises."""

    def __init__(self, binary):
        self.binary = binary
        self.q = queue.Queue()
        self.stop = threading.Event()
        self.proc = None
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        if self.binary:
            self.thread.start()

    def _run(self):
        backoff = 5
        while not self.stop.is_set():
            try:
                self.proc = subprocess.Popen([self.binary, "pipe", "-i", "1000"], stdout=subprocess.PIPE,
                                             stderr=subprocess.DEVNULL, text=True)
                for line in self.proc.stdout:
                    parsed = L.parse_macmon_line(line)
                    if parsed:
                        self.q.put((time.time(), parsed[0], parsed[1], L.parse_macmon_parts(line)))
                        backoff = 5
                self.proc.wait()
            except OSError:
                pass
            if self.stop.wait(backoff):
                break
            backoff = min(backoff * 2, 300)

    def drain(self):
        out = []
        while True:
            try:
                out.append(self.q.get_nowait())
            except queue.Empty:
                return out

    def close(self):
        self.stop.set()
        try:
            if self.proc and self.proc.poll() is None:
                self.proc.terminate()
        except OSError:
            pass


# Run in a fresh single-threaded interpreter (start_new_session made it a session leader): make the pty on stdout its
# controlling terminal, then become nettop. A failed ioctl still runs nettop, only without the hangup safeguard.
NETTOP_CTTY = ("import fcntl, os, sys, termios\n"
               "try:\n"
               "    fcntl.ioctl(1, getattr(termios, 'TIOCSCTTY', 0x20007461), 0)\n"
               "except OSError:\n"
               "    pass\n"
               "os.execv(sys.argv[1], sys.argv[1:])\n")


class NettopReader:
    """Keeps ONE `nettop` (L.NETTOP_CMD: delta mode, a block every 5 s) running in a background thread and queues
    its blocks as (ts, dt_s, rows). Never raises.

    - nettop block-buffers into a pipe (nothing arrived for 20 s+), so its stdout is a pseudo-terminal.
    - The first block after every (re)start holds each flow's total so far, not a delta: it is dropped.
    - A block ends at the next header, or after quiet_s with no output (nettop writes a block at once), so a block
      is queued about a second after nettop wrote it. dt_s is the time since the previous block's header.
    - nettop is restarted with backoff when it exits, and after max_age_s as a precaution against slow growth;
      the restart loses the block in progress (5-10 s of per-process bytes; the row notes "net bytes partial").
    - The pty is nettop's controlling terminal (NETTOP_CTTY, in a session of its own), so if the sampler dies, even
      by SIGKILL, the pty hangs up and nettop gets SIGHUP. Without that an orphaned nettop kept writing to the dead
      pty at 146% CPU (2026-11-03 test)."""

    def __init__(self, cmd=None, quiet_s=1.0, max_age_s=24 * 3600.0, backoff_s=5.0):
        self.cmd = list(cmd or L.NETTOP_CMD)
        self.quiet_s, self.max_age_s, self.backoff_s = quiet_s, max_age_s, backoff_s
        self.q = queue.Queue()
        self.stop = threading.Event()
        self.proc = None
        self.runs = 0
        self.thread = threading.Thread(target=self._run, daemon=True, name="nettop")

    def start(self):
        if not os.access(self.cmd[0], os.X_OK):
            return False
        self.thread.start()
        return True

    def _run(self):
        backoff = self.backoff_s
        while not self.stop.is_set():
            aged, got = self._run_once()
            if aged:
                continue                 # retired on purpose: start the next one at once
            if got:
                backoff = self.backoff_s
            if self.stop.wait(backoff):
                break
            backoff = min(backoff * 2, 300.0)

    def _run_once(self):
        """One nettop process until it exits or ages out -> (aged, got_a_delta_block)."""
        try:
            master, slave = pty.openpty()
        except OSError:
            return False, False
        try:
            self.proc = subprocess.Popen([sys.executable, "-I", "-c", NETTOP_CTTY] + self.cmd,
                                         stdin=subprocess.DEVNULL, stdout=slave, stderr=subprocess.DEVNULL,
                                         close_fds=True, start_new_session=True)
        except OSError:
            os.close(master)
            os.close(slave)
            return False, False
        os.close(slave)
        self.runs += 1
        started = time.time()
        buf = b""
        st = {"n": 0, "rows": None, "ts": None, "prev_ts": None, "got": False}
        aged = False
        try:
            while not self.stop.is_set():
                if time.time() - started > self.max_age_s:
                    aged = True
                    break
                try:
                    ready, _, _ = select.select([master], [], [], self.quiet_s)
                except (OSError, ValueError):
                    break
                if not ready:
                    self._finish(st)     # quiet: the block being read is complete
                    continue
                try:
                    chunk = os.read(master, 65536)
                except OSError:          # EIO: nettop exited, the pty closed
                    break
                if not chunk:
                    break
                buf += chunk
                *lines, buf = buf.split(b"\n")
                for raw in lines:
                    kind, val = L.parse_nettop_line(raw.decode("utf-8", "replace"))
                    if kind == "header":
                        self._finish(st)
                        st["rows"], st["ts"] = [], time.time()
                    elif kind == "row" and st["rows"] is not None:
                        st["rows"].append(val)
        finally:
            self._kill()
            try:
                os.close(master)
            except OSError:
                pass
        return aged, st["got"]

    def _finish(self, st):
        """Queue the block being read, unless it is the run's first (cumulative totals, not a delta)."""
        if st["rows"] is None:
            return
        if st["n"] > 0 and st["prev_ts"] is not None:
            self.q.put((st["ts"], st["ts"] - st["prev_ts"], st["rows"]))
            st["got"] = True
        st["n"] += 1
        st["prev_ts"], st["rows"] = st["ts"], None

    def _kill(self):
        p = self.proc
        try:
            if p and p.poll() is None:
                p.terminate()
                try:
                    p.wait(3)
                except subprocess.TimeoutExpired:
                    p.kill()
                    p.wait(3)
        except (OSError, subprocess.SubprocessError):
            pass

    def drain(self):
        out = []
        while True:
            try:
                out.append(self.q.get_nowait())
            except queue.Empty:
                return out

    def close(self):
        self.stop.set()
        self._kill()


class NetProbe:
    """Per poll (main thread): nettop blocks -> gpu/sandbox bytes, netstat -ibn -> the physical-interface total.

    Processes are classified with L.classify_net_proc against the latest ps run (_PS) and the provider pid from
    daemon-state.json. A pid once seen as the provider service stays gpu for gpu_memory_s, so the bytes of a
    provider's last block still count after it exits (the next ps no longer lists it)."""

    def __init__(self, reader, netstat=None, gpu_memory_s=600.0):
        self.reader = reader
        self.netstat = netstat or (lambda: L.parse_netstat_ib(_run(L.NETSTAT_CMD)))
        self.gpu_memory_s = gpu_memory_s
        self.gpu_pids = {}           # (pid, name) -> last time it was seen as the provider service
        self.prev_if = None
        self.prev_if_ts = None

    def classify(self, name, pid, provider_pid, cmds, now):
        key = (pid, name)
        cls = L.classify_net_proc(name, pid, cmds.get(pid), provider_pid)
        if cls == "gpu":
            self.gpu_pids[key] = now
        elif cls is None and key in self.gpu_pids:
            cls = "gpu"
        return cls

    def sample(self, win, now, provider_pid, cmds=None):
        cmds = _PS["cmds"] if cmds is None else cmds
        for _ts, dt_s, rows in self.reader.drain():
            by_class, notes = L.net_block_bytes(
                rows, dt_s, lambda name, pid: self.classify(name, pid, provider_pid, cmds, now))
            win.add_net_block(dt_s, by_class)
            win.notes.update(notes)
        for key, seen in list(self.gpu_pids.items()):
            if now - seen > self.gpu_memory_s:
                del self.gpu_pids[key]
        cur = self.netstat()
        if not cur:
            return                       # unreadable: the next good reading covers the gap
        if self.prev_if is not None:
            b_in, b_out, notes = L.iface_bytes_delta(self.prev_if, cur, now - self.prev_if_ts)
            win.add_net_total(b_in, b_out)
            win.notes.update(notes)
        self.prev_if, self.prev_if_ts = cur, now


SANDBOX_READ_WAIT_S = 2.0


def _incident(kind, **fields):
    """Best-effort entry in the shared infra incident log (infra_incidents.py beside this file). Never raises."""
    try:
        import infra_incidents
        infra_incidents.record(kind, "power-sampler", **fields)
    except Exception:  # noqa: BLE001 - logging must never cost a power row
        pass


class BoundedSandboxRead:
    """L.read_sandbox_jobs on a daemon thread, waited on for at most wait_s.

    2026-11-02: with the screen locked, macOS held the sampler's read of the sandbox status.json (on
    /Volumes/NVMe-Models) in the kernel for 33 minutes, and no power rows were written in that time. Now a read
    that does not answer counts 0 jobs with a note and the row is written anyway. While that read is still
    outstanding no second one starts (one stuck thread at most), and its late answer is dropped. The first
    unanswered read of an outage logs a path-blocked incident; the first answered read after it logs path-cleared."""

    def __init__(self, path, wait_s=SANDBOX_READ_WAIT_S, read=None, incident=None):
        self.path, self.wait_s = path, wait_s
        self.read = read or (L.read_sandbox_auto if path is None else L.read_sandbox_jobs)
        self.incident = incident or _incident
        self.pending = None
        self.blocked_since = None
        self.problem = False

    def __call__(self, now):
        if self.pending is not None:
            if self.pending.is_alive():
                return self._blocked(now)
            self.pending = None          # the stuck read returned at last; its answer is stale, read again
        box = {}

        def run():
            try:
                box["v"] = self.read(now) if self.path is None else self.read(self.path, now)
            except Exception:  # noqa: BLE001 - read_sandbox_jobs never raises; a stand-in might
                box["v"] = (0, "")
        t = threading.Thread(target=run, daemon=True, name="sandbox-status-read")
        t.start()
        t.join(self.wait_s)
        if t.is_alive():
            self.pending = t
            return self._blocked(now)
        if self.blocked_since is not None:
            self.incident("path-cleared", path=str(self.path), blocked_for_s=round(now - self.blocked_since))
            self.blocked_since = None
        v = box.get("v", (0, ""))
        bad = bool(v[1]) and v[1].startswith(L.SANDBOX_PROBLEM_NOTE)
        if bad != self.problem:          # once per condition per process
            self.problem = bad
            if bad:
                print(f"bloom-power-log: WARNING {v[1]}", file=sys.stderr, flush=True)
                self.incident("status-problem", detail=v[1])
            else:
                self.incident("status-ok")
        return v

    def _blocked(self, now):
        if self.blocked_since is None:
            self.blocked_since = now
            self.incident("path-blocked", path=str(self.path), wait_s=self.wait_s)
        return 0, f"sandbox status unreadable (no answer in {self.wait_s:g}s)"


_SANDBOX_READ = []


IOREG_GPU_CMD = ["/usr/sbin/ioreg", "-a", "-r", "-d", "1", "-w", "0", "-c", "AGXDeviceUserClient"]
RUSAGE_INFO_V6 = 6       # <sys/resource.h>: after ri_uuid[16], u64 fields; [0] user, [1] system time (mach ticks),
RI_START, RI_ENERGY_NJ, RI_FIELDS = 8, 40, 42   # [8] proc_start_abstime, [40] energy_nj


class _Timebase(ctypes.Structure):
    _fields_ = [("numer", ctypes.c_uint32), ("denom", ctypes.c_uint32)]


class UsageProbe:
    """Snapshots per-process CPU time + energy (proc_pid_rusage, RUSAGE_INFO_V6: the operator's own processes, no root)
    and per-client GPU time (ioreg AGXDeviceUserClient) once per row; L.usage_deltas turns two snapshots into the row's
    USAGE_DELTA_COLUMNS. Every counter is cumulative, so nothing between two snapshots is missed except the last part of
    a process that exited. A part that cannot be read is None in the snapshot ("" in the row). Never raises."""

    def __init__(self, run=None, ioreg=None):
        self.run = run or _run
        self.ioreg = ioreg or (lambda: subprocess.run(IOREG_GPU_CMD, capture_output=True, timeout=5).stdout)
        self.prev = None
        self.lib = None
        try:
            lib = ctypes.CDLL("/usr/lib/libSystem.dylib")
            tb = _Timebase()
            lib.mach_timebase_info(ctypes.byref(tb))
            lib.mach_absolute_time.restype = ctypes.c_uint64
            lib.proc_pid_rusage.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_void_p]
            self.tick_ns = tb.numer / tb.denom
            self.buf = ctypes.create_string_buffer(1024)
            self.lib = lib
        except (OSError, AttributeError):
            pass

    def rusage(self, pid):
        """(start_ticks, cpu_ns, energy_nj) of one process, or None when it cannot be read."""
        if self.lib is None or self.lib.proc_pid_rusage(pid, RUSAGE_INFO_V6, self.buf) != 0:
            return None
        v = struct.unpack_from("<%dQ" % RI_FIELDS, self.buf.raw, 16)
        return v[RI_START], int((v[0] + v[1]) * self.tick_ns), v[RI_ENERGY_NJ]

    def snapshot(self):
        procs, me_pid = {}, os.getpid()
        meters = {me_pid}
        for ln in self.run(["ps", "-axo", "pid=,ppid=,uid=,command="]).splitlines():
            parts = ln.strip().split(None, 3)
            try:
                procs[int(parts[0])] = (int(parts[2]), parts[3] if len(parts) == 4 else "")
                if int(parts[1]) == me_pid:
                    meters.add(int(parts[0]))
            except (IndexError, ValueError):
                pass
        snap = {"t": time.monotonic(), "abs": self.lib.mach_absolute_time() if self.lib else 0, "procs": procs,
                "cpu": None, "gpu": None, "meters": meters}
        if self.lib is not None and procs:
            me, cpu = os.getuid(), {}
            for pid, (uid, _cmd) in procs.items():
                r = self.rusage(pid) if uid == me else None
                if r:
                    cpu[(pid, r[0])] = (r[1], r[2])
            snap["cpu"] = cpu
        try:
            out = self.ioreg()
            snap["gpu"] = L.parse_gpu_clients(out) if out else None
        except (OSError, subprocess.SubprocessError):
            pass
        return snap

    def prime(self):
        """Take the first snapshot (the start of the first row)."""
        try:
            self.prev = self.snapshot()
        except Exception:  # noqa: BLE001 - a probe failure must never kill the sampler
            self.prev = None

    def close_row(self, sandbox_jobs):
        """The ending row's USAGE_DELTA_COLUMNS ("" when not measured); its end snapshot starts the next row."""
        out = {c: "" for c in L.USAGE_DELTA_COLUMNS}
        try:
            cur = self.snapshot()
        except Exception:  # noqa: BLE001
            cur = None
        try:
            d = L.usage_deltas(self.prev, cur, sandbox_jobs)
        except Exception:  # noqa: BLE001
            d = None
        self.prev = cur
        if d:
            out.update(d)
        return out


def sample_once(win, reader, sandbox_read=None, net=None):
    now = time.time()
    for ts, w, g, *parts in reader.drain():
        win.add_power(ts, w, g, parts[0] if parts else None)
    ds = L.read_daemon_state(L.HOME_DIR / "daemon-state.json", now)
    up = dbk_process_up(ds.get("pid"))
    if sandbox_read is None:
        if not _SANDBOX_READ:
            _SANDBOX_READ.append(BoundedSandboxRead(None))
        sandbox_read = _SANDBOX_READ[0]
    sandbox = sandbox_read(now)
    try:
        others = probe_other_work(sandbox[0])
    except Exception as e:  # noqa: BLE001 - a probe failure must never kill the sampler
        others = []
        win.notes.add(f"other-work probe failed: {type(e).__name__}")
    win.add_poll(up, ds, others, sandbox)
    if net is not None:              # after probe_other_work: its ps run is what NetProbe classifies with
        try:
            net.sample(win, now, ds.get("pid"))
        except Exception as e:  # noqa: BLE001 - a byte count must never cost a power row
            win.notes.add(f"net probe failed: {type(e).__name__}")


def write_row(row):
    path = L.power_log_path(L.HOME_DIR, row["ts_utc"])
    L.append_csv_row(path, L.POWER_COLUMNS, row)
    try:
        L.bridge_row(L.HOME_DIR, row)      # sandbox-jobs / net-bytes / usage sidecars (the power-log header never carries them)
    except OSError as e:
        print(f"bloom-power-log: sidecar write failed: {e}", file=sys.stderr, flush=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--seconds", type=float, default=20.0)
    ap.add_argument("--no-write", action="store_true", help="with --once: print the row, do not append")
    a = ap.parse_args(argv)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    binary = find_macmon()
    if not binary:
        print("bloom-power-log: macmon not found (brew install macmon); logging 'power unavailable' rows",
              file=sys.stderr, flush=True)
    reader = MacmonReader(binary)
    reader.start()
    nettop = NettopReader()
    if not nettop.start():
        print("bloom-power-log: nettop not found; gpu/sandbox byte columns stay empty", file=sys.stderr, flush=True)
    net = NetProbe(nettop)
    usage = UsageProbe()
    usage.prime()
    prev = None
    try:
        if a.once:
            win = Window(time.time())
            end = time.time() + a.seconds
            while time.time() < end:
                sample_once(win, reader, net=net)
                time.sleep(min(POLL_S, max(0.1, end - time.time())))
            sample_once(win, reader, net=net)
            row = win.row(time.time(), prev)
            row.update(usage.close_row(win.sandbox_jobs))
            if not a.no_write:
                write_row(row)
            print(row)
            return 0
        win = Window(time.time())
        next_flush = (int(time.time() // ROW_S) + 1) * ROW_S
        while True:
            time.sleep(POLL_S)
            sample_once(win, reader, net=net)
            now = time.time()
            if now >= next_flush:
                row = win.row(now, prev)
                row.update(usage.close_row(win.sandbox_jobs))
                try:
                    write_row(row)
                except OSError as e:
                    print(f"bloom-power-log: write failed: {e}", file=sys.stderr, flush=True)
                prev = win.counters_last or prev
                win = Window(now)
                next_flush = (int(now // ROW_S) + 1) * ROW_S
    finally:
        reader.close()
        nettop.close()


if __name__ == "__main__":
    sys.exit(main())
