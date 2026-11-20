"""Optional integrations. Everything here is off unless switched on; nothing in the core needs any of it.

BloomGauge (a separate Mac app that some Darkbloom operators use) is optional: the ledger reads Darkbloom directly and never
reads BloomGauge data. The switch only records that the operator uses it, so Status can say so. The Mac client can detect the
app to offer the switch, but detection never turns it on."""
import os

TRUE = ("1", "true", "yes", "on")


def _truthy(v):
    return str(v or "").strip().lower() in TRUE


def bloomgauge_state(db=None, env=None):
    """'enabled' when BLOOM_BLOOMGAUGE is set (or the setup page stored the choice), else 'not set up'."""
    env = os.environ if env is None else env
    if _truthy(env.get("BLOOM_BLOOMGAUGE")) or _truthy(env.get("BLOOMGAUGE_ENABLED")):
        return "enabled"
    if db is not None:
        try:
            r = db.execute("SELECT v FROM acct_meta WHERE k = 'integration_bloomgauge'").fetchone()
            if r and r[0] == "1":
                return "enabled"
        except Exception:
            pass
    return "not set up"


def set_bloomgauge(db, on):
    db.execute("CREATE TABLE IF NOT EXISTS acct_meta (k TEXT PRIMARY KEY, v TEXT)")
    db.execute("INSERT OR REPLACE INTO acct_meta (k, v) VALUES ('integration_bloomgauge', ?)", ("1" if on else "0",))
    db.commit()


def describe(db=None, env=None):
    state = bloomgauge_state(db, env)
    return [{"name": "BloomGauge", "optional": True, "state": state,
             "detail": "Not needed. The ledger reads Darkbloom directly." if state != "enabled" else "Switched on. The ledger does not depend on it."}]
