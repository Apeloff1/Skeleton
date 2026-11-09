"""Forensic runtime event ledger regressions."""
import sqlite3,pytest
from dataclasses import replace
from skeleton.ai.webcrawler.dragon_runtime_events import DragonRuntimeEventLedger

def test_event_chain_verifies_and_orders():
 db=sqlite3.connect(":memory:");l=DragonRuntimeEventLedger(db)
 a=l.append("u","r",event_type="attempt",layer="temporal",outcome="started",occurred_at=1,authorized=True)
 b=l.append("u","r",event_type="attempt",layer="temporal",outcome="failed",error_code="PermissionError",occurred_at=2,authorized=True)
 assert b.previous_hash==a.event_hash and l.verify("u","r",authorized=True)

def test_tampered_event_is_detected():
 db=sqlite3.connect(":memory:");l=DragonRuntimeEventLedger(db)
 l.append("u","r",event_type="attempt",layer="source",outcome="started",occurred_at=1,authorized=True)
 db.execute("UPDATE dragon_runtime_events SET outcome='accepted' WHERE owner='u' AND run_id='r'");db.commit()
 assert not l.verify("u","r",authorized=True)

def test_event_time_cannot_regress():
 db=sqlite3.connect(":memory:");l=DragonRuntimeEventLedger(db)
 l.append("u","r",event_type="attempt",layer="source",outcome="started",occurred_at=2,authorized=True)
 with pytest.raises(ValueError,match="time regression"):
  l.append("u","r",event_type="attempt",layer="source",outcome="failed",occurred_at=1,authorized=True)

def test_failed_event_does_not_become_chain_receipt():
 db=sqlite3.connect(":memory:");l=DragonRuntimeEventLedger(db)
 l.append("u","r",event_type="attempt",layer="source_integrity",outcome="failed",error_code="ValueError",occurred_at=1,authorized=True)
 assert l.events("u","r",authorized=True)[0].outcome=="failed"
 tables={x[0] for x in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
 assert "dragon_analysis_run_receipts" not in tables
