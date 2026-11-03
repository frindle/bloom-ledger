"""Frozen test: receipt route paths. Fake data."""
import bloom_accounting_receipts as R


def test_good_paths(tmp_path):
    assert R.receipt_dir(tmp_path) == str(tmp_path / "receipts")
    assert R.entry_id_from_path("/v1/accounting/entries/12/receipt") == 12
    assert R.entry_id_from_path("/v1/accounting/entries/12/receipt?x=1") == 12
    assert R.entry_id_from_path("/v1/accounting/entries/9999999999/receipt") == 9999999999
    assert R.MAX_BYTES == 10 * 1024 * 1024 and R.TYPES["image/jpeg"] == ".jpg" and sorted(R.TYPES) == sorted(
        ["application/pdf", "image/jpeg", "image/png", "image/heic", "image/webp"])


def test_bad_paths():
    for bad in ("/v1/accounting/entries/0/receipt", "/v1/accounting/entries/-1/receipt", "/v1/accounting/entries/x/receipt",
                "/v1/accounting/entries/12/receipt/..", "/v1/accounting/entries/12", "/v1/accounting/entries/void",
                "/v1/accounting/entries/12/receipt\n", "/v1/accounting/entries/01/receipt",
                "/v1/accounting/entries/12345678901/receipt"):
        assert R.entry_id_from_path(bad) is None, bad
