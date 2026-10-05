"""Updating a document body must not wipe tags, and a negative limit is not the tail."""

import pytest

from skeleton.intelligence.knowledge_base import KnowledgeBase, KnowledgeError
from skeleton.knowledge.store import KnowledgeStore, VerificationState


def test_put_keeps_tags_when_the_update_omits_them(tmp_path) -> None:
    base = KnowledgeBase(root=tmp_path)
    base.put("runbook", "Restart API", "stop then start", tags=["ops"], subsystems=["api"])
    updated = base.put("runbook", "Restart API", "stop, wait, start")
    assert updated.version == 2
    assert updated.tags == ["ops"]
    assert updated.subsystems == ["api"]
    cleared = base.put("runbook", "Restart API", "stop, wait, start", tags=[], subsystems=[])
    assert cleared.tags == []
    assert cleared.subsystems == []


def test_negative_search_limit_is_rejected(tmp_path) -> None:
    base = KnowledgeBase(root=tmp_path)
    base.put("a", "Alpha guide", "alpha details", tags=["guide"])
    with pytest.raises(ValueError):
        base.search("alpha", limit=-1)
    assert base.search("alpha", limit=0) == []


def test_put_projects_deterministic_evidence_bound_claim(tmp_path) -> None:
    claims = KnowledgeStore()
    base = KnowledgeBase(root=tmp_path, claim_store=claims, scope_key="tenant-a/project-a")
    doc = base.put("runbook", "Restart API", "stop then start", tags=["ops"], subsystems=["api"])
    view = claims.query(
        scope_key="tenant-a/project-a",
        subject="knowledge-document:runbook",
        predicate="revision",
    )
    assert len(view.claims) == 1
    claim = view.claims[0]
    assert claim.claim_id == "knowledge-base:runbook:v1"
    assert claim.verification is VerificationState.CORROBORATED
    assert claim.confidence == 1.0
    assert len(claim.evidence) == 1
    assert claim.evidence[0].digest == claim.value_digest
    assert doc.version == 1


def test_document_revision_is_append_only_in_claim_store(tmp_path) -> None:
    claims = KnowledgeStore()
    base = KnowledgeBase(root=tmp_path, claim_store=claims, scope_key="tenant-a/project-a")
    base.put("runbook", "Restart API", "stop then start")
    base.put("runbook", "Restart API", "stop wait then start")
    view = claims.query(
        scope_key="tenant-a/project-a",
        subject="knowledge-document:runbook",
        predicate="revision",
    )
    assert [claim.claim_id for claim in view.claims] == [
        "knowledge-base:runbook:v1",
        "knowledge-base:runbook:v2",
    ]
    assert view.claims[0].value_digest != view.claims[1].value_digest


def test_claim_projection_configuration_fails_closed(tmp_path) -> None:
    with pytest.raises(KnowledgeError, match="configured together"):
        KnowledgeBase(root=tmp_path, claim_store=KnowledgeStore())
    with pytest.raises(KnowledgeError, match="configured together"):
        KnowledgeBase(root=tmp_path, scope_key="tenant-a/project-a")
