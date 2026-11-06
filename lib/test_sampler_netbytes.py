"""bloom-power-log.py: network byte columns (2026-11-03, for bloom-ledger's bandwidth lines).

gpu_bytes_in/out, sandbox_bytes_in/out, total_bytes_in/out are NOT in the main power-log header here; they always go
to power/net-bytes-YYYY-MM.csv (and sandbox_jobs to power/sandbox-jobs-YYYY-MM.csv). Per-process bytes come from one
long-running nettop in delta mode (a fake nettop script here), the total from netstat -ibn (text fixtures here).
A counter reset, a restarted process or a glitch never yields a negative or a spike. Temp files and fake commands
only: never runs the real nettop, never probes Darkbloom.
"""
import csv
import importlib.util
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
CLIENT = HERE.parent / "client"
sys.path.insert(0, str(HERE))        # client/bloom-power-log.py imports bloom_power_lib (installed beside it)
NOW = 1793680600.0


def load(name, file, base=HERE):
    sp = importlib.util.spec_from_file_location(name, base / file)
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


L = load("bloom_power_lib_nb", "bloom_power_lib.py")
S = load("bloom_power_log_nb", "bloom-power-log.py", CLIENT)

PROVIDER = "/Users/penn/.darkbloom/Darkbloom.app/Contents/MacOS/darkbloom start --foreground --model m"
WATCHDOG = "/Users/penn/.darkbloom/Darkbloom.app/Contents/MacOS/darkbloom watchdog --config /x/provider.toml"
CLI = "/Users/penn/.darkbloom/bin/darkbloom status"


# ---------------------------------------------------------------- columns and bridges
MAIN_HEADER = ["ts_utc", "interval_s", "samples", "power_ok", "avg_w", "max_w", "wh", "dbk_up", "dbk_state",
               "inference_active_frac", "requests_delta", "tokens_delta", "warm_models", "load_transition_active",
               "gpu_pct", "other_work", "other_procs", "note", "machine_id", "daemon_started_at",
               "coordinator_connected", "coordinator_since", "requests_served", "tokens_generated",
               "prompt_tokens_processed", "cached_input_tokens", "reasoning_tokens", "usage_gaps",
               "cancellations_partial_complete", "resident_seconds"]
SIDE_HEADER = "ts_utc,gpu_bytes_in,gpu_bytes_out,sandbox_bytes_in,sandbox_bytes_out,total_bytes_in,total_bytes_out"


def test_the_main_power_log_header_is_unchanged_and_the_sidecar_headers_are_exact():
    want = ["gpu_bytes_in", "gpu_bytes_out", "sandbox_bytes_in", "sandbox_bytes_out", "total_bytes_in",
            "total_bytes_out"]
    assert L.POWER_COLUMNS == MAIN_HEADER
    assert L.NET_COLUMNS == want and L.NET_BRIDGE_COLUMNS == ["ts_utc"] + want
    assert ",".join(L.NET_BRIDGE_COLUMNS) == SIDE_HEADER
    assert L.SANDBOX_BRIDGE_COLUMNS == ["ts_utc", "sandbox_jobs"]
    assert L.NET_BRIDGE == "net-bytes-{month}.csv" and L.SANDBOX_BRIDGE == "sandbox-jobs-{month}.csv"
    assert L.DAEMON_COLUMNS[0] == "machine_id" and L.DAEMON_COLUMNS[-1] == "resident_seconds"


def prow(ts, **kw):
    r = {c: "" for c in L.POWER_COLUMNS}
    r.update({"ts_utc": ts, "interval_s": 60, "power_ok": 1, "avg_w": 9, "wh": 0.15, "dbk_state": "idle",
              "sandbox_jobs": 0, "gpu_bytes_in": 10, "gpu_bytes_out": 20, "sandbox_bytes_in": 30,
              "sandbox_bytes_out": 40, "total_bytes_in": 500, "total_bytes_out": 600})
    r.update(kw)
    return r


