#!/usr/bin/env python3
"""Manage API keys from the command line (stdlib only), for scripts and the container.

  bloom_keys.py create --label NAME [--replace]   prints only the new key on stdout (it is never stored or shown again)
  bloom_keys.py list                              label, created, last used (never a key)
  bloom_keys.py revoke --label NAME               revokes every active key with that label

The database is <BLOOM_DATA>/index.sqlite (BLOOM_DATA defaults to /data, as for the server)."""
import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bloom_api_keys as AK  # noqa: E402
import bloom_ingest as I  # noqa: E402


def stamp(t):
    return "never" if t is None else time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(t))


def main(argv=None, out=sys.stdout, err=sys.stderr):
    ap = argparse.ArgumentParser(prog="bloom_keys.py", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create")
    c.add_argument("--label", required=True)
    c.add_argument("--replace", action="store_true", help="revoke any active keys with the same label")
    sub.add_parser("list")
    r = sub.add_parser("revoke")
    r.add_argument("--label", required=True)
    args = ap.parse_args(argv)
    db = I.open_db(Path(os.environ.get("BLOOM_DATA", "/data")) / "index.sqlite")
    if args.cmd == "create":
        try:
            kid, key = AK.create(db, args.label)
        except ValueError as e:
            print(str(e), file=err)
            return 1
        if args.replace:
            AK.revoke_label(db, args.label.strip(), keep_id=kid)
        print(key, file=out)
    elif args.cmd == "list":
        for k in AK.list_keys(db):
            print("%s\tcreated %s\tlast used %s" % (k["label"], stamp(k["created_at"]), stamp(k["last_used_at"])), file=out)
    else:
        n = AK.revoke_label(db, args.label.strip())
        print("revoked %d key(s)" % n, file=err)
        return 0 if n else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
