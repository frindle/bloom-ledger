"""bloom-power-log.py: per-process CPU / GPU use (2026-11-06, for bloom-ledger's "usage" business share).

Each row gets USAGE_COLUMNS in power/usage-YYYY-MM.csv: CPU time + kernel energy per bucket (Darkbloom, Sandbox, own)
from proc_pid_rusage, GPU time per bucket from ioreg AGXDeviceUserClient, and macmon's CPU and GPU energy. Fake
snapshots, fake ps / ioreg and plist fixtures only: never reads real counters, never probes Darkbloom.
"""
import importlib.util
import json
import plistlib
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CLIENT = HERE.parent / "client"
sys.path.insert(0, str(HERE))
NOW = 1793680600.0
ME = 501
DBK = "/Users/penn/.darkbloom/Darkbloom.app/Contents/MacOS/darkbloom start --foreground --model m"
VM = "/System/Library/Frameworks/Virtualization.framework/Versions/A/XPCServices/com.apple.Virtualization.VirtualMachine.xpc"
VMGPU = ("/System/Library/Frameworks/ParavirtualizedGraphics.framework/Versions/A/XPCServices/"
         "com.apple.gpusw.ParavirtualizedGraphicsGPUTask.xpc/Contents/MacOS/com.apple.gpusw.ParavirtualizedGraphicsGPUTask")


def load(name, file, base=HERE):
    sp = importlib.util.spec_from_file_location(name, base / file)
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


L = load("bloom_power_lib_us", "bloom_power_lib.py")
S = load("bloom_power_log_us", "bloom-power-log.py", CLIENT)


def ioreg(*clients):
    return plistlib.dumps([{"IORegistryEntryID": rid, "IOUserClientCreator": f"pid {pid}, x",
                            "AppUsage": [{"API": "Metal", "accumulatedGPUTime": ns}]} for rid, pid, ns in clients])


def snap(t, abs_, procs, cpu=None, gpu=None):
    return {"t": t, "abs": abs_, "procs": procs, "cpu": cpu, "gpu": gpu}


# ---------------------------------------------------------------- columns
def test_usage_sidecar_columns_and_bridge():
    assert L.USAGE_BRIDGE == "usage-{month}.csv"
    assert L.USAGE_BRIDGE_COLUMNS == ["ts_utc"] + L.USAGE_COLUMNS
    assert L.USAGE_DELTA_COLUMNS == L.USAGE_COLUMNS[:L.USAGE_COLUMNS.index("cpu_mj")]
    assert L.USAGE_COLUMNS[-3:] == ["cpu_mj", "gpu_mj", "dbk_local"]
    assert not set(L.USAGE_COLUMNS) & set(L.POWER_COLUMNS), "the main power-log header never changes"
    assert (L.USAGE_BRIDGE, L.USAGE_BRIDGE_COLUMNS) in L.BRIDGES


def test_bridge_row_writes_the_usage_sidecar(tmp_path):
    row = {c: "" for c in L.POWER_COLUMNS + L.NET_COLUMNS + L.USAGE_COLUMNS + ["sandbox_jobs"]}
    row.update({"ts_utc": "2026-11-06T20:00:00Z", "usage_s": 60.0, "dbk_cpu_ms": 1200, "gpu_mj": 900000,
                "dbk_local": 0})
    L.bridge_row(tmp_path, row)
    lines = (tmp_path / "power" / "usage-2026-11.csv").read_text().splitlines()
    assert lines[0] == ",".join(L.USAGE_BRIDGE_COLUMNS)
    vals = dict(zip(L.USAGE_BRIDGE_COLUMNS, lines[1].split(",")))
    assert vals["usage_s"] == "60.0" and vals["dbk_cpu_ms"] == "1200" and vals["gpu_mj"] == "900000"
    assert vals["sbx_cpu_ms"] == "" and vals["dbk_local"] == "0"