def test_bridge_row_writes_both_sidecars_and_leaves_the_main_file_alone(tmp_path):
    f = L.power_log_path(tmp_path, "2026-11-03T07:00:00Z")
    L.append_csv_row(f, L.POWER_COLUMNS, prow("2026-11-03T07:00:00Z"))
    before = f.read_bytes()
    got = L.bridge_row(tmp_path, prow("2026-11-03T07:00:00Z", sandbox_jobs=2))
    assert got == [tmp_path / "power" / "sandbox-jobs-2026-11.csv", tmp_path / "power" / "net-bytes-2026-11.csv",
                   tmp_path / "power" / "usage-2026-11.csv"]
    assert f.read_bytes() == before and f.read_text().splitlines()[0] == ",".join(MAIN_HEADER)
    assert all(len(r) == 30 for r in csv.reader(f.read_text().splitlines()))
    net = (tmp_path / "power" / "net-bytes-2026-11.csv").read_text().splitlines()
    assert net == [SIDE_HEADER, "2026-11-03T07:00:00Z,10,20,30,40,500,600"]
    sb = (tmp_path / "power" / "sandbox-jobs-2026-11.csv").read_text().splitlines()
    assert sb == ["ts_utc,sandbox_jobs", "2026-11-03T07:00:00Z,2"]
    L.bridge_row(tmp_path, prow("2026-11-03T07:01:00Z"))
    assert len((tmp_path / "power" / "net-bytes-2026-11.csv").read_text().splitlines()) == 3


def test_write_row_bridges_the_bytes_through_the_sampler(tmp_path, monkeypatch):
    monkeypatch.setattr(S.L, "HOME_DIR", tmp_path)
    S.write_row(prow("2026-11-03T06:00:00Z", gpu_bytes_in=7))
    assert (tmp_path / "power" / "net-bytes-2026-11.csv").read_text().splitlines() == [
        SIDE_HEADER, "2026-11-03T06:00:00Z,7,20,30,40,500,600"]
    assert (tmp_path / "power" / "power-log-2026-11.csv").read_text().splitlines()[0] == ",".join(MAIN_HEADER)


def test_a_sidecar_write_failure_never_kills_the_sampler(tmp_path, monkeypatch):
    monkeypatch.setattr(S.L, "HOME_DIR", tmp_path)
    monkeypatch.setattr(S.L, "bridge_row", lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))
    S.write_row(prow("2026-11-03T06:00:00Z"))
    assert (tmp_path / "power" / "power-log-2026-11.csv").exists()


def test_ingest_reads_the_same_net_columns_and_route():
    sys.path.insert(0, str(HERE.parent / "ingest"))
    A = importlib.import_module("bloom_accounting_index")
    assert list(A.NET_COLUMNS) == L.NET_COLUMNS
    assert A.route("power/net-bytes-2026-11.csv") == "net"
    assert A.route("power/sandbox-jobs-2026-11.csv") == "sandbox"


# ---------------------------------------------------------------- parsing
@pytest.mark.parametrize("line, want", [
    (",bytes_in,bytes_out,", ("header", None)),
    (",bytes_in,bytes_out,\r", ("header", None)),
    ("darkbloom.98299,1069098,1234,", ("row", ("darkbloom", 98299, 1069098, 1234))),
    ("darkbloom-sandb.16219,5,6,\r", ("row", ("darkbloom-sandb", 16219, 5, 6))),
    ("Slack Helper.1023,56,54,", ("row", ("Slack Helper", 1023, 56, 54))),
    ("2.1.316.2427,0,0,", ("row", ("2.1.316", 2427, 0, 0))),
    ("odd,name.77,1,2,", ("row", ("odd,name", 77, 1, 2))),
    ("noTrailing.5,1,2", ("row", ("noTrailing", 5, 1, 2))),
    ("neg.5,-40,3,", ("row", ("neg", 5, 0, 3))),
    ("", (None, None)),
    ("garbage", (None, None)),
    ("nopid,1,2,", (None, None)),
    ("x.12a,1,2,", (None, None)),
    ("x.12,one,2,", (None, None)),
])
def test_nettop_lines(line, want):
    assert L.parse_nettop_line(line) == want


