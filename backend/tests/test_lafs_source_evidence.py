"""Quarantine, review, provenance and retrieval are bound to exact source evidence."""
import hashlib
import time
import pytest
from gameforge.lafs.source_evidence import _canonical, validate_evidence, online_enabled
from gameforge.lafs.lafs_engine import LeverArchFileSystem, CabinetConflict
from tests.test_lafs_evidence_custody import Collection


def evidence(extract="Untrusted text"):
    fields = {"title": "Game design", "extract": extract,
              "source_url": "https://en.wikipedia.org/wiki/Game_design", "revision": 100}
    return {**fields, "response_sha256": "f"*64,
            "evidence_sha256": hashlib.sha256(_canonical(fields)).hexdigest(),
            "fetched_at": time.time()}


def test_opt_in_and_digest_admission(monkeypatch):
    monkeypatch.delenv("LAFS_ONLINE_LEARNING", raising=False)
    assert not online_enabled()
    record = evidence()
    assert validate_evidence(record) == record
    with pytest.raises(ValueError):
        validate_evidence({**record, "extract": "modified"})
    with pytest.raises(ValueError):
        validate_evidence({**record, "source_url": "https://example.org/wiki/Game_design"})


def test_quarantine_is_idempotent_and_review_bound(monkeypatch):
    store = Collection()
    ledger = LeverArchFileSystem()
    monkeypatch.setattr(ledger, "_col", lambda: store)
    record = evidence("dragon design")
    first = ledger.ingest_external("Meta", "Discovery", record)
    second = ledger.ingest_external("Narrative", "Lore", record)
    sid = first["sheet"]["id"]
    assert first["created"] and not second["created"]
    assert second["sheet"]["id"] == sid
    assert ledger.probability_search("dragon") == []
    assert ledger.reinforce(sid, True) is None
    assert ledger.external_queue()[0]["id"] == sid
    with pytest.raises(CabinetConflict):
        ledger.external_review(sid, "0"*64, "approved", "admin", "review")
    approved = ledger.external_review(sid, record["evidence_sha256"], "approved", "admin", "verified source")
    assert approved["evidence_status"] == "approved"
    assert ledger.probability_search("dragon")[0]["id"] == sid
    with pytest.raises(CabinetConflict):
        ledger.external_review(sid, record["evidence_sha256"], "rejected", "admin", "second review")


def test_legacy_sources_are_not_canonical(monkeypatch):
    store = Collection()
    ledger = LeverArchFileSystem()
    monkeypatch.setattr(ledger, "_col", lambda: store)
    old = ledger.add_sheet("Meta", "Discovery", {"extract": "dragon", "provenance": "wikipedia_rest_v1"},
                           author="Jeeves-Sweep")
    assert old.evidence_status == "legacy_unverified"
    assert ledger.probability_search("dragon") == []


def test_approved_source_is_revalidated_and_can_be_revoked(monkeypatch):
    store = Collection()
    ledger = LeverArchFileSystem()
    monkeypatch.setattr(ledger, "_col", lambda: store)
    record = evidence("dragon lore")
    sid = ledger.ingest_external("Meta", "Discovery", record)["sheet"]["id"]
    ledger.external_review(sid, record["evidence_sha256"], "approved", "operator", "review")
    assert ledger.external_queue(status="approved")[0]["id"] == sid
    revoked = ledger.external_review(sid, record["evidence_sha256"], "revoked", "operator", "new evidence")
    assert revoked["evidence_status"] == "revoked"
    assert revoked["provenance"]["prior_review"]["review_status"] == "approved"
    assert ledger.probability_search("dragon") == []
    assert ledger.stats()["excluded_sheets"] == 1
    # Deliberate corruption of source bytes after a review cannot enter RAG.
    store.doc["sheets"][sid]["payload"]["extract"] = "mutated dragon"
    assert ledger.external_queue(status="integrity_hold")[0]["id"] == sid
    assert ledger.probability_search("dragon") == []