# ---------------------------------------------------------------- parsing
def test_parse_macmon_parts():
    assert L.parse_macmon_parts(json.dumps({"cpu_power": 3.5, "gpu_power": 20})) == (3.5, 20.0)
    for bad in ('{"cpu_power": 3}', '{"cpu_power": -1, "gpu_power": 2}', '{"cpu_power": "x", "gpu_power": 2}',
                "not json", '{"cpu_power": NaN, "gpu_power": 1}'):
        assert L.parse_macmon_parts(bad) is None, bad


def test_usage_bucket():
    assert L.usage_bucket(DBK, ME, ME) == "dbk"
    assert L.usage_bucket("darkbloom start", ME, ME) == "dbk"
    assert L.usage_bucket("/Users/penn/.darkbloom/bin/darkbloom status", ME, ME) == "dbk"
    assert L.usage_bucket("/Applications/Darkbloom Monitor.app/Contents/MacOS/Darkbloom Monitor", ME, ME) == "own"
    assert L.usage_bucket("/x/DarkbloomSandbox.app/Contents/MacOS/DarkbloomSandbox", ME, ME) == "sbx"
    assert L.usage_bucket("sandbox-linux-worker --job 1", ME, ME) == "sbx"
    assert L.usage_bucket(VM, ME, ME) == "vm"
    assert L.usage_bucket(VMGPU, ME, ME) == "vmgpu"
    assert L.usage_bucket("/opt/homebrew/bin/macmon pipe -i 1000", ME, ME) == "sys"
    assert L.usage_bucket("/usr/bin/python3 bloom-power-log.py", ME, ME) == "sys"
    assert L.usage_bucket("/Applications/Safari.app/Contents/MacOS/Safari", ME, ME) == "own"
    assert L.usage_bucket(DBK, 0, ME) == "sys", "another user's process is the system's"


def test_parse_gpu_clients_sums_app_usage_and_skips_junk():
    data = plistlib.dumps([
        {"IORegistryEntryID": 10, "IOUserClientCreator": "pid 43458, darkbloom",
         "AppUsage": [{"accumulatedGPUTime": 5_000_000}, {"accumulatedGPUTime": 2_000_000}, {"x": 1}]},
        {"IORegistryEntryID": 11, "IOUserClientCreator": "pid 900, WindowServer"},
        {"IORegistryEntryID": 12, "IOUserClientCreator": "no pid here", "AppUsage": [{"accumulatedGPUTime": 1}]},
        {"IOUserClientCreator": "pid 1, x"}, "junk"])
    assert L.parse_gpu_clients(data) == {10: (43458, 7_000_000), 11: (900, 0)}
    assert L.parse_gpu_clients(b"") == {} and L.parse_gpu_clients(b"<not a plist") == {}


# ---------------------------------------------------------------- deltas
PROCS = {1: (ME, DBK), 2: (ME, "/Applications/Safari.app/Contents/MacOS/Safari"), 3: (ME, VM), 4: (ME, VM),
         5: (0, "/usr/libexec/WindowServer"), 6: (ME, "/opt/homebrew/bin/macmon pipe")}


def test_deltas_split_cpu_and_gpu_by_bucket():
    prev = snap(100.0, 1000, PROCS,
                cpu={(1, 10): (1e9, 5e9), (2, 10): (2e9, 1e9), (3, 10): (0, 0), (4, 10): (0, 0), (6, 10): (1e9, 1e9)},
                gpu={20: (1, 1e9), 21: (2, 0), 22: (5, 0)})
    cur = snap(160.04, 2000, PROCS,
               cpu={(1, 10): (31e9, 65e9), (2, 10): (7e9, 3e9), (3, 10): (9e9, 9e9), (4, 10): (1e9, 1e9),
                    (6, 10): (2e9, 2e9)},
               gpu={20: (1, 41e9), 21: (2, 3e9), 22: (5, 2e9), 23: (3, 4e9)})
    d = L.usage_deltas(prev, cur, sandbox_jobs=1, my_uid=ME)
    assert set(d) == set(L.USAGE_DELTA_COLUMNS)
    assert d["usage_s"] == 60.0
    assert (d["dbk_cpu_ms"], d["dbk_cpu_mj"], d["dbk_gpu_ms"]) == (30000, 60000, 40000)
    assert (d["sbx_cpu_ms"], d["sbx_cpu_mj"], d["sbx_gpu_ms"]) == (9000, 9000, 4000), "busiest VM is the job's"
    assert (d["own_cpu_ms"], d["own_cpu_mj"], d["own_gpu_ms"]) == (5000 + 1000, 2000 + 1000, 3000)
    assert d["sys_gpu_ms"] == 2000, "WindowServer GPU is the system's; macmon CPU drops into the remainder"