NETSTAT = """\
Name       Mtu   Network       Address            Ipkts Ierrs     Ibytes    Opkts Oerrs     Obytes  Coll
lo0        16384 <Link#1>                      20162480     0 15200034754 20162480     0 15200034754     0
lo0        16384 127           localhost       20162480     -  15200034754 20162480     -  15200034754     -
gif0*      1280  <Link#2>                             0     0          0        0     0          0     0
anpi1      1500  <Link#4>    86:3b:d6:6b:45:3e        0     0          0        0     0          0     0
en2        1500  <Link#12>   36:2b:2a:1d:4a:80        0     0          0        0     0          0     0
en3        1500  <Link#13>                             7     0       4096        8     0       2048     0
en0        1500  <Link#20>   1c:1d:d3:e5:8b:c6 327910759     0 338962685325 149992925     0 380578320634     0
en0        1500  fe80::1%en0 fe80:5::1         327910759     - 338962685325 149992925     - 380578320634     -
bridge0    1500  <Link#21>   36:2b:2a:1d:4a:80        5     0       9999        5     0       9999     0
utun0      1380  <Link#22>                       100     0   184000000      100     0   99000000     0
en1        1500  <Link#17>   1c:1d:d3:ef:f3:03 15229059     0 3035664861   425238     0  123361707     0
awdl0      1500  <Link#18>   fe:61:58:50:21:b2      789     0     212410      582     0     139750     0
en9*       1500  <Link#11>   86:3b:d6:6b:45:20        0     0          0        0     0          0     0
"""


def test_netstat_is_numeric():
    assert L.NETSTAT_CMD == ["/usr/sbin/netstat", "-ibn"], "without -n, name lookups took 6.7 s (probe timeout 5 s)"


def test_netstat_reads_only_the_physical_interfaces_link_rows():
    assert L.parse_netstat_ib(NETSTAT) == {"en0": (338962685325, 380578320634), "en1": (3035664861, 123361707),
                                           "en2": (0, 0), "en3": (4096, 2048), "en9": (0, 0)}
    assert L.parse_netstat_ib("") == {} and L.parse_netstat_ib(None) == {}


def test_interface_deltas_never_go_negative_or_spike():
    prev = {"en0": (1000, 2000), "en1": (50, 60), "en5": (10, 10)}
    cur = {"en0": (1500, 2600), "en1": (40, 70), "en7": (9999, 9999), "en5": (10, 10 + int(L.NET_MAX_BPS * 6))}
    assert L.iface_bytes_delta(prev, cur, 5.0) == (500, 600, ["net spike dropped (total: en5)"])
    assert L.iface_bytes_delta(None, cur, 5.0) == (0, 0, [])          # no baseline yet
    assert L.iface_bytes_delta(prev, {}, 5.0) == (0, 0, [])
    big = {"en0": (1000 + int(L.NET_MAX_BPS * 100), 2000)}             # a long sleep is a long interval, not a spike
    assert L.iface_bytes_delta(prev, big, 120.0)[0] == int(L.NET_MAX_BPS * 100)


