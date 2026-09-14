import pytest

from core.evidence_registry import EvidenceRegistry, EvidenceRegistryIntegrityError
from core.truth_verifier import EvidenceItem, EvidenceKind
from core.verified_curiosity import VerifiedCuriosityEngine


def _item(source="study-a", *, quality=1.0, supports=True):
    return EvidenceItem(
        source_id=source,
        locator=f"doi:{source}#result",
        kind=EvidenceKind.PRIMARY_EMPIRICAL,
        supports=supports,
        independence_group="lab-a",
        quality=quality,
        reproducible=True,
        peer_reviewed=True,
        primary=True,
        provenance_verified=True,
        preregistered=True,
        data_available=True,
        code_available=True,
        sample_size=500,
        uncertainty_reported=True,
    )


def test_unbound_legacy_evidence_is_historical_but_not_truth_eligible(tmp_path):
    registry = EvidenceRegistry(tmp_path)
    claim = "System A decreases measured latency by 10 percent."
    item = _item()
    record = registry.register(claim, item)
    assert record.citation_bound is False
    assert registry.evidence_for(claim) == ()
    assert registry.evidence_for(claim, citation_bound_only=False) == (item,)
    stats = registry.stats()
    assert stats["unbound_records"] == 1
    assert stats["active_citation_bound_records"] == 0
    assert stats["truth_eligible_default"] is True


def test_exact_legacy_record_can_be_upgraded_once_with_citation_attestation(tmp_path):
    registry = EvidenceRegistry(tmp_path)
    claim = "System A decreases measured latency by 10 percent."
    item = _item()
    first = registry.register(claim, item)
    upgraded = registry.register(claim, item, citation_binding_attestation_sha256="a" * 64)
    assert upgraded.id == first.id
    assert upgraded.citation_bound is True
    assert upgraded.citation_binding_attestation_sha256 == "a" * 64
    assert registry.evidence_for(claim) == (item,)

    # Once the immutable evidence record is citation-bound, another attestation
    # cannot silently rewrite the provenance proof.
    with pytest.raises(EvidenceRegistryIntegrityError):
        registry.register(claim, item, citation_binding_attestation_sha256="b" * 64)


def test_same_evidence_identity_cannot_change_material_payload(tmp_path):
    registry = EvidenceRegistry(tmp_path)
    claim = "System A decreases measured latency by 10 percent."
    registry.register(claim, _item(quality=0.8))
    with pytest.raises(EvidenceRegistryIntegrityError):
        registry.register(claim, _item(quality=1.0))


def test_accept_finding_rejects_strong_raw_evidence_without_citation_binding(tmp_path):
    engine = VerifiedCuriosityEngine(tmp_path)
    claim = "System B decreases measured latency by 12 percent."
    engine.observe_prompt("latency verification")
    inquiry = engine.next_inquiry(); assert inquiry is not None
    raw = {
        "source_id": "study-a", "source": "study-a", "locator": "doi:study-a#result",
        "kind": "primary_empirical", "supports": True, "independence_group": "lab-a",
        "quality": 1.0, "reproducible": True, "peer_reviewed": True, "primary": True,
        "provenance_verified": True, "preregistered": True, "data_available": True,
        "code_available": True, "sample_size": 500, "uncertainty_reported": True,
    }
    replication = {**raw, "source_id": "study-b", "source": "study-b", "locator": "doi:study-b#result",
                   "kind": "replication", "independence_group": "lab-b"}
    record = engine.accept_finding(inquiry, {
        "summary": "Evidence intentionally lacks inspectable citation bindings.",
        "claims": [claim], "falsifiable": {claim: True},
        "claim_evidence": {claim: [raw, replication]},
    })
    assert record.claims == ()
    assert engine.truth_ledger.authoritative(claim) is False
    assert engine.evidence_registry.stats()["citation_bound_records"] == 0


def test_reverification_does_not_consume_unbound_registry_records(tmp_path):
    registry = EvidenceRegistry(tmp_path / "evidence")
    claim = "System C decreases measured latency by 7 percent."
    registry.register(claim, _item("legacy-a"))
    registry.register(claim, EvidenceItem(
        **{**_item("legacy-b").__dict__} if hasattr(_item("legacy-b"), "__dict__") else {
            "source_id": "legacy-b", "locator": "doi:legacy-b#result", "kind": EvidenceKind.REPLICATION,
            "supports": True, "independence_group": "lab-b", "quality": 1.0, "reproducible": True,
            "peer_reviewed": True, "primary": True, "provenance_verified": True, "preregistered": True,
            "data_available": True, "code_available": True, "sample_size": 500, "uncertainty_reported": True,
        }
    ))
    engine = VerifiedCuriosityEngine(tmp_path)
    result = engine.reverify_claim(claim)
    assert result["authoritative"] is False
    assert result["state"] != "verified"
    assert result["independence"]["raw_sources"] == 0