def test_no_jobs_means_every_vm_is_own():
    prev = snap(0.0, 0, PROCS, cpu={(3, 1): (0, 0)}, gpu={})
    cur = snap(60.0, 9, PROCS, cpu={(3, 1): (4e9, 2e9)}, gpu={})
    d = L.usage_deltas(prev, cur, sandbox_jobs=0, my_uid=ME)
    assert d["own_cpu_ms"] == 4000 and d["sbx_cpu_ms"] == 0


def test_vm_gpu_helpers_follow_the_jobs_and_meters_are_the_systems():
    procs = {**PROCS, 7: (ME, VMGPU), 8: (ME, VMGPU), 10: (ME, "/usr/bin/nettop -P -x -n")}
    prev = snap(0.0, 0, procs, cpu={(7, 1): (0, 0), (8, 1): (0, 0), (10, 1): (0, 0)}, gpu={50: (7, 0), 51: (8, 0)})
    cur = snap(60.0, 1, procs, cpu={(7, 1): (1e9, 1e9), (8, 1): (2e9, 2e9), (10, 1): (5e9, 5e9)},
               gpu={50: (7, 9e9), 51: (8, 1e9)})
    cur["meters"] = {10}
    d = L.usage_deltas(prev, cur, sandbox_jobs=1, my_uid=ME)
    assert d["sbx_gpu_ms"] == 9000 and d["sbx_cpu_ms"] == 1000, "the busiest-GPU helper is the job's"
    assert d["own_gpu_ms"] == 1000 and d["own_cpu_ms"] == 2000, "the other helper and the meter's nettop are not own"
    d0 = L.usage_deltas(prev, cur, sandbox_jobs=0, my_uid=ME)
    assert d0["sbx_gpu_ms"] == 0 and d0["own_gpu_ms"] == 10000


def test_new_and_missed_processes_and_clients():
    prev = snap(0.0, 5000, PROCS, cpu={}, gpu={30: (1, 0)})
    cur = snap(60.0, 9000, PROCS,
               cpu={(1, 6000): (2e9, 4e9),        # started after prev: all of it counts
                    (2, 4000): (9e9, 9e9)},       # started before prev but not seen then: missed, counts nothing
               gpu={30: (1, 1e9), 31: (1, 5e9),   # higher id: a new client, all of it counts
                    29: (2, 7e9)})                # lower id, not seen before: missed
    d = L.usage_deltas(prev, cur, my_uid=ME)
    assert d["dbk_cpu_ms"] == 2000 and d["dbk_cpu_mj"] == 4000 and d["own_cpu_ms"] == 0
    assert d["dbk_gpu_ms"] == 6000 and d["own_gpu_ms"] == 0


def test_counter_going_down_or_pid_reuse_never_goes_negative():
    prev = snap(0.0, 0, PROCS, cpu={(1, 1): (9e9, 9e9)}, gpu={40: (1, 9e9)})
    cur = snap(60.0, 1, PROCS, cpu={(1, 1): (1e9, 1e9)}, gpu={40: (2, 1e9)})
    d = L.usage_deltas(prev, cur, my_uid=ME)
    assert d["dbk_cpu_ms"] == 0 and d["dbk_gpu_ms"] == 0 and d["own_gpu_ms"] == 0