# ---------------------------------------------------------------- classification
@pytest.mark.parametrize("name, pid, cmd, provider, want", [
    ("darkbloom", 98299, PROVIDER, 98299, "gpu"),
    ("darkbloom", 98299, None, 98299, "gpu"),               # exited, but daemon-state names it
    ("darkbloom", 93990, WATCHDOG, 98299, "gpu"),
    ("darkbloom", 5000, CLI, 98299, None),                  # the queue's status poll is not the provider
    ("darkbloom", 5001, None, 98299, None),                 # a CLI call that exited before ps saw it
    ("darkbloom", 5002, PROVIDER, None, "gpu"),             # no daemon-state: the command line decides
    ("darkbloom", 5003, PROVIDER, "junk", "gpu"),
    ("darkbloom-sandb", 16219, None, 98299, "sandbox"),
    ("sandbox-macos-w", 27308, None, None, "sandbox"),
    ("sandbox-linux-w", 27309, None, None, "sandbox"),
    ("DarkbloomSandbo", 16217, None, None, "sandbox"),
    ("com.apple.Virtu", 28016, None, None, "sandbox"),
    ("CloudflareWARP", 607, None, 98299, None),
    ("kernel_task", 0, None, 98299, None),
    ("BloomDashboardB", 59461, None, 98299, None),
    ("python3", 1, "python3 x.py darkbloom start", 98299, None),   # only a darkbloom process can be the provider
])
def test_classify(name, pid, cmd, provider, want):
    assert L.classify_net_proc(name, pid, cmd, provider) == want


def test_a_block_sums_by_class_and_drops_a_glitch():
    rows = [("darkbloom", 1, 100, 10), ("darkbloom", 2, 7, 7), ("darkbloom-sandb", 3, 50, 5),
            ("sandbox-macos-w", 4, 1000, 2000), ("firefox", 5, 99999, 99999),
            ("sandbox-macos-w", 6, int(L.NET_MAX_BPS * 5) + 1, 0)]
    cls = {1: "gpu", 2: None, 3: "sandbox", 4: "sandbox", 5: None, 6: "sandbox"}
    by, notes = L.net_block_bytes(rows, 5.0, lambda n, p: cls[p])
    assert by == {"gpu": [100, 10], "sandbox": [1050, 2005]}
    assert notes == ["net spike dropped (sandbox: sandbox-macos-w.6)"]


# ---------------------------------------------------------------- the sampler side
class FakeReader:
    def __init__(self, blocks):
        self.blocks = list(blocks)

    def drain(self):
        out, self.blocks = self.blocks, []
        return out


def test_netprobe_counts_provider_and_sandbox_not_the_cli_and_remembers_an_exited_provider():
    reads = [{"en0": (100, 100)}, {"en0": (400, 900)}, {}, {"en0": (100, 1000)}, {"en0": (150, 1100)}]
    blocks = [(NOW, 5.0, [("darkbloom", 98299, 1000, 100), ("darkbloom", 93990, 10, 1), ("darkbloom", 5000, 12000, 800),
                          ("sandbox-macos-w", 27308, 300, 3000), ("firefox", 9, 5, 5)])]
    rd = FakeReader(blocks)
    probe = S.NetProbe(rd, netstat=lambda: reads.pop(0))
    cmds = {98299: PROVIDER, 93990: WATCHDOG, 5000: CLI}
    w = S.Window(NOW - 60)
    probe.sample(w, NOW - 55, 98299, cmds)          # first netstat reading: a baseline only
    assert w.net == [1010, 101, 300, 3000] and w.net_total is None
    probe.sample(w, NOW - 50, 98299, cmds)
    assert w.net_total == [300, 800]
    probe.sample(w, NOW - 45, 98299, cmds)          # netstat unreadable: nothing counted, baseline kept
    assert w.net_total == [300, 800]
    probe.sample(w, NOW - 40, 98299, cmds)          # en0 counter went down (reset): 0, never negative
    assert w.net_total == [300, 800]
    # the provider restarted: the old pid's last block arrives after ps stopped listing it and daemon-state moved on
    rd.blocks = [(NOW - 35, 5.0, [("darkbloom", 98299, 70, 7), ("darkbloom", 99000, 5, 5)])]
    probe.sample(w, NOW - 35, 99000, {99000: PROVIDER})
    assert w.net == [1010 + 75, 101 + 12, 300, 3000] and w.net_total == [350, 900]
    r = w.row(NOW, None)
    assert [r[c] for c in L.NET_COLUMNS] == [1085, 113, 300, 3000, 350, 900]


