"""bloom-power-log.py: network byte columns (2026-11-03, for bloom-ledger's bandwidth lines).

gpu_bytes_in/out, sandbox_bytes_in/out, total_bytes_in/out are NOT in the main power-log header here; they always go
to power/net-bytes-YYYY-MM.csv (and sandbox_jobs to power/sandbox-jobs-YYYY-MM.csv). Since 2026-11-19 all of them count
INTERNET traffic only and come from one long-running per-flow nettop in delta mode (a fake nettop script here, plus
synthetic per-flow lines using documentation addresses as stand-in public ones); the net_scope column marks those rows.
A restarted process or a glitch never yields a negative or a spike. Temp files and fake commands
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
SIDE_HEADER = "ts_utc,gpu_bytes_in,gpu_bytes_out,sandbox_bytes_in,sandbox_bytes_out,total_bytes_in,total_bytes_out,net_scope"


def test_the_main_power_log_header_is_unchanged_and_the_sidecar_headers_are_exact():
    want = ["gpu_bytes_in", "gpu_bytes_out", "sandbox_bytes_in", "sandbox_bytes_out", "total_bytes_in",
            "total_bytes_out"]
    assert L.POWER_COLUMNS == MAIN_HEADER
    assert L.NET_COLUMNS == want and L.NET_BRIDGE_COLUMNS == ["ts_utc"] + want + ["net_scope"]
    assert ",".join(L.NET_BRIDGE_COLUMNS) == SIDE_HEADER
    assert L.SANDBOX_BRIDGE_COLUMNS == ["ts_utc", "sandbox_jobs"]
    assert L.NET_BRIDGE == "net-bytes-{month}.csv" and L.SANDBOX_BRIDGE == "sandbox-jobs-{month}.csv"
    assert L.DAEMON_COLUMNS[0] == "machine_id" and L.DAEMON_COLUMNS[-1] == "resident_seconds"


def prow(ts, **kw):
    r = {c: "" for c in L.POWER_COLUMNS}
    r.update({"ts_utc": ts, "interval_s": 60, "power_ok": 1, "avg_w": 9, "wh": 0.15, "dbk_state": "idle",
              "sandbox_jobs": 0, "gpu_bytes_in": 10, "gpu_bytes_out": 20, "sandbox_bytes_in": 30,
              "sandbox_bytes_out": 40, "total_bytes_in": 500, "total_bytes_out": 600, "net_scope": "internet"})
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
    assert net == [SIDE_HEADER, "2026-11-03T07:00:00Z,10,20,30,40,500,600,internet"]
    sb = (tmp_path / "power" / "sandbox-jobs-2026-11.csv").read_text().splitlines()
    assert sb == ["ts_utc,sandbox_jobs", "2026-11-03T07:00:00Z,2"]
    L.bridge_row(tmp_path, prow("2026-11-03T07:01:00Z"))
    assert len((tmp_path / "power" / "net-bytes-2026-11.csv").read_text().splitlines()) == 3


def test_write_row_bridges_the_bytes_through_the_sampler(tmp_path, monkeypatch):
    monkeypatch.setattr(S.L, "HOME_DIR", tmp_path)
    S.write_row(prow("2026-11-03T06:00:00Z", gpu_bytes_in=7))
    assert (tmp_path / "power" / "net-bytes-2026-11.csv").read_text().splitlines() == [
        SIDE_HEADER, "2026-11-03T06:00:00Z,7,20,30,40,500,600,internet"]
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
# Synthetic per-flow lines. 203.0.113.x / 198.51.100.x / 2001:db8:: are documentation ranges standing in for public hosts.
HDR = ",interface,state,bytes_in,bytes_out,"


@pytest.mark.parametrize("line, want", [
    (HDR, ("header", None)),
    (HDR + "\r", ("header", None)),
    ("darkbloom.98299,,,1069098,1234,", ("proc", ("darkbloom", 98299, 1069098, 1234))),
    ("darkbloom-sandb.16219,,,5,6,\r", ("proc", ("darkbloom-sandb", 16219, 5, 6))),
    ("Slack Helper.1023,,,56,54,", ("proc", ("Slack Helper", 1023, 56, 54))),
    ("2.1.316.2427,,,0,0,", ("proc", ("2.1.316", 2427, 0, 0))),
    ("odd,name.77,,,1,2,", ("proc", ("odd,name", 77, 1, 2))),
    ("noTrailing.5,,,1,2", ("proc", ("noTrailing", 5, 1, 2))),
    ("neg.5,,,-40,3,", ("proc", ("neg", 5, 0, 3))),
    ("tcp4 192.168.1.5:50000<->203.0.113.9:443,en0,Established,100,200,", ("flow", ("203.0.113.9", "en0", 100, 200))),
    ("tcp4 192.168.1.5:50000<->192.168.1.20:445,en0,Established,7,8,", ("flow", ("192.168.1.20", "en0", 7, 8))),
    ("tcp6 2001:db8::2.50000<->2001:db8:1::9.443,en0,Established,1,2,", ("flow", ("2001:db8:1::9", "en0", 1, 2))),
    ("tcp6 fe80::1%en0.5000<->fe80::2%en0.5001,en0,Established,1,2,", ("flow", ("fe80::2", "en0", 1, 2))),
    ("udp4 10.9.0.2:51820<->198.51.100.7:2408,utun4,,30,40,", ("flow", ("198.51.100.7", "utun4", 30, 40))),
    ("udp4 *:5353<->*:*,en0,,3,4,", ("flow", ("", "en0", 3, 4))),
    ("udp6 *.*<->*.*,,,3,4,", ("flow", ("", "", 3, 4))),
    ("", (None, None)),
    ("garbage", (None, None)),
    ("nopid,,,1,2,", (None, None)),
    ("x.12a,,,1,2,", (None, None)),
    ("x.12,,,one,2,", (None, None)),
    ("darkbloom.1,5,6,", (None, None)),                  # the old per-process layout (three fields) is not a flow row
])
def test_nettop_lines(line, want):
    assert L.parse_nettop_line(line) == want


def test_nettop_command_is_per_flow_with_the_interface_column():
    assert "-P" not in L.NETTOP_CMD, "-P would fold every flow into its process row"
    assert L.NETTOP_CMD[L.NETTOP_CMD.index("-J") + 1] == "interface,state,bytes_in,bytes_out"
    types = [L.NETTOP_CMD[i + 1] for i, a in enumerate(L.NETTOP_CMD) if a == "-t"]
    assert types == ["external", "undefined"], "undefined = utun* (WARP): needed for the per-process figures"


@pytest.mark.parametrize("addr, want", [
    ("203.0.113.9", True), ("198.51.100.7", True), ("8.8.4.4", True), ("2001:db8:1::9", True),
    ("2606:4700::1", True), ("::ffff:203.0.113.9", True),
    ("127.0.0.1", False), ("127.5.5.5", False), ("::1", False), ("10.1.2.3", False), ("172.16.0.1", False),
    ("172.31.255.255", False), ("172.32.0.1", True), ("192.168.50.2", False), ("100.64.0.1", False),
    ("100.127.255.255", False), ("100.128.0.1", True), ("169.254.9.9", False), ("fe80::1", False),
    ("fd12:3456::1", False), ("fc00::1", False), ("224.0.0.251", False), ("239.255.255.250", False),
    ("ff02::fb", False), ("255.255.255.255", False), ("0.0.0.0", False), ("::", False), ("::ffff:192.168.1.1", False),
    ("", False), ("*", False), ("not-an-address", False), (None, False),
])
def test_only_public_remote_addresses_are_the_internet(addr, want):
    assert L.is_internet_remote(addr) is want


@pytest.mark.parametrize("iface, want", [("utun4", True), ("utun0", True), ("ipsec0", True), ("lo0", True),
                                         ("awdl0", True), ("bridge0", True), ("en0", False), ("en12", False),
                                         ("", False), (None, False)])
def test_tunnel_interfaces(iface, want):
    assert L.is_tunnel_iface(iface) is want


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


PUB, PUB6, LAN, LAN6, CGNAT = "203.0.113.9", "2001:db8:1::9", "192.168.1.20", "fd00::5", "100.100.1.1"


def flow(remote, iface, b_in, b_out):
    return (remote, iface, b_in, b_out)


def blk(rows, dt=5.0, cls=None):
    cls = cls or {}
    return L.net_block_bytes(rows, dt, lambda n, p: cls.get(p))


def test_lan_loopback_cgnat_and_multicast_flows_do_not_count_internet_ones_do():
    rows = [("darkbloom", 1, [flow(PUB, "en0", 100, 10), flow(LAN, "en0", 5000, 5000), flow("127.0.0.1", "lo0", 9, 9),
                              flow(CGNAT, "en0", 7, 7), flow("224.0.0.251", "en0", 3, 3), flow("", "en0", 4, 4)]),
            ("backupd", 2, [flow(LAN, "en0", 10**9, 10**9), flow("fe80::2", "en0", 8, 8)]),
            ("Safari", 3, [flow(PUB6, "en0", 20, 2), flow(LAN6, "en0", 600, 600)])]
    by, notes = blk(rows, cls={1: "gpu"})
    assert by == {"gpu": [100, 10], "sandbox": [0, 0], "total": [120, 12]} and notes == []


def test_time_machine_style_lan_traffic_leaves_every_figure_at_zero():
    rows = [("backupd", 2, [flow(LAN, "en0", 10**9, 10**8), flow(LAN6, "en0", 5, 5)]),
            ("sandbox-macos-w", 4, [flow(LAN, "en0", 300, 300)])]
    assert blk(rows, cls={4: "sandbox"})[0] == {"gpu": [0, 0], "sandbox": [0, 0], "total": [0, 0]}


def test_ipv6_internet_flows_count():
    rows = [("darkbloom", 1, [flow(PUB6, "en0", 11, 22)]), ("sandbox-macos-w", 4, [flow(PUB6, "en0", 33, 44)])]
    assert blk(rows, cls={1: "gpu", 4: "sandbox"})[0] == {"gpu": [11, 22], "sandbox": [33, 44], "total": [44, 66]}


def test_warp_counts_each_byte_once():
    """WARP on: an app's inner flow runs on utun4 to its real (public) destination, and WARP's own outer flow runs on
    en0 to a public address of the provider. The whole machine counts the outer flow only; a gpu/sandbox process has no
    outer flow of its own, so its inner flows count for it."""
    rows = [("CloudflareWARP", 607, [flow("198.51.100.7", "en0", 1000, 900)]),                   # the outer flow
            ("Safari", 3, [flow(PUB, "utun4", 700, 600)]),                                        # inner: not the wire
            ("darkbloom", 1, [flow(PUB, "utun4", 150, 120), flow(LAN, "utun4", 9, 9)]),
            ("sandbox-macos-w", 4, [flow(PUB6, "utun4", 40, 30)])]
    by, _ = blk(rows, cls={1: "gpu", 4: "sandbox"})
    assert by == {"gpu": [150, 120], "sandbox": [40, 30], "total": [1000, 900]}
    # WARP off: the same app flows are on en0 and count once, directly
    rows = [("Safari", 3, [flow(PUB, "en0", 700, 600)]), ("darkbloom", 1, [flow(PUB, "en0", 150, 120)])]
    assert blk(rows, cls={1: "gpu"})[0] == {"gpu": [150, 120], "sandbox": [0, 0], "total": [850, 720]}


def test_a_flow_with_no_interface_counts_as_the_wire():
    assert blk([("Safari", 3, [flow(PUB, "", 5, 6)])])[0]["total"] == [5, 6]


def test_gpu_and_sandbox_classes_sum_only_their_own_processes():
    rows = [("darkbloom", 1, [flow(PUB, "en0", 100, 10)]), ("darkbloom", 2, [flow(PUB, "en0", 7, 7)]),
            ("darkbloom-sandb", 3, [flow(PUB, "en0", 50, 5)]), ("sandbox-macos-w", 4, [flow(PUB, "en0", 1000, 2000)]),
            ("firefox", 5, [flow(PUB, "en0", 99999, 99999)])]
    cls = {1: "gpu", 2: None, 3: "sandbox", 4: "sandbox"}
    by, notes = blk(rows, cls=cls)
    assert by["gpu"] == [100, 10] and by["sandbox"] == [1050, 2005] and by["total"] == [101156, 102021]


def test_a_glitch_flow_counts_zero_with_a_note():
    big = int(L.NET_MAX_BPS * 5) + 1
    rows = [("sandbox-macos-w", 6, [flow(PUB, "en0", big, 0), flow(PUB, "en0", 4, 5)]),
            ("Safari", 7, [flow(PUB, "en0", 0, big)])]
    by, notes = blk(rows, cls={6: "sandbox"})
    assert by == {"gpu": [0, 0], "sandbox": [4, 5], "total": [4, 5]}
    assert notes == ["net spike dropped (sandbox: sandbox-macos-w.6)", "net spike dropped (total: Safari.7)"]


def test_a_process_with_no_flows_and_an_empty_block_count_nothing():
    assert blk([("darkbloom", 1, [])], cls={1: "gpu"})[0] == {"gpu": [0, 0], "sandbox": [0, 0], "total": [0, 0]}
    assert blk([])[0]["total"] == [0, 0]


# ---------------------------------------------------------------- the sampler side
class FakeReader:
    def __init__(self, blocks):
        self.blocks = list(blocks)

    def drain(self):
        out, self.blocks = self.blocks, []
        return out


def test_netprobe_counts_provider_and_sandbox_not_the_cli_and_remembers_an_exited_provider():
    blocks = [(NOW, 5.0, [("darkbloom", 98299, [flow(PUB, "en0", 1000, 100), flow(LAN, "en0", 777, 777)]),
                          ("darkbloom", 93990, [flow(PUB, "en0", 10, 1)]),
                          ("darkbloom", 5000, [flow(PUB, "en0", 12000, 800)]),
                          ("sandbox-macos-w", 27308, [flow(PUB, "utun4", 300, 3000)]),
                          ("firefox", 9, [flow(PUB, "en0", 5, 5)])])]
    rd = FakeReader(blocks)
    probe = S.NetProbe(rd)
    cmds = {98299: PROVIDER, 93990: WATCHDOG, 5000: CLI}
    w = S.Window(NOW - 60)
    probe.sample(w, NOW - 55, 98299, cmds)
    assert w.net == [1010, 101, 300, 3000]
    assert w.net_total == [1000 + 10 + 12000 + 5, 100 + 1 + 800 + 5], "the CLI and firefox are whole-machine traffic only; utun is not the wire"
    # the provider restarted: the old pid's last block arrives after ps stopped listing it and daemon-state moved on
    rd.blocks = [(NOW - 35, 5.0, [("darkbloom", 98299, [flow(PUB, "en0", 70, 7)]),
                                  ("darkbloom", 99000, [flow(PUB6, "en0", 5, 5)])])]
    probe.sample(w, NOW - 35, 99000, {99000: PROVIDER})
    assert w.net == [1010 + 75, 101 + 12, 300, 3000]
    r = w.row(NOW, None)
    assert [r[c] for c in L.NET_COLUMNS] == [1085, 113, 300, 3000, 13090, 918] and r["net_scope"] == "internet"


def test_a_lan_only_minute_is_a_measured_zero_not_a_gap():
    w = S.Window(NOW - 60)
    probe = S.NetProbe(FakeReader([(NOW, 15.0, [("backupd", 2, [flow(LAN, "en0", 10**9, 10**9)])])]))
    probe.sample(w, NOW - 50, None, {})
    r = w.row(NOW, None)
    assert [r[c] for c in L.NET_COLUMNS[4:]] == [0, 0]


def test_the_gpu_memory_of_an_exited_pid_expires():
    probe = S.NetProbe(FakeReader([]), gpu_memory_s=600)
    assert probe.classify("darkbloom", 7, 7, {}, NOW) == "gpu"
    probe.sample(S.Window(NOW), NOW + 601, None, {})
    assert probe.classify("darkbloom", 7, None, {}, NOW + 602) is None


def test_a_row_with_nothing_measured_leaves_the_byte_columns_empty_and_partial_cover_is_noted():
    r = S.Window(NOW - 60).row(NOW, None)
    assert [r[c] for c in L.NET_COLUMNS] == [""] * 6 and "net bytes" not in r["note"]
    w = S.Window(NOW - 60)
    w.add_net_block(20.0, {"gpu": [1, 2], "sandbox": [0, 0], "total": [0, 0]})
    r = w.row(NOW, None)
    assert [r[c] for c in L.NET_COLUMNS] == [1, 2, 0, 0, 0, 0] and "net bytes partial (20s of 60s)" in r["note"]
    assert set(L.POWER_COLUMNS) <= set(r) and set(L.NET_COLUMNS) <= set(r)
    w = S.Window(NOW - 60)
    for _ in range(12):
        w.add_net_block(5.0, {"gpu": [0, 0], "sandbox": [0, 0], "total": [0, 0]})
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
    sys.stdout.write(",interface,state,bytes_in,bytes_out,\n")
    base = 10**9 if i == 0 else 0          # block 0: cumulative totals, never a delta
    sys.stdout.write("darkbloom.98299,,,%d,%d,\n" % (base + 100 + i + 9, base + 10 + i))
    sys.stdout.write("tcp4 192.168.1.5:50000<->203.0.113.9:443,en0,Established,%d,%d,\n" % (base + 100 + i, base + 10 + i))
    sys.stdout.write("tcp4 192.168.1.5:50001<->192.168.1.20:445,en0,Established,9,0,\n")
    sys.stdout.write("sandbox-macos-w.27308,,,%d,7,\n" % (base + 5))
    sys.stdout.write("udp6 fd00::5.5000<->2001:db8:1::9.443,en0,,%d,7,\n" % (base + 5))
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
        assert all(f[2] < 10**9 for _, _, flows in rows for f in flows), "a run's first (cumulative) block leaked"
        assert [(n, p) for n, p, _ in rows] == [("darkbloom", 98299), ("sandbox-macos-w", 27308)]
        assert [f[0] for f in rows[0][2]] == ["203.0.113.9", "192.168.1.20"] and rows[1][2][0][:2] == ("2001:db8:1::9", "en0")
    assert [r[0][2][0][2] for _, _, r in got[:4]] == [101, 102, 101, 102]
    by, _ = L.net_block_bytes(got[0][2], got[0][1], lambda n, p: {98299: "gpu", 27308: "sandbox"}.get(p))
    assert by == {"gpu": [101, 11], "sandbox": [5, 7], "total": [106, 18]}, "the LAN flow in the fake output is left out"


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


def test_nettop_interval_is_one_constant_and_the_byte_totals_do_not_depend_on_it():
    i = L.NETTOP_CMD.index("-s")
    assert L.NETTOP_CMD[i + 1] == str(L.NETTOP_INTERVAL_S) and L.NETTOP_INTERVAL_S >= 15
    assert "-d" in L.NETTOP_CMD and L.NETTOP_CMD[L.NETTOP_CMD.index("-L") + 1] == "0"   # delta mode, no line limit
    rows = [("darkbloom", 10, [flow(PUB, "en0", 1000, 2000)]), ("sandbox-macos-w", 11, [flow(PUB, "en0", 30, 40)]),
            ("Safari", 12, [flow(PUB, "en0", 5, 5)])]
    classify = lambda name, pid: {"darkbloom": "gpu", "sandbox-macos-w": "sandbox"}.get(name)   # noqa: E731
    # the same bytes, whatever the block length: a 15 s block is not read as a glitch below the 40 Gbit/s cap
    a, na = L.net_block_bytes(rows, 5.0, classify)
    b, nb = L.net_block_bytes(rows, float(L.NETTOP_INTERVAL_S), classify)
    assert a == b == {"gpu": [1000, 2000], "sandbox": [30, 40], "total": [1035, 2045]} and na == nb == []


def test_a_minute_holding_one_block_fewer_is_not_partial_but_two_fewer_is():
    blk = float(L.NETTOP_INTERVAL_S)
    per_min = int(60 // blk)
    w = S.Window(NOW - 60)
    for _ in range(per_min - 1):            # block edges don't line up with the minute: one block fewer is normal
        w.add_net_block(blk - 0.2, {"gpu": [0, 0], "sandbox": [0, 0], "total": [0, 0]})
    assert "net bytes partial" not in w.row(NOW, None)["note"]
    w = S.Window(NOW - 60)
    for _ in range(per_min - 2):            # two missing blocks is a real gap (a nettop restart)
        w.add_net_block(blk, {"gpu": [0, 0], "sandbox": [0, 0], "total": [0, 0]})
    assert "net bytes partial" in w.row(NOW, None)["note"]


# ---------------------------------------------------------------- partial blocks
PARTIAL = r'''#!/usr/bin/env python3
import sys, time
w = sys.stdout.write
for i in range(3):
    w(",interface,state,bytes_in,bytes_out,\n")
    if i == 0:
        w("darkbloom.1,,,5,5,\n")
    elif i == 1:
        # a flow row that appears before any process row (a block cut at the top) is ignored, and a half-written
        # short line is not a row
        w("tcp4 192.168.1.5:5<->203.0.113.9:443,en0,Established,999,999,\n")
        w("darkbloom.1,,,1,1,\n")
        w("tcp4 192.168.1.5:6<->203.0.113.9:443,en0,Established,11,12,\n")
        w("tcp4 192.168.1.5:7<->203.0.113.9:443,en0,Established\n")
    else:
        w("darkbloom.1,,,1,1,\n")
        w("tcp4 192.168.1.5:6<->203.0.113.9:443,en0,Established,21,22,\n")
    sys.stdout.flush()
    time.sleep(0.4)
time.sleep(1.0)
'''


def test_a_block_cut_short_keeps_its_complete_flows_and_ignores_orphans(tmp_path):
    p = tmp_path / "nettop"
    p.write_text(PARTIAL.replace("#!/usr/bin/env python3", "#!" + sys.executable))
    p.chmod(0o755)
    rd = S.NettopReader(cmd=[str(p)], quiet_s=0.15, backoff_s=30)
    assert rd.start()
    try:
        got = wait_blocks(rd, 2)
    finally:
        rd.close()
    assert len(got) >= 2
    assert got[0][2] == [("darkbloom", 1, [("203.0.113.9", "en0", 11, 12)])]
    assert got[1][2] == [("darkbloom", 1, [("203.0.113.9", "en0", 21, 22)])]


# ---------------------------------------------------------------- history marker
OLD_HEADER = "ts_utc,gpu_bytes_in,gpu_bytes_out,sandbox_bytes_in,sandbox_bytes_out,total_bytes_in,total_bytes_out"


def old_month_file(tmp_path):
    f = tmp_path / "power" / "net-bytes-2026-11.csv"
    f.parent.mkdir(parents=True)
    f.write_text(OLD_HEADER + "\n2026-11-03T05:00:00Z,1,2,3,4,500,600\n")
    return f


def test_a_new_months_sidecar_carries_the_scope_column_from_its_first_line(tmp_path):
    L.bridge_row(tmp_path, prow("2026-12-01T00:01:00Z"))
    lines = (tmp_path / "power" / "net-bytes-2026-12.csv").read_text().splitlines()
    assert lines == [SIDE_HEADER, "2026-12-01T00:01:00Z,10,20,30,40,500,600,internet"]


def test_an_older_month_file_gets_one_second_header_line_and_its_old_rows_stay_byte_identical(tmp_path):
    f = old_month_file(tmp_path)
    before = f.read_bytes()
    L.bridge_row(tmp_path, prow("2026-11-19T07:00:00Z"))
    L.bridge_row(tmp_path, prow("2026-11-19T07:01:00Z"))
    after = f.read_bytes()
    assert after.startswith(before), "older rows are never rewritten"
    assert f.read_text().splitlines() == [
        OLD_HEADER, "2026-11-03T05:00:00Z,1,2,3,4,500,600",
        SIDE_HEADER, "2026-11-19T07:00:00Z,10,20,30,40,500,600,internet", "2026-11-19T07:01:00Z,10,20,30,40,500,600,internet"]


def test_a_restarted_sampler_does_not_repeat_the_second_header(tmp_path):
    f = old_month_file(tmp_path)
    L.bridge_row(tmp_path, prow("2026-11-19T07:00:00Z"))
    L._SCOPE_HEADER_SEEN.clear()            # a new process: it must find the header line already in the file
    L.bridge_row(tmp_path, prow("2026-11-19T07:01:00Z"))
    assert f.read_text().count(SIDE_HEADER) == 1 and len(f.read_text().splitlines()) == 5


def test_ingest_labels_rows_by_the_header_in_force(tmp_path):
    sys.path.insert(0, str(HERE.parent / "ingest"))
    A = importlib.import_module("bloom_accounting_index")
    I = importlib.import_module("bloom_ingest")
    f = old_month_file(tmp_path)
    L.bridge_row(tmp_path, prow("2026-11-19T07:00:00Z"))
    db = I.open_db(tmp_path / "i.sqlite")
    A.create_schema(db)
    A.store_net(db, "m1", f.read_text())
    got = {r[0]: r[1] for r in db.execute("SELECT ts, net_scope FROM net_bridge")}
    assert sorted(got.values()) == ["all", "internet"]
    # a headerless increment (what a later sync ships) of new-layout rows is internet, of old-layout rows is all
    A.store_net(db, "m2", "2026-11-19T07:05:00Z,1,2,3,4,5,6,internet\n2026-11-03T05:05:00Z,1,2,3,4,5,6\n")
    scopes = {r[0]: r[1] for r in db.execute("SELECT ts, net_scope FROM net_bridge WHERE machine_id = 'm2'")}
    assert sorted(scopes.values()) == ["all", "internet"]
