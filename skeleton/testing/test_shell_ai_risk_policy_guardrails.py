"""AI shell effect, risk, autonomy policy, and guardrail regressions."""

from __future__ import annotations

import pytest

from skeleton.shells.ai.effects import EffectContract, EffectKind, EffectRegistry
from skeleton.shells.ai.guardrails import GuardrailSeverity, ModelOutputGuard
from skeleton.shells.ai.policy import AIShellPolicy, AutonomyMode
from skeleton.shells.ai.risk import AIRiskAssessor, RiskBand
from skeleton.shells.ai.types import AIAction, AIIntent, AIPlanProposal, IntentConstraint


def action(command="inspect", **changes):
    values = dict(action_id="a", command=command, args=())
    values.update(changes)
    return AIAction(**values)


def intent(**changes):
    values = dict(
        intent_id="i",
        goal="Do bounded work",
        constraint=IntentConstraint(max_steps=8),
    )
    values.update(changes)
    return AIIntent(**values)


def proposal(command="inspect", **changes):
    values = dict(
        proposal_id="p",
        intent_id="i",
        actions=(action(command),),
        confidence=0.9,
        uncertainty=0.1,
    )
    values.update(changes)
    return AIPlanProposal(**values)


def registry(*contracts):
    return EffectRegistry(tuple(contracts))


def contract(command="inspect", effects=(), **changes):
    return EffectContract(command, frozenset(effects), **changes)


def test_effect_contract_destructive_delete():
    item = contract("delete", {EffectKind.DELETE_FILESYSTEM})
    assert item.destructive


def test_effect_contract_read_not_destructive():
    item = contract("inspect", {EffectKind.READ_FILESYSTEM})
    assert not item.destructive


def test_effect_compensation_requires_reversible():
    with pytest.raises(ValueError):
        contract("write", {EffectKind.WRITE_FILESYSTEM}, compensation_command="undo")


def test_effect_registry_digest_stable():
    effects = registry(
        contract("b", {EffectKind.NETWORK}),
        contract("a", {EffectKind.READ_FILESYSTEM}),
    )
    assert effects.digest == effects.digest
    assert [item.command for item in effects.snapshot()] == ["a", "b"]


def test_effect_registry_duplicate_rejected():
    effects = registry(contract())
    with pytest.raises(ValueError):
        effects.register(contract())


def test_effect_registry_replace():
    effects = registry(contract())
    effects.register(contract(effects={EffectKind.NETWORK}), replace=True)
    assert EffectKind.NETWORK in effects.get("inspect").effects


def test_risk_read_only_low():
    effects = registry(
        contract(
            "inspect",
            {EffectKind.READ_FILESYSTEM},
            idempotent=True,
            reversible=True,
        )
    )
    result = AIRiskAssessor(effects).assess(intent(), proposal())
    assert result.band is RiskBand.LOW
    assert result.reversible


def test_risk_unknown_command():
    result = AIRiskAssessor(EffectRegistry()).assess(intent(), proposal())
    assert result.unknown_commands == ("inspect",)
    assert not result.reversible


def test_risk_network_conflict_raises_score():
    effects = registry(contract("net", {EffectKind.NETWORK}, reversible=True))
    result = AIRiskAssessor(effects).assess(intent(), proposal("net"))
    assert any("network" in reason for reason in result.reasons)
    assert result.score >= 25


def test_risk_write_conflict():
    effects = registry(
        contract("write", {EffectKind.WRITE_FILESYSTEM}, reversible=True)
    )
    result = AIRiskAssessor(effects).assess(intent(), proposal("write"))
    assert any("write" in reason for reason in result.reasons)


def test_risk_destructive_conflict():
    effects = registry(
        contract("delete", {EffectKind.DELETE_FILESYSTEM}, reversible=False)
    )
    result = AIRiskAssessor(effects).assess(intent(), proposal("delete"))
    assert any("destructive" in reason for reason in result.reasons)
    assert result.band in {RiskBand.HIGH, RiskBand.CRITICAL}


def test_risk_allowed_network_is_lower():
    effects = registry(contract("net", {EffectKind.NETWORK}, reversible=True))
    denied = AIRiskAssessor(effects).assess(intent(), proposal("net"))
    allowed_intent = intent(
        constraint=IntentConstraint(max_steps=8, allow_network=True)
    )
    allowed = AIRiskAssessor(effects).assess(allowed_intent, proposal("net"))
    assert allowed.score < denied.score


def test_risk_uncertainty_adds_risk():
    effects = registry(contract("inspect", {EffectKind.READ_FILESYSTEM}, reversible=True))
    low = AIRiskAssessor(effects).assess(
        intent(),
        proposal(uncertainty=0.05, confidence=0.95),
    )
    high = AIRiskAssessor(effects).assess(
        intent(),
        proposal(uncertainty=0.9, confidence=0.5),
    )
    assert high.score > low.score


def test_policy_fingerprint_stable():
    policy = AIShellPolicy()
    assert len(policy.fingerprint) == 64
    assert policy.fingerprint == policy.fingerprint


