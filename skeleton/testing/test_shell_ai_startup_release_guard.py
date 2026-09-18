"""Signed release/channel startup enforcement tests."""

from __future__ import annotations

from dataclasses import replace
import sys

import pytest

from skeleton.shells.ai.catalog import AIToolCatalog
from skeleton.shells.ai.compiler import AIPlanCompiler
from skeleton.shells.ai.critic import AIPlanCritic
from skeleton.shells.ai.diagnostics import AIDiagnosticsReport, AIShellDiagnostics
from skeleton.shells.ai.distributed_state import InMemoryFencedStore
from skeleton.shells.ai.effects import EffectContract, EffectKind, EffectRegistry
from skeleton.shells.ai.eval_runner import AIEvalCaseResult, AIEvalRun
from skeleton.shells.ai.governance import AIShellGovernance
from skeleton.shells.ai.lifecycle import AIServicePhase
from skeleton.shells.ai.model_port import CallableAIModelPort, ModelCapabilities
from skeleton.shells.ai.orchestrator import AIShellOrchestrator
from skeleton.shells.ai.planner import AIPlanner
from skeleton.shells.ai.policy import AIShellPolicy
from skeleton.shells.ai.policy_store import AIPolicyStore
from skeleton.shells.ai.provider_attestation import AttestationReport, ProviderAttestation
from skeleton.shells.ai.red_team import AIRedTeamResult
from skeleton.shells.ai.release_channel import AIReleaseChannelStore
from skeleton.shells.ai.release_evidence import ReleaseEvidenceBuilder
from skeleton.shells.ai.release_registry import AIReleaseRegistry
from skeleton.shells.ai.router import AIToolRouter
from skeleton.shells.ai.safety_case import AISafetyCaseBuilder
from skeleton.shells.ai.service import AIShellService
from skeleton.shells.ai.signed_artifact import ArtifactSigner
from skeleton.shells.ai.startup_release import (
    AIStartupReleaseGuard,
    RuntimeReleaseExpectation,
)
from skeleton.shells.arguments import ArgumentPolicy
from skeleton.shells.commands import CommandCatalog, CommandDefinition
from skeleton.shells.executor import ShellExecutor
from skeleton.shells.registry import ExecutableSpec
from skeleton.shells.runner import ShellPolicy, ShellRunner
from skeleton.shells.shell_service import ShellService


def fp(char):
    return char * 64


def provider_attestation():
    return ProviderAttestation(
        "provider",
        "model",
        "2026",
        "adapter",
        ModelCapabilities(),
        (1,),
        fp("t"),
    )


def eval_run():
    return AIEvalRun(
        "dataset",
        1,
        fp("d"),
        "model",
        (
            AIEvalCaseResult(
                "case",
                True,
                (),
                fp("p"),
                1,
                False,
                1,
            ),
        ),
    )


def safety_case():
    return AISafetyCaseBuilder().build(
        diagnostics=AIDiagnosticsReport(()),
        eval_run=eval_run(),
        red_team=(AIRedTeamResult("red", True, ("x",), ()),),
        attestation=AttestationReport(True, ()),
    )


def evidence(policy, *, release_id="r", code_revision="code"):
    return ReleaseEvidenceBuilder().build(
        release_id=release_id,
        code_revision=code_revision,
        policy_fingerprint=policy.fingerprint,
        tool_catalog_digest=fp("t"),
        effect_digest=fp("e"),
        eval_dataset_digest=fp("d"),
        eval_run_payload=eval_run().to_dict(),
        provider_attestation=provider_attestation(),
        safety_case=safety_case(),
        workspace_manifest_digest=fp("w"),
    )


