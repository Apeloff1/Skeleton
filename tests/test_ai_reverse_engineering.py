from __future__ import annotations

import pytest

from skeleton.ai.research.model_internals.reverse_engineering import (
    ArtifactProvenance,
    AuthorizationScope,
    ProbeCase,
    ProbeKind,
    ProvenanceGate,
    ReverseEngineeringError,
    ReverseEngineeringSession,
    compare_bundles,
)
from skeleton.ai.research.model_internals.reverse_engineering.provenance import RightsBasis


def _features(output):
    if isinstance(output, dict) and output.get("stateful"):
        yield "stateful"
    if isinstance(output, dict) and output.get("tool"):
        yield "tool_boundary"


def test_reverse_engineering_requires_explicit_target_authorization():
    session = ReverseEngineeringSession(
        authorization=AuthorizationScope(target_ids=("owned-a",), purpose="regression"),
    )
    with pytest.raises(ReverseEngineeringError, match="outside authorization scope"):
        session.inspect(
            target_id="unowned-b",
            target=lambda value: value,
            probes=(ProbeCase("p1", ProbeKind.CUSTOM, {"x": 1}),),
        )


def test_evidence_is_deterministic_and_does_not_persist_raw_probe_payload():
    session = ReverseEngineeringSession(
        authorization=AuthorizationScope(target_ids=("owned-a",), purpose="fingerprint"),
    )
    probes = (
        ProbeCase("det-1", ProbeKind.DETERMINISM, {"secretish": "ephemeral input"}),
    )
    first = session.inspect(target_id="owned-a", target=lambda value: {"ok": len(value)}, probes=probes, repeats=2)
    second = session.inspect(target_id="owned-a", target=lambda value: {"ok": len(value)}, probes=probes, repeats=2)
    assert first.report_digest == second.report_digest
    assert first.evidence.digest == second.evidence.digest
    wire = str(first.evidence.as_dict())
    assert "ephemeral input" not in wire
    assert len(first.evidence.observations[0].input_digest) == 64


def test_repeatable_probe_can_support_observable_repeatability_claim():
    session = ReverseEngineeringSession(
        authorization=AuthorizationScope(target_ids=("owned-a",), purpose="repeatability"),
    )
    report = session.inspect(
        target_id="owned-a",
        target=lambda value: {"stable": value["n"] * 2},
        probes=(ProbeCase("det-1", ProbeKind.DETERMINISM, {"n": 3}),),
        repeats=3,
    )
    claim = next(item for item in report.claims if item.claim_id == "observable.repeatability")
    assert claim.status == "supported"
    assert claim.promotable is True
    assert claim.evidence_probe_ids == ("det-1",)


def test_state_and_tool_features_create_evidence_bound_claims():
    session = ReverseEngineeringSession(
        authorization=AuthorizationScope(target_ids=("owned-a",), purpose="features"),
        feature_extractors=(_features,),
    )
    report = session.inspect(
        target_id="owned-a",
        target=lambda value: {"stateful": True, "tool": value.get("tool", False)},
        probes=(
            ProbeCase("state-1", ProbeKind.STATE, {"tool": False}),
            ProbeCase("tool-1", ProbeKind.TOOLING, {"tool": True}),
        ),
    )
    supported = {claim.claim_id for claim in report.supported_claims}
    assert "observable.statefulness" in supported
    assert "observable.tool_boundary" in supported


def test_differential_report_identifies_changed_output_for_shared_probe():
    auth = AuthorizationScope(target_ids=("left", "right"), purpose="differential")
    session = ReverseEngineeringSession(authorization=auth)
    probes = (ProbeCase("same-probe", ProbeKind.FORMAT, {"x": 2}),)
    left = session.inspect(target_id="left", target=lambda _: {"v": 1}, probes=probes)
    right = session.inspect(target_id="right", target=lambda _: {"v": 2}, probes=probes)
    findings = compare_bundles(left.evidence, right.evidence)
    assert len(findings) == 1
    assert findings[0].probe_id == "same-probe"
    assert findings[0].agreement_ratio == 0.0


def test_artifact_provenance_is_separately_authorized_and_fail_closed():
    provenance = ArtifactProvenance(
        artifact_id="local-model-card",
        source_uri="file:///owned/model-card.json",
        rights_basis=RightsBasis.OWNED,
    )
    blocked = ProvenanceGate(
        AuthorizationScope(target_ids=("owned-a",), purpose="black-box only"),
    )
    with pytest.raises(ReverseEngineeringError, match="artifact inspection is not authorized"):
        blocked.receipt(provenance)

    gate = ProvenanceGate(
        AuthorizationScope(
            target_ids=("owned-a",),
            purpose="owned artifact analysis",
            artifact_inspection=True,
        ),
    )
    receipt = gate.receipt(provenance)
    assert len(receipt) == 64

    credential_bearing = ArtifactProvenance(
        artifact_id="bad",
        source_uri="file:///owned/secrets.bin",
        rights_basis=RightsBasis.OWNED,
        contains_credentials=True,
    )
    with pytest.raises(ReverseEngineeringError, match="credential-bearing"):
        gate.admit(credential_bearing)
