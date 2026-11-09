"""Model attestation registry and signed AI release registry tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.shells.ai.diagnostics import AIDiagnosticsReport
from skeleton.shells.ai.eval_runner import AIEvalCaseResult, AIEvalRun
from skeleton.shells.ai.model_port import ModelCapabilities
from skeleton.shells.ai.model_registry import AIModelRegistry, ModelRegistryConflict
from skeleton.shells.ai.provider_attestation import ProviderAttestation
from skeleton.shells.ai.red_team import AIRedTeamResult
from skeleton.shells.ai.release_evidence import ReleaseEvidenceBuilder
from skeleton.shells.ai.release_registry import (
    AIReleaseRegistry,
    ReleaseRegistryConflict,
)
from skeleton.shells.ai.safety_case import AISafetyCaseBuilder
from skeleton.shells.ai.signed_artifact import ArtifactSignatureError, ArtifactSigner


def fp(char):
    return char * 64


def attestation(version="1", *, model_id="model", provider_id="provider"):
    return ProviderAttestation(
        provider_id=provider_id,
        model_id=model_id,
        model_version=version,
        adapter_version="adapter-1",
        capabilities=ModelCapabilities(
            structured_output=True,
            tool_use=True,
            critique=True,
        ),
        protocol_versions=(1,),
        tool_catalog_digest=fp("t"),
    )


def safety_case(ok=True):
    from skeleton.shells.ai.diagnostics import AIDiagnosticFinding, AIDiagnosticSeverity

    diagnostics = (
        AIDiagnosticsReport(())
        if ok
        else AIDiagnosticsReport(
            (AIDiagnosticFinding(AIDiagnosticSeverity.ERROR, "x", "bad"),)
        )
    )
    run = AIEvalRun(
        "d",
        1,
        fp("d"),
        "model",
        (
            AIEvalCaseResult(
                "c",
                True,
                (),
                fp("p"),
                1,
                False,
                1,
            ),
        ),
    )
    red = (AIRedTeamResult("r", True, ("x",), ()),)
    from skeleton.shells.ai.provider_attestation import AttestationReport
    return AISafetyCaseBuilder().build(
        diagnostics=diagnostics,
        eval_run=run,
        red_team=red,
        attestation=AttestationReport(True, ()),
    )


def evidence(release_id="r", *, ok=True):
    run = AIEvalRun(
        "d",
        1,
        fp("d"),
        "model",
        (
            AIEvalCaseResult(
                "c",
                True,
                (),
                fp("p"),
                1,
                False,
                1,
            ),
        ),
    )
    return ReleaseEvidenceBuilder().build(
        release_id=release_id,
        code_revision="abc",
        policy_fingerprint=fp("q"),
        tool_catalog_digest=fp("t"),
        effect_digest=fp("e"),
        eval_dataset_digest=fp("d"),
        eval_run_payload=run.to_dict(),
        provider_attestation=attestation(),
        safety_case=safety_case(ok),
    )


def test_model_registry_first_revision():
    registry = AIModelRegistry()
    item = registry.register(attestation())
    assert item.revision == 1
    assert item.active
    assert item.registry_id == "provider:model"


def test_model_registry_same_attestation_idempotent():
    registry = AIModelRegistry()
    first = registry.register(attestation())
    second = registry.register(attestation())
    assert first == second


def test_model_registry_new_version_increments_revision():
    registry = AIModelRegistry()
    registry.register(attestation("1"))
    second = registry.register(attestation("2"), expected_revision=1)
    assert second.revision == 2
    assert second.attestation.model_version == "2"


def test_model_registry_stale_revision_conflict():
    registry = AIModelRegistry()
    registry.register(attestation("1"))
    registry.register(attestation("2"), expected_revision=1)
    with pytest.raises(ModelRegistryConflict):
        registry.register(attestation("3"), expected_revision=1)


def test_model_registry_deactivate_activate():
    registry = AIModelRegistry()
    first = registry.register(attestation())
    off = registry.deactivate(first.registry_id, expected_revision=1)
    assert not off.active
    on = registry.activate(first.registry_id, expected_revision=2)
    assert on.active
    assert on.revision == 3


def test_model_registry_active_filters():
    registry = AIModelRegistry()
    one = registry.register(attestation(model_id="one"))
    two = registry.register(attestation(model_id="two"))
    registry.deactivate(one.registry_id)
    assert [item.registry_id for item in registry.active()] == [two.registry_id]


def test_model_registry_capacity():
    registry = AIModelRegistry(max_models=1)
    registry.register(attestation(model_id="one"))
    with pytest.raises(RuntimeError):
        registry.register(attestation(model_id="two"))


def test_release_registry_registers_signed_evidence():
    signer = ArtifactSigner("key", b"k" * 32)
    registry = AIReleaseRegistry(signer)
    item = registry.register(evidence())
    assert item.revision == 1
    assert not item.active
    signer.verify(item.signature)


def test_release_registry_same_evidence_idempotent():
    registry = AIReleaseRegistry(ArtifactSigner("key", b"k" * 32))
    first = registry.register(evidence())
    second = registry.register(evidence())
    assert first == second


def test_release_registry_changed_evidence_increments_revision():
    registry = AIReleaseRegistry(ArtifactSigner("key", b"k" * 32))
    first = registry.register(evidence())
    changed = replace(
        first.evidence,
        code_revision="def",
    )
    second = registry.register(changed, expected_revision=1)
    assert second.revision == 2
    assert second.evidence.code_revision == "def"


def test_release_registry_revision_conflict():
    registry = AIReleaseRegistry(ArtifactSigner("key", b"k" * 32))
    registry.register(evidence())
    changed = replace(evidence(), code_revision="def")
    registry.register(changed, expected_revision=1)
    with pytest.raises(ReleaseRegistryConflict):
        registry.register(
            replace(evidence(), code_revision="ghi"),
            expected_revision=1,
        )


def test_release_registry_activate_deployable():
    registry = AIReleaseRegistry(ArtifactSigner("key", b"k" * 32))
    registered = registry.register(evidence())
    active = registry.activate("r", expected_revision=registered.revision)
    assert active.active
    assert active.revision == 2


def test_release_registry_cannot_activate_blocked_release():
    registry = AIReleaseRegistry(ArtifactSigner("key", b"k" * 32))
    registry.register(evidence(ok=False))
    with pytest.raises(RuntimeError, match="non-deployable"):
        registry.activate("r")


def test_release_registry_detects_signature_tamper():
    signer = ArtifactSigner("key", b"k" * 32)
    registry = AIReleaseRegistry(signer)
    item = registry.register(evidence())
    history = registry._items["r"]
    history[-1] = replace(
        item,
        signature=replace(item.signature, signature="0" * 64),
    )
    with pytest.raises(ArtifactSignatureError):
        registry.activate("r")


def test_release_registry_deactivate():
    registry = AIReleaseRegistry(ArtifactSigner("key", b"k" * 32))
    registry.register(evidence())
    active = registry.activate("r")
    off = registry.deactivate("r", expected_revision=active.revision)
    assert not off.active