def test_the_gpu_memory_of_an_exited_pid_expires():
    probe = S.NetProbe(FakeReader([]), netstat=lambda: {}, gpu_memory_s=600)
    assert probe.classify("darkbloom", 7, 7, {}, NOW) == "gpu"
    probe.sample(S.Window(NOW), NOW + 601, None, {})
    assert probe.classify("darkbloom", 7, None, {}, NOW + 602) is None


def test_a_row_with_nothing_measured_leaves_the_byte_columns_empty_and_partial_cover_is_noted():
    r = S.Window(NOW - 60).row(NOW, None)
    assert [r[c] for c in L.NET_COLUMNS] == [""] * 6 and "net bytes" not in r["note"]
    w = S.Window(NOW - 60)
    w.add_net_block(20.0, {"gpu": [1, 2], "sandbox": [0, 0]})
    w.add_net_total(0, 0)
    r = w.row(NOW, None)
    assert [r[c] for c in L.NET_COLUMNS] == [1, 2, 0, 0, 0, 0] and "net bytes partial (20s of 60s)" in r["note"]
    assert set(L.POWER_COLUMNS) <= set(r) and set(L.NET_COLUMNS) <= set(r)
    w = S.Window(NOW - 60)
    for _ in range(12):
        w.add_net_block(5.0, {"gpu": [0, 0], "sandbox": [0, 0]})
    assert "net bytes" not in w.row(NOW, None)["note"]


def test_sample_once_feeds_the_net_probe_after_the_ps_run(monkeypatch):
    monkeypatch.setattr(S.L, "read_daemon_state", lambda p, now: {"ok": False, "pid": 98299})
    monkeypatch.setattr(S, "dbk_process_up", lambda pid: True)
    order = []
    monkeypatch.setattr(S, "probe_other_work", lambda n: order.append("ps") or [])

    class Net:
        def sample(self, win, now, provider_pid):
            order.append(("net", provider_pid))

    class Boom:
        def sample(self, win, now, provider_pid):
            raise RuntimeError("x")
    w = S.Window(NOW)
    S.sample_once(w, FakeReader([]), sandbox_read=lambda now: (0, ""), net=Net())
    assert order == ["ps", ("net", 98299)]
    S.sample_once(w, FakeReader([]), sandbox_read=lambda now: (0, ""), net=Boom())
    assert "net probe failed: RuntimeError" in w.notes
    S.sample_once(w, FakeReader([]), sandbox_read=lambda now: (0, ""))      # no probe: nothing runs
    assert w.net is None


# ---------------------------------------------------------------- NettopReader against a fake nettop
FAKE = r'''#!/usr/bin/env python3
import os, sys, time
mode = os.environ.get("FAKE_MODE", "steady")
blocks = int(os.environ.get("FAKE_BLOCKS", "4"))
for i in range(blocks):
    sys.stdout.write(",bytes_in,bytes_out,\n")
    base = 10**9 if i == 0 else 0          # block 0: cumulative totals, never a delta
    sys.stdout.write("darkbloom.98299,%d,%d,\n" % (base + 100 + i, base + 10 + i))
    sys.stdout.write("sandbox-macos-w.27308,%d,7,\n" % (base + 5))
    sys.stdout.flush()
    time.sleep(0.4)
if mode == "hang":
    time.sleep(60)
'''


def fake_nettop(tmp_path):
    p = tmp_path / "nettop"
    p.write_text(FAKE.replace("#!/usr/bin/env python3", "#!" + sys.executable))
    p.chmod(0o755)
    return str(p)


def wait_blocks(rd, n, timeout=15.0):
    got, end = [], time.time() + timeout
    while time.time() < end and len(got) < n:
        got += rd.drain()
        time.sleep(0.05)
    return got


