"""Tamper detection and owner separation tests for research receipts."""
import sqlite3
import pytest
from skeleton.ai.webcrawler.dragon_research_audit import DragonResearchAudit


def test_audit_chain_verifies_and_is_owner_scoped():
    connection = sqlite3.connect(":memory:")
    audit = DragonResearchAudit(connection)
    first = audit.append("alice", "proposal_created", "p1", now=10)
    second = audit.append("alice", "proposal_approved", "p1", now=11)
    other = audit.append("bob", "proposal_rejected", "p2", now=12)
    assert first.sequence == 1 and second.sequence == 2
    assert other.sequence == 1
    assert second.previous_hash == first.event_hash
    assert audit.verify("alice") and audit.verify("bob")


def test_modified_receipt_fails_verification():
    connection = sqlite3.connect(":memory:")
    audit = DragonResearchAudit(connection)
    audit.append("alice", "proposal_created", "p1", now=10)
    audit.append("alice", "proposal_approved", "p1", now=11)
    connection.execute("""
        UPDATE dragon_research_audit SET action='proposal_rejected'
        WHERE owner='alice' AND sequence=1
    """)
    connection.commit()
    assert not audit.verify("alice")


def test_deleted_middle_event_fails_verification():
    connection = sqlite3.connect(":memory:")
    audit = DragonResearchAudit(connection)
    for i in range(3):
        audit.append("alice", "proposal_created", str(i), now=10 + i)
    connection.execute(
        "DELETE FROM dragon_research_audit WHERE owner='alice' AND sequence=2"
    )
    connection.commit()
    assert not audit.verify("alice")


def test_invalid_actions_and_budget_are_rejected():
    audit = DragonResearchAudit(sqlite3.connect(":memory:"))
    with pytest.raises(ValueError):
        audit.append("alice", "secret_download", "p1", now=10)
    audit.append("alice", "proposal_created", "p1", now=10)
    with pytest.raises(ValueError, match="budget"):
        audit.verify("alice", max_events=0)


def test_owner_can_erase_receipts():
    audit = DragonResearchAudit(sqlite3.connect(":memory:"))
    audit.append("alice", "consent_revoked", "all", now=10)
    assert audit.erase("alice") == 1
    assert audit.verify("alice")


def test_integer_and_float_audit_timestamps_produce_stable_signed_chain():
    db=sqlite3.connect(":memory:")
    audit=DragonResearchAudit(db)
    one=audit.append("owner","proposal_created","p1",now=10)
    two=audit.append("owner","proposal_approved","p1",now=11.0)
    assert one.observed_at==10.0 and two.observed_at==11.0
    assert audit.verify("owner")
    old=DragonResearchAudit._digest("legacy",1,"proposal_created","p1",10,"0"*64)
    db.execute("""INSERT INTO dragon_research_audit VALUES(?,?,?,?,?,?,?)""",
               ("legacy",1,"proposal_created","p1",10,"0"*64,old))
    db.commit()
    assert audit.verify("legacy")
    db.execute("""UPDATE dragon_research_audit SET subject_id='tampered'
                  WHERE owner='legacy'""")
    db.commit()
    assert not audit.verify("legacy")
