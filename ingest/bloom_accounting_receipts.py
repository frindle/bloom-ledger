"""Receipt files for ledger entries: one stored file per entry under <data>/receipts, named by entry id and content hash.

Upload: POST /v1/accounting/entries/<id>/receipt with the raw file as the body and its Content-Type.
Download: GET /v1/accounting/entries/<id>/receipt. Bookkeeping records, not tax advice."""
import hashlib
import os
import re

import bloom_accounting_entries as AE

MAX_BYTES = 10 * 1024 * 1024
TYPES = {"application/pdf": ".pdf", "image/jpeg": ".jpg", "image/png": ".png", "image/heic": ".heic", "image/webp": ".webp"}
EXT_TYPE = {v: k for k, v in TYPES.items()}
PATH_RE = re.compile(r"^/v1/accounting/entries/([1-9][0-9]{0,9})/receipt\Z")


def entry_id_from_path(path):
    m = PATH_RE.match(path.split('?', 1)[0])
    return int(m.group(1)) if m else None


def receipt_dir(root):
    return os.path.join(str(root), "receipts")


def receipt_post(db, root, entry_id, content_type, body):
    type_ = (content_type or "").split(";", 1)[0].strip().lower()
    if type_ not in TYPES:
        return (415, {"error": "receipt must be a PDF, JPEG, PNG, HEIC or WebP file"})
    if not body:
        return (400, {"error": "empty receipt"})
    if len(body) > MAX_BYTES:
        return (413, {"error": "too large"})
    if not any(e["id"] == entry_id for e in AE.current_entries(db)):
        return (404, {"error": "not found"})
    name = "entry-%d-%s%s" % (entry_id, hashlib.sha256(body).hexdigest()[:16], TYPES[type_])
    os.makedirs(receipt_dir(root), exist_ok=True)
    tmp_name = "." + name + ".tmp"
    with open(os.path.join(receipt_dir(root), tmp_name), "wb") as f:
        f.write(body)
    os.replace(os.path.join(receipt_dir(root), tmp_name), os.path.join(receipt_dir(root), name))
    AE.attach_receipt(db, entry_id, name)
    return (201, {"receipt": name})


def receipt_get(db, root, entry_id):
    e = next((e for e in AE.all_entries(db) if e["id"] == entry_id), None)
    if not e or not e.get("receipt"):
        return (404, "application/json", b'{"error": "not found"}')
    path = os.path.join(receipt_dir(root), e["receipt"])
    if not os.path.isfile(path):
        return (404, "application/json", b'{"error": "not found"}')
    ext = os.path.splitext(e["receipt"])[1]
    ct = EXT_TYPE.get(ext, "application/octet-stream")
    with open(path, "rb") as f:
        return (200, ct, f.read())
