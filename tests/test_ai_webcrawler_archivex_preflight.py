"""ArchiveX preflight consistency regression tests."""
import sqlite3
from skeleton.ai.webcrawler.archivex import ArchiveX
from skeleton.ai.webcrawler.archivex_knowledge import ArchiveXKnowledgeStore
from skeleton.ai.webcrawler.archivex_promotion import ArchiveXPromotionGate
from skeleton.ai.webcrawler.archivex_preflight import ArchiveXPreflight


def setup():
    db = sqlite3.connect(":memory:")
    ArchiveX(db)
    knowledge = ArchiveXKnowledgeStore(ArchiveXPromotionGate(db))
    return db, ArchiveXPreflight(db, knowledge)


def test_preflight_detects_missing_dependency_schema():
    _, preflight = setup()
    report = preflight.scan("alice", authorized=True)
    assert not report.healthy
    assert any(issue.code == "SCHEMA_MISSING" for issue in report.issues)


def test_preflight_requires_authorization():
    import pytest
    _, preflight = setup()
    with pytest.raises(PermissionError):
        preflight.scan("alice", authorized=False)


def test_preflight_is_deterministic():
    _, preflight = setup()
    first = preflight.scan("alice", authorized=True)
    second = preflight.scan("alice", authorized=True)
    assert first == second


def test_preflight_detects_orphaned_consumed_approval():
    db, preflight = setup()
    db.execute("""
        INSERT INTO archivex_promotions
        (owner, claim_id, verification_fingerprint, registry_fingerprint,
         approval_id, issued_at, receipt_id, consumed_at)
        VALUES ('alice', 'c1', 'a', 'b', 'review', 100, 'receipt', 101)
    """)
    db.commit()
    report = preflight.scan("alice", authorized=True)
    assert any(issue.code == "ORPHANED_APPROVAL" for issue in report.issues)


def test_preflight_is_owner_scoped():
    db, preflight = setup()
    db.execute("""
        INSERT INTO archivex_promotions
        (owner, claim_id, verification_fingerprint, registry_fingerprint,
         approval_id, issued_at, receipt_id, consumed_at)
        VALUES ('bob', 'c1', 'a', 'b', 'review', 100, 'receipt', 101)
    """)
    db.commit()
    report = preflight.scan("alice", authorized=True)
    assert not any(issue.code == "ORPHANED_APPROVAL" for issue in report.issues)