def release_environment(policy, *, code_revision="code"):
    signer = ArtifactSigner("release-key", b"k" * 32)
    registry = AIReleaseRegistry(signer)
    registered = registry.register(
        evidence(policy, code_revision=code_revision)
    )
    active = registry.activate(
        registered.release_id,
        expected_revision=registered.revision,
    )
    channels = AIReleaseChannelStore(InMemoryFencedStore())
    state = channels.from_release("production", active)
    channels.set(state)
    guard = AIStartupReleaseGuard(channels, registry)
    expectation = RuntimeReleaseExpectation(
        "production",
        code_revision,
        policy.fingerprint,
        fp("t"),
        fp("e"),
        provider_attestation_digest=provider_attestation().digest,
        workspace_manifest_digest=fp("w"),
    )
    return guard, expectation, registry, channels, active


def test_startup_release_guard_happy_path():
    policy = AIShellPolicy()
    guard, expectation, _, _, _ = release_environment(policy)
    report = guard.inspect(expectation)
    assert report.allowed
    assert report.channel_revision == 1
    assert report.release_id == "r"
    assert report.release_revision == 2
    assert len(report.evidence_digest) == 64


def test_startup_release_guard_missing_channel():
    policy = AIShellPolicy()
    registry = AIReleaseRegistry(ArtifactSigner("k", b"k" * 32))
    channels = AIReleaseChannelStore(InMemoryFencedStore())
    guard = AIStartupReleaseGuard(channels, registry)
    expectation = RuntimeReleaseExpectation(
        "production",
        "code",
        policy.fingerprint,
        fp("t"),
        fp("e"),
    )
    report = guard.inspect(expectation)
    assert not report.allowed
    assert "not assigned" in report.reasons[0]


@pytest.mark.parametrize(
    "field,value,phrase",
    [
        ("code_revision", "other", "code revision"),
        ("policy_fingerprint", fp("x"), "policy fingerprint"),
        ("tool_catalog_digest", fp("x"), "tool catalog"),
        ("effect_digest", fp("x"), "effect registry"),
        ("provider_attestation_digest", fp("x"), "provider attestation"),
        ("workspace_manifest_digest", fp("x"), "workspace manifest"),
    ],
)
def test_startup_release_guard_runtime_drift(field, value, phrase):
    policy = AIShellPolicy()
    guard, expectation, _, _, _ = release_environment(policy)
    changed = replace(expectation, **{field: value})
    report = guard.inspect(changed)
    assert not report.allowed
    assert any(phrase in reason for reason in report.reasons)


def test_startup_release_guard_unknown_release():
    policy = AIShellPolicy()
    guard, expectation, registry, channels, active = release_environment(policy)
    backend = channels.backend
    revision, state = channels.current("production")
    backend.compare_and_swap(
        channels.namespace,
        "production",
        expected_revision=revision,
        value=replace(state, release_id="missing"),
    )
    report = guard.inspect(expectation)
    assert not report.allowed
    assert any("unknown release" in reason for reason in report.reasons)


def test_startup_release_guard_inactive_release():
    policy = AIShellPolicy()
    guard, expectation, registry, channels, active = release_environment(policy)
    inactive = registry.deactivate(
        active.release_id,
        expected_revision=active.revision,
    )
    revision, state = channels.current("production")
    channels.backend.compare_and_swap(
        channels.namespace,
        "production",
        expected_revision=revision,
        value=replace(
            state,
            release_revision=inactive.revision,
        ),
    )
    report = guard.inspect(expectation)
    assert not report.allowed
    assert any("inactive" in reason for reason in report.reasons)


def test_startup_release_guard_channel_evidence_tamper():
    policy = AIShellPolicy()
    guard, expectation, _, channels, _ = release_environment(policy)
    revision, state = channels.current("production")
    channels.backend.compare_and_swap(
        channels.namespace,
        "production",
        expected_revision=revision,
        value=replace(state, evidence_digest=fp("x")),
    )
    report = guard.inspect(expectation)
    assert not report.allowed
    assert any("evidence digest" in reason for reason in report.reasons)