def test_unmeasured_parts_are_blank_and_missing_snapshots_are_none():
    prev = snap(0.0, 0, PROCS, cpu=None, gpu={1: (1, 0)})
    cur = snap(60.0, 1, PROCS, cpu={(1, 1): (1e9, 1e9)}, gpu={1: (1, 2e9)})
    d = L.usage_deltas(prev, cur, my_uid=ME)
    assert d["dbk_cpu_ms"] == "" and d["own_cpu_mj"] == "" and d["dbk_gpu_ms"] == 2000
    assert L.usage_deltas(None, cur) is None and L.usage_deltas(prev, None) is None


# ---------------------------------------------------------------- window + probe
def test_window_integrates_macmon_cpu_and_gpu_energy():
    w = S.Window(NOW - 60)
    for i in range(60):
        w.add_power(NOW - 60 + i, 30.0, 0.5, (2.0, 10.0))
    r = w.row(NOW, None)
    assert r["cpu_mj"] == 120000 and r["gpu_mj"] == 600000
    assert r["dbk_local"] == 0
    w2 = S.Window(NOW - 60)
    w2.add_power(NOW - 30, 30.0, 0.5)
    w2.other.add("local-endpoint-client:curl")
    r2 = w2.row(NOW, None)
    assert r2["cpu_mj"] == "" and r2["gpu_mj"] == "" and r2["dbk_local"] == 1


class FakeLib:
    def __init__(self):
        self.ticks = 0

    def mach_absolute_time(self):
        self.ticks += 1000
        return self.ticks


def test_probe_rows_from_fake_ps_ioreg_and_rusage(monkeypatch):
    me = S.os.getpid()
    ps = [f"  1 1 {ME} {DBK}\n  2 1 {ME} /Applications/Safari.app/Contents/MacOS/Safari\n  5 1 0 /usr/libexec/WindowServer\n"
          f"  9 {me} {ME} /usr/bin/nettop -P -x\ngarbage line\n"]
    gpu = [ioreg((7, 1, 0), (8, 5, 0)), ioreg((7, 1, 3_000_000_000), (8, 5, 1_000_000_000))]
    p = S.UsageProbe(run=lambda cmd: ps[0], ioreg=lambda: gpu.pop(0))
    p.lib = FakeLib()
    calls = {1: [(1, 0, 0), (1, 2_000_000_000, 6_000_000_000)], 2: [(1, 0, 0), (1, 500_000_000, 100_000_000)],
             9: [(1, 0, 0), (1, 7_000_000_000, 7_000_000_000)]}
    seen = []

    def rusage(pid):
        seen.append(pid)
        return calls[pid].pop(0)
    p.rusage = rusage
    monkeypatch.setattr(S.os, "getuid", lambda: ME)
    p.prime()
    out = p.close_row(0)
    assert 5 not in seen, "another user's process is never read"
    assert set(out) == set(L.USAGE_DELTA_COLUMNS)
    assert out["dbk_cpu_ms"] == 2000 and out["dbk_cpu_mj"] == 6000 and out["dbk_gpu_ms"] == 3000
    assert out["own_cpu_ms"] == 500 and out["own_cpu_mj"] == 100 and out["sys_gpu_ms"] == 1000, \
        "the sampler's own nettop child is the system's"


def test_probe_never_raises_and_blanks_what_it_cannot_read(monkeypatch):
    monkeypatch.setattr(S.os, "getuid", lambda: ME)
    def boom(*a):
        raise OSError("no ps")
    p = S.UsageProbe(run=boom, ioreg=boom)
    p.prime()
    assert p.close_row(1) == {c: "" for c in L.USAGE_DELTA_COLUMNS}
    p2 = S.UsageProbe(run=lambda cmd: f"1 1 {ME} {DBK}\n", ioreg=lambda: ioreg((1, 1, 0)))
    p2.lib = None                                  # no libSystem (not macOS): GPU only
    p2.prime()
    out = p2.close_row(0)
    assert out["dbk_cpu_ms"] == "" and out["dbk_gpu_ms"] == 0
