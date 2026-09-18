"""AI release manager safety-gate and rollout integration tests."""

from __future__ import annotations

import pytest

from skeleton.shells.ai.diagnostics import AIDiagnosticsReport
from skeleton.shells.ai.eval_runner import AIEvalCaseResult, AIEvalRun
from skeleton.shells.ai.governance import AIShellGovernance
from skeleton.shells.ai.model_port import ModelCapabilities
from skeleton.shells.ai.policy import AIShellPolicy, AutonomyMode
from skeleton.shells.ai.policy_rollout import AIPolicyRolloutPhase
from skeleton.shells.ai.policy_store import AIPolicyStore
from skeleton.shells.ai.provider_attestation import AttestationReport, ProviderAttestation
from skeleton.shells.ai.red_team import AIRedTeamResult
from skeleton.shells.ai.release_evidence import ReleaseEvidenceBuilder
from skeleton.shells.ai.release_manager import AIReleaseManager
from skeleton.shells.ai.release_registry import AIReleaseRegistry
from skeleton.shells.ai.safety_case import AISafetyCaseBuilder
from skeleton.shells.ai.signed_artifact import ArtifactSigner


def fp(char):
    return char * 64


def attestation():
    return ProviderAttestation(
        "provider",
        "model",
        "1",
        "adapter",
        ModelCapabilities(),
        (1,),
        fp("t"),
    )


def run():
    return AIEvalRun(
        "dataset",
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


def safety(ok=True):
    from skeleton.shells.ai.diagnostics import AIDiagnosticFinding, AIDiagnosticSeverity
    diagnostics = (
        AIDiagnosticsReport(())
        if ok
        else AIDiagnosticsReport(
            (AIDiagnosticFinding(AIDiagnosticSeverity.ERROR, "bad", "bad"),)
        )
    )
    return AISafetyCaseBuilder().build(
        diagnostics=diagnostics,
        eval_run=run(),
        red_team=(AIRedTeamResult("r", True, ("x",), ()),),
        attestation=AttestationReport(True, ()),
    )


def evidence(policy, *, ok=True, release_id="r"):
    return ReleaseEvidenceBuilder().build(
        release_id=release_id,
        code_revision="abc",
        policy_fingerprint=policy.fingerprint,
        tool_catalog_digest=fp("t"),
        effect_digest=fp("e"),
        eval_dataset_digest=fp("d"),
        eval_run_payload=run().to_dict(),
        provider_attestation=attestation(),
        safety_case=safety(ok),
    )


def manager(base):
    governance = AIShellGovernance(AIPolicyStore(base))
    registry = AIReleaseRegistry(ArtifactSigner("key", b"k" * 32))
    return AIReleaseManager(registry, governance)


def test_release_manager_same_policy_no_rollout():
    base = AIShellPolicy()
    service = manager(base)
    prepared = service.prepare(evidence(base))
    assert prepared.rollout is None
    assert prepared.gate.allowed
    assert prepared.registered.release_id == "r"


def test_release_manager_target_policy_prepares_rollout():
    base = AIShellPolicy()
    target = AIShellPolicy(
        autonomy=AutonomyMode.LOW_RISK_AUTONOMOUS
    )
    service = manager(base)
    prepared = service.prepare(
        evidence(target),
        target_policy=target,
        canary_percent=25,
        rollout_reason="model release",
    )
    assert prepared.rollout is not None
    assert prepared.rollout.phase is AIPolicyRolloutPhase.PREPARED
    assert prepared.rollout.canary_percent == 25


def test_release_manager_target_policy_must_match_evidence():
    base = AIShellPolicy()
    target = AIShellPolicy(max_actions=31)
    service = manager(base)
    with pytest.raises(RuntimeError, match="target policy"):
        service.prepare(
            evidence(base),
            target_policy=target,
        )


def test_release_manager_without_target_requires_active_policy_match():
    base = AIShellPolicy()
    other = AIShellPolicy(max_actions=31)
    service = manager(base)
    with pytest.raises(RuntimeError, match="active policy"):
        service.prepare(evidence(other))


def test_release_manager_blocks_bad_safety_case():
    base = AIShellPolicy()
    service = manager(base)
    with pytest.raises(RuntimeError, match="safety case"):
        service.prepare(evidence(base, ok=False))


def test_release_manager_activate_signed_release():
    base = AIShellPolicy()
    service = manager(base)
    prepared = service.prepare(evidence(base))
    active = service.activate(prepared.registered.release_id)
    assert active.active
    service.registry.signer.verify(active.signature)


def test_release_manager_rollout_uses_release_scoped_id():
    base = AIShellPolicy()
    target = AIShellPolicy(max_actions=31)
    service = manager(base)
    prepared = service.prepare(
        evidence(target, release_id="2026-09"),
        target_policy=target,
    )
    assert prepared.rollout.rollout_id == "release:2026-09"


def test_release_manager_does_not_activate_on_prepare():
    base = AIShellPolicy()
    service = manager(base)
    prepared = service.prepare(evidence(base))
    assert not prepared.registered.active


def test_release_manager_registry_revision_is_signed():
    base = AIShellPolicy()
    service = manager(base)
    prepared = service.prepare(evidence(base))
    assert prepared.registered.signature.artifact_digest == prepared.registered.evidence.digest