def test_startup_release_guard_channel_signature_tamper():
    policy = AIShellPolicy()
    guard, expectation, _, channels, _ = release_environment(policy)
    revision, state = channels.current("production")
    channels.backend.compare_and_swap(
        channels.namespace,
        "production",
        expected_revision=revision,
        value=replace(state, registry_signature=fp("x")),
    )
    report = guard.inspect(expectation)
    assert not report.allowed
    assert any("signature mismatch" in reason for reason in report.reasons)


def test_startup_release_guard_registry_signature_tamper():
    policy = AIShellPolicy()
    guard, expectation, registry, _, active = release_environment(policy)
    registry._items[active.release_id][-1] = replace(
        active,
        signature=replace(active.signature, signature=fp("x")),
    )
    report = guard.inspect(expectation)
    assert not report.allowed
    assert any("signature verification" in reason for reason in report.reasons)


def command_catalog():
    return CommandCatalog(
        (
            CommandDefinition(
                ExecutableSpec("python", sys.executable),
                ArgumentPolicy.allow_any(),
                description="python",
            ),
        )
    )


def service_components(tmp_path, policy):
    commands = command_catalog()
    tools = AIToolCatalog(commands)
    effects = EffectRegistry(
        (
            EffectContract(
                "python",
                frozenset({EffectKind.READ_FILESYSTEM}),
                reversible=True,
            ),
        )
    )
    shell = ShellService(
        ShellExecutor(
            ShellRunner(
                ShellPolicy(
                    executables={"python": sys.executable},
                    cwd_roots=(tmp_path,),
                    default_timeout=1,
                    max_timeout=2,
                    max_output_bytes=4096,
                    max_input_bytes=4096,
                    max_env_bytes=4096,
                    max_args=32,
                    max_arg_bytes=4096,
                )
            )
        )
    )
    shell.start()
    model = CallableAIModelPort(
        "model",
        lambda request: (_ for _ in ()).throw(RuntimeError("unused")),
    )
    planner = AIPlanner(
        model,
        tools,
        AIToolRouter(tools, effects),
        policy_fingerprint=policy.fingerprint,
    )
    orchestrator = AIShellOrchestrator(
        planner=planner,
        critic=AIPlanCritic(effects, policy),
        compiler=AIPlanCompiler(effects),
        shell_service=shell,
    )
    diagnostics = AIShellDiagnostics(tools, effects, policy, model)
    governance = AIShellGovernance(AIPolicyStore(policy))
    return orchestrator, diagnostics, governance


def test_ai_service_start_ready_when_release_matches(tmp_path):
    policy = AIShellPolicy()
    guard, expectation, _, _, _ = release_environment(policy)
    orchestrator, diagnostics, governance = service_components(tmp_path, policy)
    service = AIShellService(
        orchestrator,
        diagnostics,
        governance,
        release_guard=guard,
        release_expectation=expectation,
    )
    service.start()
    assert service.state.phase is AIServicePhase.READY
    status = service.status().to_dict()
    assert status["release"]["allowed"] is True


def test_ai_service_start_fails_closed_on_release_drift(tmp_path):
    policy = AIShellPolicy()
    guard, expectation, _, _, _ = release_environment(policy)
    expectation = replace(expectation, code_revision="wrong")
    orchestrator, diagnostics, governance = service_components(tmp_path, policy)
    service = AIShellService(
        orchestrator,
        diagnostics,
        governance,
        release_guard=guard,
        release_expectation=expectation,
    )
    service.start()
    assert service.state.phase is AIServicePhase.FAILED
    assert service.status().to_dict()["release"]["allowed"] is False


def test_ai_service_release_configuration_must_be_paired(tmp_path):
    policy = AIShellPolicy()
    guard, expectation, _, _, _ = release_environment(policy)
    orchestrator, diagnostics, governance = service_components(tmp_path, policy)
    with pytest.raises(ValueError, match="configured together"):
        AIShellService(
            orchestrator,
            diagnostics,
            governance,
            release_guard=guard,
        )
    with pytest.raises(ValueError, match="configured together"):
        AIShellService(
            orchestrator,
            diagnostics,
            governance,
            release_expectation=expectation,
        )
