"""AI effect-to-isolation compiler, resource policy, and sandbox attestation tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from skeleton.shells.ai.effects import EffectContract, EffectKind, EffectRegistry
from skeleton.shells.ai.isolation_compiler import AIIsolationCompiler
from skeleton.shells.ai.resource_profile import (
    AIResourceCompiler,
    AIResourcePolicy,
    AIResourceProfile,
)
from skeleton.shells.ai.risk import AIRiskAssessor, RiskBand
from skeleton.shells.ai.sandbox_attestation import (
    SandboxAttestationVerifier,
    SandboxCapabilities,
)
from skeleton.shells.ai.sandbox_contract import AISandboxContractBuilder
from skeleton.shells.ai.types import AIAction, AIIntent, AIPlanProposal, IntentConstraint
from skeleton.shells.isolation import IsolationLevel


def effects():
    return EffectRegistry(
        (
            EffectContract(
                "read",
                frozenset({EffectKind.READ_FILESYSTEM}),
                idempotent=True,
                reversible=True,
            ),
            EffectContract(
                "write",
                frozenset({EffectKind.WRITE_FILESYSTEM}),
                reversible=True,
            ),
            EffectContract(
                "net",
                frozenset({EffectKind.NETWORK}),
                reversible=True,
            ),
            EffectContract(
                "delete",
                frozenset({EffectKind.DELETE_FILESYSTEM}),
                reversible=False,
            ),
            EffectContract(
                "deploy",
                frozenset({EffectKind.DEPLOYMENT, EffectKind.NETWORK}),
                reversible=False,
            ),
        )
    )


def intent(command, **constraint_changes):
    values = dict(
        max_steps=4,
        max_timeout_seconds=10,
        allow_network=False,
        allow_writes=False,
        allow_destructive=False,
    )
    values.update(constraint_changes)
    return AIIntent(
        "i",
        "do work",
        constraint=IntentConstraint(**values),
    )


def proposal(command, timeout=2):
    return AIPlanProposal(
        "p",
        "i",
        (
            AIAction(
                "a",
                command,
                timeout_seconds=timeout,
            ),
        ),
        confidence=0.9,
        uncertainty=0.1,
    )


def risk(command, item_intent=None):
    item_intent = item_intent or intent(command)
    return AIRiskAssessor(effects()).assess(
        item_intent,
        proposal(command),
    )


def test_read_only_compiles_workspace_isolation():
    registry = effects()
    item_intent = intent("read")
    item_proposal = proposal("read")
    decision = AIIsolationCompiler(registry).compile(
        item_intent,
        item_proposal,
        AIRiskAssessor(registry).assess(item_intent, item_proposal),
    )
    assert decision.requirement.level is IsolationLevel.WORKSPACE
    assert decision.requirement.require_readonly_source
    assert not decision.requirement.allow_network
    assert not decision.requirement.allow_home


def test_write_without_intent_permission_remains_readonly():
    registry = effects()
    item_intent = intent("write")
    item_proposal = proposal("write")
    decision = AIIsolationCompiler(registry).compile(
        item_intent,
        item_proposal,
        AIRiskAssessor(registry).assess(item_intent, item_proposal),
    )
    assert decision.requirement.require_readonly_source
    assert decision.requirement.allowed_write_roots == ()


def test_write_with_permission_can_open_narrow_root(tmp_path):
    registry = effects()
    root = tmp_path / "workspace"
    root.mkdir()
    sub = root / "generated"
    item_intent = intent("write", allow_writes=True)
    item_proposal = proposal("write")
    decision = AIIsolationCompiler(
        registry,
        default_write_roots=(str(root),),
    ).compile(
        item_intent,
        item_proposal,
        AIRiskAssessor(registry).assess(item_intent, item_proposal),
        requested_write_roots=(str(sub),),
    )
    assert not decision.requirement.require_readonly_source
    assert decision.requirement.allowed_write_roots == (str(sub.resolve()),)


def test_write_root_outside_allowlist_rejected(tmp_path):
    registry = effects()
    root = tmp_path / "workspace"
    other = tmp_path / "other"
    root.mkdir()
    other.mkdir()
    item_intent = intent("write", allow_writes=True)
    item_proposal = proposal("write")
    compiler = AIIsolationCompiler(
        registry,
        default_write_roots=(str(root),),
    )
    with pytest.raises(ValueError, match="outside"):
        compiler.compile(
            item_intent,
            item_proposal,
            AIRiskAssessor(registry).assess(item_intent, item_proposal),
            requested_write_roots=(str(other),),
        )


def test_write_root_requires_configured_allowlist(tmp_path):
    registry = effects()
    root = tmp_path / "workspace"
    root.mkdir()
    item_intent = intent("write", allow_writes=True)
    item_proposal = proposal("write")
    with pytest.raises(ValueError, match="no AI isolation write roots"):
        AIIsolationCompiler(registry).compile(
            item_intent,
            item_proposal,
            AIRiskAssessor(registry).assess(item_intent, item_proposal),
            requested_write_roots=(str(root),),
        )


def test_relative_write_root_rejected(tmp_path):
    registry = effects()
    root = tmp_path / "workspace"
    root.mkdir()
    item_intent = intent("write", allow_writes=True)
    item_proposal = proposal("write")
    with pytest.raises(ValueError, match="absolute"):
        AIIsolationCompiler(
            registry,
            default_write_roots=(str(root),),
        ).compile(
            item_intent,
            item_proposal,
            AIRiskAssessor(registry).assess(item_intent, item_proposal),
            requested_write_roots=("relative/path",),
        )


def test_network_allowed_only_when_intent_allows():
    registry = effects()
    denied_intent = intent("net", allow_network=False)
    allowed_intent = intent("net", allow_network=True)
    item_proposal = proposal("net")
    denied = AIIsolationCompiler(registry).compile(
        denied_intent,
        item_proposal,
        AIRiskAssessor(registry).assess(denied_intent, item_proposal),
    )
    allowed = AIIsolationCompiler(registry).compile(
        allowed_intent,
        item_proposal,
        AIRiskAssessor(registry).assess(allowed_intent, item_proposal),
    )
    assert not denied.requirement.allow_network
    assert allowed.requirement.allow_network


def test_delete_forces_sandboxed_level():
    registry = effects()
    item_intent = intent(
        "delete",
        allow_writes=True,
        allow_destructive=True,
    )
    item_proposal = proposal("delete")
    decision = AIIsolationCompiler(registry).compile(
        item_intent,
        item_proposal,
        AIRiskAssessor(registry).assess(item_intent, item_proposal),
    )
    assert decision.requirement.level is IsolationLevel.SANDBOXED


def test_deploy_forces_sandboxed_level():
    registry = effects()
    item_intent = intent(
        "deploy",
        allow_network=True,
        allow_destructive=True,
    )
    item_proposal = proposal("deploy")
    decision = AIIsolationCompiler(registry).compile(
        item_intent,
        item_proposal,
        AIRiskAssessor(registry).assess(item_intent, item_proposal),
    )
    assert decision.requirement.level is IsolationLevel.SANDBOXED


def test_unknown_effect_is_reported():
    registry = effects()
    item_intent = intent("unknown")
    item_proposal = proposal("unknown")
    assessment = AIRiskAssessor(registry).assess(item_intent, item_proposal)
    decision = AIIsolationCompiler(registry).compile(
        item_intent,
        item_proposal,
        assessment,
    )
    assert any("unknown effect contract" in reason for reason in decision.reasons)


def test_resource_profile_no_wider_than():
    parent = AIResourceProfile(
        10,
        10,
        1000,
        10,
        1000,
        10,
        1000,
    )
    child = AIResourceProfile(
        5,
        5,
        500,
        5,
        500,
        5,
        500,
    )
    assert child.no_wider_than(parent)
    assert not parent.no_wider_than(child)


def test_resource_policy_tightens_with_risk():
    policy = AIResourcePolicy()
    assert policy.critical.memory_bytes < policy.high.memory_bytes
    assert policy.high.memory_bytes < policy.medium.memory_bytes
    assert policy.medium.memory_bytes < policy.low.memory_bytes


def test_resource_compiler_bounds_wall_time_by_intent():
    registry = effects()
    item_intent = AIIntent(
        "i",
        "read",
        constraint=IntentConstraint(
            max_steps=4,
            max_timeout_seconds=2,
        ),
    )
    item_proposal = AIPlanProposal(
        "p",
        "i",
        (
            AIAction("a", "read", timeout_seconds=2),
            AIAction("b", "read", timeout_seconds=2),
        ),
        confidence=0.9,
        uncertainty=0.1,
    )
    assessment = AIRiskAssessor(registry).assess(
        item_intent,
        item_proposal,
    )
    decision = AIResourceCompiler().compile(
        item_intent,
        item_proposal,
        assessment,
    )
    assert decision.profile.wall_seconds <= 4


def test_resource_compiler_cpu_not_above_wall():
    registry = effects()
    item_intent = intent("read")
    item_proposal = proposal("read")
    assessment = AIRiskAssessor(registry).assess(item_intent, item_proposal)
    decision = AIResourceCompiler().compile(
        item_intent,
        item_proposal,
        assessment,
    )
    assert decision.profile.cpu_seconds <= decision.profile.wall_seconds


def sandbox_caps(**changes):
    values = dict(
        backend_id="sandbox",
        backend_version="1",
        max_level=IsolationLevel.SANDBOXED,
        private_tmp=True,
        clean_environment=True,
        readonly_source=True,
        network_namespace=True,
        home_hiding=True,
        process_group=True,
        no_new_privileges=True,
        syscall_filter=True,
        resource_limits=True,
        max_profile=AIResourceProfile(
            120,
            60,
            1024 * 1024 * 1024,
            64,
            1024 * 1024 * 1024,
            1024,
            16 * 1024 * 1024,
        ),
    )
    values.update(changes)
    return SandboxCapabilities(**values)


def contract_for(command="read", **constraint_changes):
    registry = effects()
    item_intent = intent(command, **constraint_changes)
    item_proposal = proposal(command)
    assessment = AIRiskAssessor(registry).assess(item_intent, item_proposal)
    isolation = AIIsolationCompiler(registry).compile(
        item_intent,
        item_proposal,
        assessment,
    )
    resources = AIResourceCompiler().compile(
        item_intent,
        item_proposal,
        assessment,
    )
    return AISandboxContractBuilder().build(isolation, resources)


def test_sandbox_contract_digest_stable():
    contract = contract_for("read")
    assert len(contract.digest) == 64
    assert contract.digest == contract.digest


def test_sandbox_contract_network_namespace_for_no_network():
    contract = contract_for("read")
    assert contract.require_network_namespace


def test_sandbox_contract_strong_flags_for_high_risk():
    contract = contract_for(
        "delete",
        allow_writes=True,
        allow_destructive=True,
    )
    assert contract.require_no_new_privileges
    assert contract.require_syscall_filter


def test_sandbox_attestation_happy_path():
    report = SandboxAttestationVerifier().inspect(
        contract_for("read"),
        sandbox_caps(),
    )
    assert report.compatible


def test_sandbox_attestation_level_too_low():
    report = SandboxAttestationVerifier().inspect(
        contract_for(
            "delete",
            allow_writes=True,
            allow_destructive=True,
        ),
        sandbox_caps(max_level=IsolationLevel.WORKSPACE),
    )
    assert not report.compatible
    assert any("isolation level" in reason for reason in report.reasons)


@pytest.mark.parametrize(
    "field,phrase",
    [
        ("private_tmp", "temporary"),
        ("clean_environment", "clean environment"),
        ("readonly_source", "read-only"),
        ("home_hiding", "home"),
        ("process_group", "process group"),
        ("resource_limits", "resource limits"),
    ],
)
def test_sandbox_attestation_missing_capability(field, phrase):
    report = SandboxAttestationVerifier().inspect(
        contract_for("read"),
        sandbox_caps(**{field: False}),
    )
    assert not report.compatible
    assert any(phrase in reason for reason in report.reasons)


def test_sandbox_attestation_requires_network_namespace_when_network_disabled():
    report = SandboxAttestationVerifier().inspect(
        contract_for("read"),
        sandbox_caps(network_namespace=False),
    )
    assert not report.compatible


def test_sandbox_attestation_high_risk_requires_syscall_filter():
    contract = contract_for(
        "delete",
        allow_writes=True,
        allow_destructive=True,
    )
    report = SandboxAttestationVerifier().inspect(
        contract,
        sandbox_caps(syscall_filter=False),
    )
    assert not report.compatible


def test_sandbox_attestation_high_risk_requires_no_new_privileges():
    contract = contract_for(
        "delete",
        allow_writes=True,
        allow_destructive=True,
    )
    report = SandboxAttestationVerifier().inspect(
        contract,
        sandbox_caps(no_new_privileges=False),
    )
    assert not report.compatible


def test_sandbox_attestation_resource_capability_must_cover_contract():
    tiny = AIResourceProfile(
        1,
        1,
        1024,
        1,
        1024,
        1,
        1024,
    )
    report = SandboxAttestationVerifier().inspect(
        contract_for("read"),
        sandbox_caps(max_profile=tiny),
    )
    assert not report.compatible
