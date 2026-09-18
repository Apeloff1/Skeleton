"""Assurance policy fingerprint and execution-binding tamper tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.shells.ai.assurance import (
    AIExecutionAssurancePolicy,
    AssuranceLevel,
)
from skeleton.shells.ai.assurance_binding import AssuranceBinding
from skeleton.shells.ai.risk import RiskBand


def fp(char):
    return char * 64


def binding(**changes):
    values = dict(
        schema_version=1,
        risk_band=RiskBand.HIGH,
        assurance_policy_digest=fp("a"),
        plan_fingerprint=fp("p"),
        release_evidence_digest=fp("r"),
        preconditions_digest=fp("c"),
        approval_id="approval-1",
        quorum_digest=fp("q"),
        execution_backend_id="sandbox:verified",
        sandbox_binding_digest=fp("s"),
        runtime_trust_digest=fp("t"),
    )
    values.update(changes)
    return AssuranceBinding(**values)


def test_assurance_policy_digest_is_stable():
    policy = AIExecutionAssurancePolicy.production()
    assert len(policy.digest) == 64
    assert policy.digest == policy.digest


def test_assurance_policy_digest_changes_with_level():
    first = AIExecutionAssurancePolicy()
    second = AIExecutionAssurancePolicy(
        medium=AssuranceLevel.SANDBOXED,
    )
    assert first.digest != second.digest


def test_assurance_policy_digest_changes_with_release_requirement():
    first = AIExecutionAssurancePolicy()
    second = AIExecutionAssurancePolicy(
        require_release_bands=frozenset({RiskBand.MEDIUM}),
    )
    assert first.digest != second.digest


def test_assurance_policy_digest_changes_with_precondition_requirement():
    first = AIExecutionAssurancePolicy()
    second = AIExecutionAssurancePolicy(
        require_preconditions_bands=frozenset({RiskBand.HIGH}),
    )
    assert first.digest != second.digest


def test_assurance_policy_digest_changes_with_human_requirement():
    first = AIExecutionAssurancePolicy()
    second = AIExecutionAssurancePolicy(
        require_human_approval_bands=frozenset({RiskBand.HIGH}),
    )
    assert first.digest != second.digest


def test_assurance_policy_digest_changes_with_quorum_requirement():
    first = AIExecutionAssurancePolicy()
    second = AIExecutionAssurancePolicy(
        require_quorum_bands=frozenset({RiskBand.HIGH}),
    )
    assert first.digest != second.digest


def test_assurance_policy_to_dict_is_deterministic():
    policy = AIExecutionAssurancePolicy(
        require_release_bands=frozenset(
            {RiskBand.HIGH, RiskBand.MEDIUM}
        ),
        require_quorum_bands=frozenset(
            {RiskBand.MEDIUM, RiskBand.HIGH}
        ),
    )
    first = policy.to_dict()
    second = policy.to_dict()
    assert first == second
    assert first["require_release_bands"] == ["high", "medium"]
    assert first["require_quorum_bands"] == ["high", "medium"]


def test_production_assurance_policy_has_expected_surface():
    policy = AIExecutionAssurancePolicy.production()
    assert policy.low is AssuranceLevel.STANDARD
    assert policy.medium is AssuranceLevel.SEALED
    assert policy.high is AssuranceLevel.SANDBOXED
    assert policy.critical is AssuranceLevel.DENIED
    assert RiskBand.MEDIUM in policy.require_release_bands
    assert RiskBand.HIGH in policy.require_release_bands
    assert RiskBand.HIGH in policy.require_preconditions_bands
    assert RiskBand.HIGH in policy.require_human_approval_bands
    assert RiskBand.HIGH in policy.require_quorum_bands


def test_assurance_binding_digest_stable():
    item = binding()
    assert len(item.digest) == 64
    assert item.digest == item.digest


def test_assurance_binding_to_dict_contains_all_authority_surfaces():
    data = binding().to_dict()
    assert data == {
        "schema_version": 1,
        "risk_band": "high",
        "assurance_policy_digest": fp("a"),
        "plan_fingerprint": fp("p"),
        "release_evidence_digest": fp("r"),
        "preconditions_digest": fp("c"),
        "approval_id": "approval-1",
        "quorum_digest": fp("q"),
        "execution_backend_id": "sandbox:verified",
        "sandbox_binding_digest": fp("s"),
        "runtime_trust_digest": fp("t"),
    }


@pytest.mark.parametrize(
    "field,value",
    [
        ("risk_band", RiskBand.MEDIUM),
        ("assurance_policy_digest", fp("b")),
        ("plan_fingerprint", fp("x")),
        ("release_evidence_digest", fp("l")),
        ("preconditions_digest", fp("d")),
        ("approval_id", "approval-2"),
        ("quorum_digest", fp("w")),
        ("execution_backend_id", "sandbox:other"),
        ("sandbox_binding_digest", fp("z")),
        ("runtime_trust_digest", fp("y")),
    ],
)
def test_assurance_binding_digest_changes_for_every_bound_surface(field, value):
    original = binding()
    changed = replace(original, **{field: value})
    assert changed.digest != original.digest


def test_assurance_binding_empty_optional_surfaces_supported():
    item = binding(
        release_evidence_digest="",
        preconditions_digest="",
        approval_id="",
        quorum_digest="",
        execution_backend_id="shell-service-host",
        sandbox_binding_digest="",
        runtime_trust_digest="",
    )
    assert len(item.digest) == 64
    assert item.to_dict()["execution_backend_id"] == "shell-service-host"


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", 2),
        ("assurance_policy_digest", "bad"),
        ("plan_fingerprint", "bad"),
        ("release_evidence_digest", "bad"),
        ("preconditions_digest", "bad"),
        ("quorum_digest", "bad"),
        ("sandbox_binding_digest", "bad"),
        ("runtime_trust_digest", "bad"),
    ],
)
def test_assurance_binding_validation_rejects_invalid_digest_fields(field, value):
    values = dict(
        schema_version=1,
        risk_band=RiskBand.HIGH,
        assurance_policy_digest=fp("a"),
        plan_fingerprint=fp("p"),
    )
    values[field] = value
    with pytest.raises(ValueError):
        AssuranceBinding(**values)


def test_assurance_binding_rejects_long_approval_id():
    with pytest.raises(ValueError, match="approval_id"):
        binding(approval_id="x" * 129)


def test_assurance_binding_rejects_long_backend_id():
    with pytest.raises(ValueError, match="backend"):
        binding(execution_backend_id="x" * 257)


@pytest.mark.parametrize(
    "band",
    [
        RiskBand.LOW,
        RiskBand.MEDIUM,
        RiskBand.HIGH,
        RiskBand.CRITICAL,
    ],
)
def test_assurance_binding_round_trips_risk_band(band):
    item = binding(risk_band=band)
    assert item.risk_band is band
    assert item.to_dict()["risk_band"] == band.value


def test_assurance_binding_string_risk_band_is_normalized():
    item = binding(risk_band="medium")
    assert item.risk_band is RiskBand.MEDIUM


def test_assurance_binding_policy_change_invalidates_prior_digest():
    old_policy = AIExecutionAssurancePolicy()
    new_policy = AIExecutionAssurancePolicy.production()
    old = binding(assurance_policy_digest=old_policy.digest)
    new = binding(assurance_policy_digest=new_policy.digest)
    assert old.digest != new.digest


def test_assurance_binding_backend_swap_invalidates_prior_digest():
    host = binding(
        execution_backend_id="shell-service-host",
        sandbox_binding_digest="",
    )
    sandbox = binding(
        execution_backend_id="sandbox:verified",
        sandbox_binding_digest=fp("s"),
    )
    assert host.digest != sandbox.digest


def test_assurance_binding_quorum_mutation_invalidates_prior_digest():
    first = binding(quorum_digest=fp("q"))
    second = binding(quorum_digest=fp("x"))
    assert first.digest != second.digest


def test_assurance_binding_release_promotion_invalidates_prior_digest():
    first = binding(release_evidence_digest=fp("1"))
    second = binding(release_evidence_digest=fp("2"))
    assert first.digest != second.digest


def test_assurance_binding_precondition_change_invalidates_prior_digest():
    first = binding(preconditions_digest=fp("1"))
    second = binding(preconditions_digest=fp("2"))
    assert first.digest != second.digest


def test_assurance_binding_approval_substitution_invalidates_prior_digest():
    first = binding(approval_id="approval-one")
    second = binding(approval_id="approval-two")
    assert first.digest != second.digest


def test_assurance_binding_plan_change_invalidates_prior_digest():
    first = binding(plan_fingerprint=fp("1"))
    second = binding(plan_fingerprint=fp("2"))
    assert first.digest != second.digest


def test_assurance_binding_sandbox_capability_change_invalidates_prior_digest():
    first = binding(sandbox_binding_digest=fp("1"))
    second = binding(sandbox_binding_digest=fp("2"))
    assert first.digest != second.digest



def test_assurance_binding_runtime_trust_epoch_change_invalidates_prior_digest():
    first = binding(runtime_trust_digest=fp("1"))
    second = binding(runtime_trust_digest=fp("2"))
    assert first.digest != second.digest


def test_assurance_binding_empty_runtime_trust_is_supported_without_guard():
    item = binding(runtime_trust_digest="")
    assert item.to_dict()["runtime_trust_digest"] == ""
    assert len(item.digest) == 64
