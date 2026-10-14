from dataclasses import replace

import pytest

from skeleton.ai.runtime.deferred.card_systems import (
    AgentCard, CardClaim, CardRegistry, ClaimKind, DatasetCard, EvidenceRef,
    ModelCard, ToolCard,
)

D = "a" * 64
E = EvidenceRef("eval-1", D, "eval@abc123")


def test_model_card_separates_measured_claims_and_binds_evidence():
    card = ModelCard("m1", D, "eval@abc123", (CardClaim("accuracy", "0.91", ClaimKind.MEASURED, ("eval-1",)),), (E,), ("not validated for medicine",))
    assert len(card.identity) == 64
    assert card.identity == replace(card).identity


def test_model_card_rejects_measurement_without_evidence_and_missing_limitation():
    with pytest.raises(ValueError, match="measured claims"):
        CardClaim("accuracy", "0.91", ClaimKind.MEASURED)
    with pytest.raises(ValueError, match="limitations"):
        ModelCard("m1", D, "eval@abc123", (), (), ())


def test_model_card_rejects_unknown_evidence_reference():
    with pytest.raises(ValueError, match="unknown evidence"):
        ModelCard("m1", D, "eval@abc123", (CardClaim("x", "x", ClaimKind.MEASURED, ("missing",)),), (E,), ("limit",))


def test_dataset_card_binds_immutable_fingerprint_and_discloses_unknowns():
    card = DatasetCard("ds@v3", D, ("source-a",), ("source-b:rights",), ("source-c",), ("age",), (E,))
    assert len(card.identity) == 64
    assert card.unknown_provenance == ("source-c",)


def test_dataset_card_rejects_bad_digest_and_duplicate_disclosures():
    with pytest.raises(ValueError, match="sha256"):
        DatasetCard("ds", "latest", (), (), (), (), ())
    with pytest.raises(ValueError, match="unique"):
        DatasetCard("ds", D, ("a", "a"), (), (), (), ())


def test_tool_card_is_disclosure_only_and_security_review_bound():
    card = ToolCard("search@4", D, "runtime-tools", ("read:web",), ("untrusted output",), E)
    assert len(card.identity) == 64
    assert card.authority_grants == ()


def test_tool_card_cannot_smuggle_authority():
    with pytest.raises(ValueError, match="cannot grant authority"):
        ToolCard("shell@1", D, "runtime-tools", ("execute",), ("side effects",), E, ("admin",))


def test_tool_card_requires_risk_disclosure():
    with pytest.raises(ValueError, match="disclose risks"):
        ToolCard("search@4", D, "runtime-tools", ("read:web",), (), E)


def test_agent_card_distinguishes_default_from_optional_delegation():
    card = AgentCard("secretary@9", D, ("propose",), ("write:task-bound",), E, (CardClaim("quality", "passed", ClaimKind.MEASURED, ("eval-1",)),))
    assert card.default_authority == ("propose",)
    assert card.optional_delegated_grants == ("write:task-bound",)


def test_agent_card_rejects_authority_ambiguity():
    with pytest.raises(ValueError, match="must be distinct"):
        AgentCard("worker@2", D, ("write",), ("write",), E, ())


def test_agent_measured_claim_must_bind_exact_evaluation():
    other = CardClaim("quality", "passed", ClaimKind.MEASURED, ("other-eval",))
    with pytest.raises(ValueError, match="unknown evidence"):
        AgentCard("worker@2", D, ("execute",), (), E, (other,))


def test_registry_is_idempotent_and_fail_closed_on_silent_replacement():
    registry = CardRegistry()
    card = ToolCard("search@4", D, "runtime-tools", ("read:web",), ("untrusted output",), E)
    first = registry.publish("tool", "search@4", card)
    assert registry.publish("tool", "search@4", card) == first
    changed = ToolCard("search@4", "b" * 64, "runtime-tools", ("read:web",), ("untrusted output",), E)
    with pytest.raises(ValueError, match="explicit versioned"):
        registry.publish("tool", "search@4", changed)


def test_identity_changes_when_evidence_revision_changes():
    a = ModelCard("m1", D, "eval@abc123", (CardClaim("q", "ok", ClaimKind.MEASURED, ("eval-1",)),), (E,), ("limit",))
    e2 = EvidenceRef("eval-1", D, "eval@def456")
    b = ModelCard("m1", D, "eval@def456", (CardClaim("q", "ok", ClaimKind.MEASURED, ("eval-1",)),), (e2,), ("limit",))
    assert a.identity != b.identity
