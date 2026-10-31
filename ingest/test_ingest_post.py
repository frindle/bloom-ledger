"""Frozen test: bloom_ingest.handle_post (POST /v1/objects). Fixture tokens only."""
import hashlib

import pytest

import bloom_ingest as I

NOW = 1793300000.0
TOK = "fixture-token-m4max"
TOKENS = {hashlib.sha256(TOK.encode()).hexdigest(): "m4max",
          hashlib.sha256(b"fixture-token-m5").hexdigest(): "m5ultra"}


def sha(b):
    return hashlib.sha256(b).hexdigest()


def hdrs(body, tok=TOK, kind="log", digest=None):
    h = {"X-Bloom-Kind": kind, "X-Bloom-Sha256": digest if digest is not None else sha(body)}
    if tok is not None:
        h["Authorization"] = "Bearer " + tok
    return h


@pytest.fixture
def env(tmp_path):
    return tmp_path, I.open_db(tmp_path / "index.sqlite")


def count(db):
    return db.execute("SELECT COUNT(*) FROM objects").fetchone()[0]


def test_post_stores_then_is_idempotent(env):
    root, db = env
    body = b'{"m":1}\npayload\n'
    code, obj = I.handle_post(hdrs(body), body, TOKENS, root, db, NOW)
    assert code == 201 and obj == {"sha256": sha(body), "status": "written"}
    assert (root / "objects" / "m4max" / "log" / f"{sha(body)}.obj").read_bytes() == body
    code2, obj2 = I.handle_post(hdrs(body), body, TOKENS, root, db, NOW + 60)
    assert code2 == 200 and obj2["status"] == "exists"
    assert db.execute("SELECT received_at FROM objects").fetchall() == [(NOW,)], "first receipt time is kept"
    other = b"x\n"
    I.handle_post(hdrs(other, tok="fixture-token-m5"), other, TOKENS, root, db, NOW)
    assert db.execute("SELECT machine_id FROM objects WHERE sha256 = ?", (sha(other),)).fetchall() == [("m5ultra",)], \
        "the machine comes from the token"


@pytest.mark.parametrize("tok", [None, "", "wrong-token", TOK + " "])
def test_post_unauthorized(env, tok):
    root, db = env
    body = b"x\n"
    h = hdrs(body, tok=tok)
    if tok == TOK + " ":
        h["Authorization"] = "Basic " + TOK
    code, obj = I.handle_post(h, body, TOKENS, root, db, NOW)
    assert code == 401 and count(db) == 0 and not (root / "objects").exists()


def test_post_too_large(env):
    root, db = env
    code, _ = I.handle_post({"X-Bloom-Kind": "nope"}, b"x" * (I.MAX_BYTES + 1), TOKENS, root, db, NOW)
    assert code == 401, "auth is checked before size, kind or digest"
    body = b"x" * (I.MAX_BYTES + 1)
    code, _ = I.handle_post(hdrs(body, digest="0" * 64), body, TOKENS, root, db, NOW)
    assert code == 413 and count(db) == 0, "size is checked before the digest"
    ok = b"y" * I.MAX_BYTES
    assert I.handle_post(hdrs(ok), ok, TOKENS, root, db, NOW)[0] == 201, "exactly MAX_BYTES is allowed"


@pytest.mark.parametrize("kind,digest", [("secrets", None), ("", None), ("log", "xyz"), ("log", "")])
def test_post_bad_request(env, kind, digest):
    root, db = env
    body = b"x\n"
    code, _ = I.handle_post(hdrs(body, kind=kind, digest=digest), body, TOKENS, root, db, NOW)
    assert code == 400 and count(db) == 0


def test_post_sha_mismatch_and_uppercase(env):
    root, db = env
    body = b"x\n"
    code, _ = I.handle_post(hdrs(body, digest=sha(b"other")), body, TOKENS, root, db, NOW)
    assert code == 422 and count(db) == 0 and not any(root.rglob("*.obj"))
    code, obj = I.handle_post(hdrs(body, digest=sha(body).upper()), body, TOKENS, root, db, NOW)
    assert code == 201 and obj["sha256"] == sha(body), "hex case is normalised"
