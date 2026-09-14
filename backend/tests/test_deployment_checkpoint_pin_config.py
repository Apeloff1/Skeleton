from __future__ import annotations

import base64

import pytest

from core.deployment_checkpoint_pin_config import load_deployment_checkpoint_pin_policy


def _key(seed: int = 1) -> str:
    return base64.b64encode(bytes([seed]) * 32).decode("ascii")


def _raw() -> str:
    return (
        '[{"id":"d0","independence_group":"org-a","enabled":true,"public_key_b64":"'
        + _key(1)
        + '"},{"id":"d1","independence_group":"org-b","enabled":true,"public_key_b64":"'
        + _key(2)
        + '"}]'
    )


def test_deployment_pin_policy_is_independent_from_epistemic_env(monkeypatch):
    monkeypatch.setenv("TRANSPARENCY_FINALITY_REQUIRED", "true")
    monkeypatch.setenv("TRANSPARENCY_SIGNED_FINALITY_REQUIRED", "true")
    policy = load_deployment_checkpoint_pin_policy(
        raw_json="[]", required_groups=1, max_age_seconds=300, required=False,
    )
    assert policy.required is False
    assert policy.witnesses == ()


def test_required_deployment_quorum_needs_enough_pinned_independent_groups():
    one_group = '[{"id":"d0","independence_group":"org-a","enabled":true,"public_key_b64":"' + _key() + '"}]'
    with pytest.raises(ValueError, match="pinned Ed25519"):
        load_deployment_checkpoint_pin_policy(
            raw_json=one_group, required_groups=2, max_age_seconds=300, required=True,
        )


def test_valid_required_policy_preserves_exact_contract():
    policy = load_deployment_checkpoint_pin_policy(
        raw_json=_raw(), required_groups=2, max_age_seconds=300, required=True,
    )
    assert policy.required is True
    assert policy.required_groups == 2
    assert policy.max_age_seconds == 300
    assert {row.independence_group for row in policy.witnesses} == {"org-a", "org-b"}


def test_policy_arguments_reject_python_type_confusion():
    with pytest.raises(ValueError, match="quorum must be an integer"):
        load_deployment_checkpoint_pin_policy(raw_json="[]", required_groups=True)
    with pytest.raises(ValueError, match="max age must be an integer"):
        load_deployment_checkpoint_pin_policy(raw_json="[]", required_groups=1, max_age_seconds=True)
    with pytest.raises(ValueError, match="requirement must be boolean"):
        load_deployment_checkpoint_pin_policy(raw_json="[]", required_groups=1, required="false")


def test_noncanonical_deployment_environment_values_fail_closed(monkeypatch):
    monkeypatch.setenv("DEPLOYMENT_CHECKPOINT_WITNESS_QUORUM", "03")
    with pytest.raises(ValueError, match="leading zeros"):
        load_deployment_checkpoint_pin_policy(raw_json="[]")

    monkeypatch.setenv("DEPLOYMENT_CHECKPOINT_WITNESS_QUORUM", "3")
    monkeypatch.setenv("DEPLOYMENT_CHECKPOINT_WITNESS_MAX_AGE_SECONDS", " 300")
    with pytest.raises(ValueError, match="canonical positive integer"):
        load_deployment_checkpoint_pin_policy(raw_json="[]")

    monkeypatch.setenv("DEPLOYMENT_CHECKPOINT_WITNESS_MAX_AGE_SECONDS", "300")
    monkeypatch.setenv("DEPLOYMENT_CHECKPOINT_SIGNED_PINS_REQUIRED", "TRUE")
    with pytest.raises(ValueError, match="canonical boolean string"):
        load_deployment_checkpoint_pin_policy(raw_json="[]")
