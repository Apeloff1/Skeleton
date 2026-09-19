"""Provider attestation, release safety case, evidence, and gate tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.shells.ai.diagnostics import AIDiagnosticsReport
from skeleton.shells.ai.eval_runner import AIEvalCaseResult, AIEvalRun
from skeleton.shells.ai.model_port import ModelCapabilities
from skeleton.shells.ai.provider_attestation import (
    AttestationRequirement,
    ProviderAttestation,
    ProviderAttestationVerifier,
)
from skeleton.shells.ai.red_team import AIRedTeamResult
from skeleton.shells.ai.regression import RegressionComparison
from skeleton.shells.ai.release_evidence import ReleaseEvidenceBuilder
from skeleton.shells.ai.release_gate import AIReleaseGate, ReleaseGateDecision
from skeleton.shells.ai.safety_case import (
    AISafetyCaseBuilder,
    SafetyCasePolicy,
    SafetyCaseState,
)


def fp(char):
    return char * 64


def attestation(**changes):
    values = dict(
        provider_id="provider",
        model_id="model",
        model_version="2026-09",
        adapter_version="1",
        capabilities=ModelCapabilities(
            structured_output=True,
            tool_use=True,
            critique=True,
            parallel_candidates=True,
            max_input_bytes=10000,
            max_output_bytes=10000,
        ),
        protocol_versions=(1,),
        tool_catalog_digest=fp("a"),
    )
    values.update(changes)
    return ProviderAttestation(**values)


def attestation_report(ok=True):
    from skeleton.shells.ai.provider_attestation import AttestationReport
    return AttestationReport(ok, () if ok else ("bad",))


def eval_run(passed=True):
    result = AIEvalCaseResult(
        "c",
        passed,
        () if passed else ("failed",),
        fp("b"),
        1,
        False,
        1,
    )
    return AIEvalRun("dataset", 1, fp("c"), "model", (result,))


def red_team(passed=True):
    return (
        AIRedTeamResult(
            "red",
            passed,
            ("command_constraint",) if passed else (),
            () if passed else ("command_constraint",),
        ),
    )


def diagnostics(errors=0, warnings=0):
    from skeleton.shells.ai.diagnostics import AIDiagnosticFinding, AIDiagnosticSeverity

    findings = []
    findings.extend(
        AIDiagnosticFinding(AIDiagnosticSeverity.ERROR, f"e{i}", "error")
        for i in range(errors)
    )
    findings.extend(
        AIDiagnosticFinding(AIDiagnosticSeverity.WARNING, f"w{i}", "warning")
        for i in range(warnings)
    )
    return AIDiagnosticsReport(tuple(findings))


def test_provider_attestation_digest_stable():
    item = attestation()
    assert len(item.digest) == 64
    assert item.digest == item.digest


def test_provider_attestation_requires_protocols():
    with pytest.raises(ValueError):
        attestation(protocol_versions=())


def test_provider_attestation_tool_digest_length():
    with pytest.raises(ValueError):
        attestation(tool_catalog_digest="short")


def test_attestation_verifier_happy_path():
    report = ProviderAttestationVerifier().inspect(
        attestation(),
        AttestationRequirement(
            require_critique=True,
            require_parallel_candidates=True,
            min_input_bytes=1000,
            min_output_bytes=1000,
            protocol_version=1,
        ),
        expected_tool_catalog_digest=fp("a"),
    )
    assert report.compatible


def test_attestation_missing_structured_output():
    item = attestation(
        capabilities=ModelCapabilities(
            structured_output=False,
            tool_use=True,
        )
    )
    report = ProviderAttestationVerifier().inspect(
        item,
        AttestationRequirement(),
        expected_tool_catalog_digest=fp("a"),
    )
    assert not report.compatible
    assert "structured output" in report.reasons[0]


def test_attestation_missing_tool_use():
    item = attestation(
        capabilities=ModelCapabilities(
            structured_output=True,
            tool_use=False,
        )
    )
    report = ProviderAttestationVerifier().inspect(
        item,
        AttestationRequirement(),
        expected_tool_catalog_digest=fp("a"),
    )
    assert not report.compatible


def test_attestation_missing_protocol():
    report = ProviderAttestationVerifier().inspect(
        attestation(protocol_versions=(2,)),
        AttestationRequirement(protocol_version=1),
        expected_tool_catalog_digest=fp("a"),
    )
    assert not report.compatible


def test_attestation_tool_digest_mismatch():
    report = ProviderAttestationVerifier().inspect(
        attestation(),
        AttestationRequirement(),
        expected_tool_catalog_digest=fp("9"),
    )
    assert not report.compatible


def test_attestation_byte_capacity():
    item = attestation(
        capabilities=ModelCapabilities(
            max_input_bytes=100,
            max_output_bytes=100,
        )
    )
    report = ProviderAttestationVerifier().inspect(
        item,
        AttestationRequirement(
            min_input_bytes=101,
            min_output_bytes=101,
        ),
        expected_tool_catalog_digest=fp("a"),
    )
    assert len(report.reasons) == 2


def test_safety_case_pass():
    case = AISafetyCaseBuilder().build(
        diagnostics=diagnostics(),
        eval_run=eval_run(True),
        red_team=red_team(True),
        attestation=attestation_report(True),
    )
    assert case.state is SafetyCaseState.PASS
    assert case.deployable


def test_safety_case_blocks_diagnostics_error():
    case = AISafetyCaseBuilder().build(
        diagnostics=diagnostics(errors=1),
        eval_run=eval_run(True),
        red_team=red_team(True),
        attestation=attestation_report(True),
    )
    assert case.state is SafetyCaseState.BLOCK


def test_safety_case_blocks_eval_failure():
    case = AISafetyCaseBuilder().build(
        diagnostics=diagnostics(),
        eval_run=eval_run(False),
        red_team=red_team(True),
        attestation=attestation_report(True),
    )
    assert case.state is SafetyCaseState.BLOCK


def test_safety_case_blocks_red_team_failure():
    case = AISafetyCaseBuilder().build(
        diagnostics=diagnostics(),
        eval_run=eval_run(True),
        red_team=red_team(False),
        attestation=attestation_report(True),
    )
    assert case.state is SafetyCaseState.BLOCK
    assert case.red_team_failures == ("red",)


def test_safety_case_requires_attestation_by_default():
    case = AISafetyCaseBuilder().build(
        diagnostics=diagnostics(),
        eval_run=eval_run(True),
        red_team=red_team(True),
        attestation=None,
    )
    assert case.state is SafetyCaseState.BLOCK


def test_safety_case_can_allow_missing_attestation_by_policy():
    builder = AISafetyCaseBuilder(
        SafetyCasePolicy(require_provider_attestation=False)
    )
    case = builder.build(
        diagnostics=diagnostics(),
        eval_run=eval_run(True),
        red_team=red_team(True),
    )
    assert case.deployable


def test_safety_case_regression_blocks():
    regression = RegressionComparison(
        0.5,
        1.0,
        -0.5,
        ("c",),
        (),
    )
    case = AISafetyCaseBuilder().build(
        diagnostics=diagnostics(),
        eval_run=eval_run(True),
        red_team=red_team(True),
        attestation=attestation_report(True),
        regression=regression,
    )
    assert case.state is SafetyCaseState.BLOCK


def test_safety_case_warning_can_require_review():
    builder = AISafetyCaseBuilder(
        SafetyCasePolicy(allow_diagnostic_warnings=False)
    )
    case = builder.build(
        diagnostics=diagnostics(warnings=1),
        eval_run=eval_run(True),
        red_team=red_team(True),
        attestation=attestation_report(True),
    )
    assert case.state is SafetyCaseState.REVIEW
    assert not case.deployable


def release_evidence(case):
    return ReleaseEvidenceBuilder().build(
        release_id="r",
        code_revision="abc123",
        policy_fingerprint=fp("p"),
        tool_catalog_digest=fp("t"),
        effect_digest=fp("e"),
        eval_dataset_digest=fp("d"),
        eval_run_payload=eval_run(True).to_dict(),
        provider_attestation=attestation(),
        safety_case=case,
        workspace_manifest_digest=fp("w"),
    )


def test_release_evidence_digest_stable():
    case = AISafetyCaseBuilder().build(
        diagnostics=diagnostics(),
        eval_run=eval_run(True),
        red_team=red_team(True),
        attestation=attestation_report(True),
    )
    evidence = release_evidence(case)
    assert len(evidence.digest) == 64
    assert evidence.digest == evidence.digest
    assert evidence.deployable


def test_release_gate_allows_matching_evidence():
    case = AISafetyCaseBuilder().build(
        diagnostics=diagnostics(),
        eval_run=eval_run(True),
        red_team=red_team(True),
        attestation=attestation_report(True),
    )
    evidence = release_evidence(case)
    result = AIReleaseGate().inspect(
        evidence,
        expected_policy_fingerprint=fp("p"),
        expected_tool_catalog_digest=fp("t"),
        expected_effect_digest=fp("e"),
        expected_code_revision="abc123",
    )
    assert result.decision is ReleaseGateDecision.ALLOW


@pytest.mark.parametrize(
    "kwargs,phrase",
    [
        ({"expected_policy_fingerprint": fp("9")}, "policy"),
        ({"expected_tool_catalog_digest": fp("9")}, "tool"),
        ({"expected_effect_digest": fp("9")}, "effect"),
        ({"expected_code_revision": "other"}, "code"),
    ],
)
def test_release_gate_denies_mismatch(kwargs, phrase):
    case = AISafetyCaseBuilder().build(
        diagnostics=diagnostics(),
        eval_run=eval_run(True),
        red_team=red_team(True),
        attestation=attestation_report(True),
    )
    result = AIReleaseGate().inspect(release_evidence(case), **kwargs)
    assert not result.allowed
    assert any(phrase in reason for reason in result.reasons)


def test_release_gate_denies_blocked_safety_case():
    blocked = AISafetyCaseBuilder().build(
        diagnostics=diagnostics(errors=1),
        eval_run=eval_run(True),
        red_team=red_team(True),
        attestation=attestation_report(True),
    )
    result = AIReleaseGate().inspect(release_evidence(blocked))
    assert not result.allowed


def test_release_gate_require_raises():
    blocked = AISafetyCaseBuilder().build(
        diagnostics=diagnostics(errors=1),
        eval_run=eval_run(True),
        red_team=red_team(True),
        attestation=attestation_report(True),
    )
    with pytest.raises(RuntimeError):
        AIReleaseGate().require(release_evidence(blocked))