def test_policy_propose_mode_requires_approval():
    effects = registry(contract("inspect", {EffectKind.READ_FILESYSTEM}, reversible=True))
    risk = AIRiskAssessor(effects).assess(intent(), proposal())
    decision = AIShellPolicy(autonomy=AutonomyMode.PROPOSE).evaluate(
        intent(),
        proposal(),
        risk,
        proposal_effects=frozenset({EffectKind.READ_FILESYSTEM}),
    )
    assert not decision.allowed
    assert decision.requires_approval


def test_policy_low_risk_autonomous_allows_reversible_low():
    effects = registry(contract("inspect", {EffectKind.READ_FILESYSTEM}, reversible=True))
    risk = AIRiskAssessor(effects).assess(intent(), proposal())
    decision = AIShellPolicy(
        autonomy=AutonomyMode.LOW_RISK_AUTONOMOUS
    ).evaluate(
        intent(),
        proposal(),
        risk,
        proposal_effects=frozenset({EffectKind.READ_FILESYSTEM}),
    )
    assert decision.allowed
    assert not decision.requires_approval


def test_policy_autonomy_requires_reversible_by_default():
    effects = registry(contract("inspect", {EffectKind.READ_FILESYSTEM}, reversible=False))
    risk = AIRiskAssessor(effects).assess(intent(), proposal())
    decision = AIShellPolicy(
        autonomy=AutonomyMode.LOW_RISK_AUTONOMOUS,
        deny_unknown_effects=False,
    ).evaluate(
        intent(),
        proposal(),
        risk,
        proposal_effects=frozenset({EffectKind.READ_FILESYSTEM}),
    )
    assert not decision.allowed


def test_policy_denied_effect():
    effects = registry(contract("root", {EffectKind.PRIVILEGED}, reversible=False))
    risk = AIRiskAssessor(effects).assess(
        intent(constraint=IntentConstraint(max_steps=8, allow_destructive=True)),
        proposal("root"),
    )
    decision = AIShellPolicy(
        autonomy=AutonomyMode.SUPERVISED
    ).evaluate(
        intent(constraint=IntentConstraint(max_steps=8, allow_destructive=True)),
        proposal("root"),
        risk,
        proposal_effects=frozenset({EffectKind.PRIVILEGED}),
    )
    assert not decision.allowed
    assert any("denied effects" in reason for reason in decision.reasons)


def test_policy_unknown_effect_denied():
    risk = AIRiskAssessor(EffectRegistry()).assess(intent(), proposal())
    decision = AIShellPolicy(
        autonomy=AutonomyMode.LOW_RISK_AUTONOMOUS
    ).evaluate(intent(), proposal(), risk)
    assert not decision.allowed


def test_policy_low_confidence_denied():
    effects = registry(contract("inspect", {EffectKind.READ_FILESYSTEM}, reversible=True))
    low_proposal = proposal(confidence=0.2)
    risk = AIRiskAssessor(effects).assess(intent(), low_proposal)
    decision = AIShellPolicy(
        autonomy=AutonomyMode.LOW_RISK_AUTONOMOUS
    ).evaluate(intent(), low_proposal, risk)
    assert not decision.allowed


def test_guard_command_constraint_error():
    item = intent(
        constraint=IntentConstraint(allowed_commands=frozenset({"inspect"}))
    )
    report = ModelOutputGuard().inspect(item, proposal("other"))
    assert not report.ok
    assert any(f.code == "command_constraint" for f in report.findings)


def test_guard_timeout_constraint_error():
    item = intent(constraint=IntentConstraint(max_timeout_seconds=2))
    risky = proposal(actions=(action(timeout_seconds=3),))
    report = ModelOutputGuard().inspect(item, risky)
    assert any(f.code == "timeout_constraint" for f in report.findings)


def test_guard_shell_metacharacter_is_warning_not_execution_denial():
    risky = proposal(actions=(action(args=("hello;touch",)),))
    report = ModelOutputGuard().inspect(intent(), risky)
    findings = [f for f in report.findings if f.code == "shell_metacharacter"]
    assert findings
    assert findings[0].severity is GuardrailSeverity.WARNING
    assert report.ok


def test_guard_interpreter_code_warning():
    risky = proposal(
        actions=(AIAction("a", "python", ("-c", "print(1)")),)
    )
    report = ModelOutputGuard().inspect(intent(), risky)
    assert any(f.code == "interpreter_code" for f in report.findings)


def test_guard_environment_ref_info():
    risky = proposal(
        actions=(action(environment_refs={"TOKEN": "secret/token"}),)
    )
    report = ModelOutputGuard().inspect(intent(), risky)
    assert any(f.code == "environment_reference" for f in report.findings)


def test_guard_free_form_shell_field_denied():
    report = ModelOutputGuard().validate_free_form_payload(
        {"shell_command": "rm -rf /"}
    )
    assert not report.ok


def test_guard_benign_structured_payload():
    report = ModelOutputGuard().validate_free_form_payload(
        {"proposal_id": "p", "actions": []}
    )
    assert report.ok
