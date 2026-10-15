"""Historical SQLite REAL coercion must preserve exact integer-time evidence."""
import json
import sqlite3
from hashlib import sha256

from skeleton.ai.webcrawler.dragon_journal import DragonEventJournal
from skeleton.ai.webcrawler.dragon_research_audit import DragonResearchAudit
from skeleton.ai.webcrawler.dragon_runtime_events import DragonRuntimeEventLedger


def test_historical_integer_journal_hash_survives_without_rewriting():
    db=sqlite3.connect(":memory:"); journal=DragonEventJournal(db)
    body={"session_id":"s","sequence":1,"kind":"fetch_started","url":"https://example.org",
        "at":1,"payload":{},"previous_digest":"0"*64}
    digest=sha256(json.dumps(body,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
    db.execute("INSERT INTO dragon_companion_events VALUES (?,?,?,?,?,?,?,?,?)",
        ("s",1,digest,"fetch_started","https://example.org",1,"{}","0"*64,digest))
    assert journal.verify("s")
    journal.append("s","fetch_started","https://example.org",at=2)
    assert journal.verify("s")
    assert db.execute("SELECT digest FROM dragon_companion_events WHERE sequence=1").fetchone()[0]==digest
    db.execute("UPDATE dragon_companion_events SET at=1.5 WHERE sequence=1")
    assert not journal.verify("s")


def test_historical_runtime_hash_survives_but_other_changes_fail():
    db=sqlite3.connect(":memory:"); ledger=DragonRuntimeEventLedger(db)
    body=["u","r",1,"attempt","source","started","","",1,"0"*64]
    digest=sha256(json.dumps(body,separators=(",",":")).encode()).hexdigest()
    db.execute("INSERT INTO dragon_runtime_events VALUES (?,?,?,?,?,?,?,?,?,?,?)",(*body,digest))
    assert ledger.verify("u","r",authorized=True)
    ledger.append("u","r",event_type="attempt",layer="source",outcome="failed",occurred_at=2,authorized=True)
    assert ledger.verify("u","r",authorized=True)
    db.execute("UPDATE dragon_runtime_events SET outcome='accepted' WHERE sequence=1")
    assert not ledger.verify("u","r",authorized=True)


def test_historical_research_hash_survives_but_time_changes_fail():
    db=sqlite3.connect(":memory:"); audit=DragonResearchAudit(db)
    digest=sha256(json.dumps(["u",1,"digest_completed","source",1,"0"*64],separators=(",",":")).encode()).hexdigest()
    db.execute("INSERT INTO dragon_research_audit VALUES (?,?,?,?,?,?,?)",
        ("u",1,"digest_completed","source",1,"0"*64,digest))
    assert audit.verify("u")
    audit.append("u","digest_completed","new",now=2)
    assert audit.verify("u")
    db.execute("UPDATE dragon_research_audit SET observed_at=3 WHERE sequence=1")
    assert not audit.verify("u")
