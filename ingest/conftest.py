import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(1, str(HERE.parents[2] / "bin"))   # bloom_ledger.py / bloom_power_lib.py (copied to /app in the image)


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _export_api_on_for_tests(monkeypatch, request):
    """Most tests exercise the export routes; the gate itself is tested in test_export_gate.py with the variable unset."""
    if "export_gate" not in request.node.nodeid:
        monkeypatch.setenv("BLOOM_ENABLE_EXPORT_API", "1")


@pytest.fixture(autouse=True)
def _auth_off_for_old_tests(monkeypatch, request):
    """Older tests drive writes without a login. test_auth*.py and test_e2e*.py run with the real default."""
    if "test_auth" not in request.node.nodeid and "test_e2e" not in request.node.nodeid:
        monkeypatch.setenv("BLOOM_AUTH", "off")