def test_reader_drops_each_runs_first_block_and_restarts(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_BLOCKS", "3")
    rd = S.NettopReader(cmd=[fake_nettop(tmp_path)], quiet_s=0.15, backoff_s=0.2)
    assert rd.start()
    try:
        got = wait_blocks(rd, 4)        # two delta blocks per run (3 blocks, the first dropped), two runs
    finally:
        rd.close()
    assert len(got) >= 4 and rd.runs >= 2
    for ts, dt_s, rows in got:
        assert 0.2 < dt_s < 2.0
        assert all(b_in < 10**9 for _, _, b_in, _ in rows), "a run's first (cumulative) block leaked"
    assert [r[0][2] for _, _, r in got[:4]] == [101, 102, 101, 102]


def test_reader_retires_an_old_nettop_and_starts_a_new_one(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_BLOCKS", "50")
    rd = S.NettopReader(cmd=[fake_nettop(tmp_path)], quiet_s=0.15, max_age_s=1.5, backoff_s=30)
    assert rd.start()
    try:
        end = time.time() + 12
        while time.time() < end and rd.runs < 2:
            time.sleep(0.1)
        runs = rd.runs
    finally:
        rd.close()
    assert runs >= 2, "an aged-out nettop is replaced at once, without the error backoff"


def test_reader_close_stops_a_hung_nettop(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_BLOCKS", "2")
    monkeypatch.setenv("FAKE_MODE", "hang")
    rd = S.NettopReader(cmd=[fake_nettop(tmp_path)], quiet_s=0.15)
    assert rd.start()
    got = wait_blocks(rd, 1)
    proc = rd.proc
    rd.close()
    rd.thread.join(10)
    assert len(got) == 1 and not rd.thread.is_alive() and proc.poll() is not None


HOST = r"""
import importlib.util, sys, time
sp = importlib.util.spec_from_file_location("bpl_host", sys.argv[1])
m = importlib.util.module_from_spec(sp)
sp.loader.exec_module(m)
r = m.NettopReader(cmd=[sys.argv[2]], quiet_s=0.15)
assert r.start()
while r.proc is None:
    time.sleep(0.05)
print(r.proc.pid, flush=True)
time.sleep(60)
"""


def test_a_killed_sampler_does_not_leave_nettop_running(tmp_path, monkeypatch):
    """2026-11-03: after a SIGKILLed sampler, the orphaned nettop wrote to the dead pty at 146% CPU. The pty is now
    its controlling terminal, so the hangup ends it (the fake here sleeps, so only SIGHUP can)."""
    monkeypatch.setenv("FAKE_BLOCKS", "2")
    monkeypatch.setenv("FAKE_MODE", "hang")
    host = tmp_path / "host.py"
    host.write_text(HOST)
    p = subprocess.Popen([sys.executable, str(host), str(CLIENT / "bloom-power-log.py"), fake_nettop(tmp_path)],
                         stdout=subprocess.PIPE, text=True,
                         env={**os.environ, "PYTHONPATH": str(HERE)})
    child = None
    try:
        child = int(p.stdout.readline())
        time.sleep(1.5)                  # the wrapper has become the fake nettop, which wrote its blocks
        os.kill(child, 0)
        p.kill()
        p.wait(5)
        end = time.time() + 10
        while time.time() < end:
            try:
                os.kill(child, 0)
            except ProcessLookupError:
                child = None
                break
            time.sleep(0.1)
        assert child is None, "nettop outlived a SIGKILLed sampler"
    finally:
        if p.poll() is None:
            p.kill()
        if child is not None:
            try:
                os.kill(child, signal.SIGKILL)
            except ProcessLookupError:
                pass


def test_reader_without_nettop_does_not_start(tmp_path):
    assert S.NettopReader(cmd=[str(tmp_path / "no-such-nettop")]).start() is False
