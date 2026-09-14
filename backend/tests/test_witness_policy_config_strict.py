from __future__ import annotations

import base64

import pytest

from core.transparency_witness_config import load_witness_policy


def _public_key(seed: int = 1) -> str:
    return base64.b64encode(bytes([seed]) * 32).decode("ascii")


def _row(**changes):
    row = {
        "id": "w0",
        "independence_group": "org-a",
        "enabled": True,
        "public_key_b64": _public_key(),
    }
    row.update(changes)
    return row


def test_valid_policy_preserves_exact_types():
    raw = '[{"id":"w0","independence_group":"org-a","enabled":true,"public_key_b64":"' + _public_key() + '"}]'
    policy = load_witness_policy(
        raw_json=raw,
        required_groups=1,
        max_age_seconds=300,
        finality_required=True,
        signed_finality_required=True,
    )
    assert policy.required_groups == 1
    assert type(policy.required_groups) is int
    assert policy.finality_required is True
    assert policy.signed_finality_required is True
    assert policy.witnesses[0].enabled is True


def test_json_string_boolean_cannot_enable_a_witness():
    raw = '[{"id":"w0","independence_group":"org-a","enabled":"false","public_key_b64":"' + _public_key() + '"}]'
    with pytest.raises(ValueError, match="enabled must be boolean"):
        load_witness_policy(raw_json=raw, required_groups=1)


def test_bool_as_int_policy_arguments_are_rejected():
    with pytest.raises(ValueError, match="required_groups must be an integer"):
        load_witness_policy(raw_json="[]", required_groups=True)
    with pytest.raises(ValueError, match="max_age_seconds must be an integer"):
        load_witness_policy(raw_json="[]", required_groups=1, max_age_seconds=True)
    with pytest.raises(ValueError, match="finality_required must be boolean"):
        load_witness_policy(raw_json="[]", required_groups=1, finality_required=1)
    with pytest.raises(ValueError, match="signed_finality_required must be boolean"):
        load_witness_policy(raw_json="[]", required_groups=1, signed_finality_required="false")


def test_duplicate_json_keys_and_unknown_fields_are_rejected():
    duplicate = '[{"id":"w0","id":"w1","independence_group":"org-a"}]'
    with pytest.raises(ValueError, match="strict valid JSON"):
        load_witness_policy(raw_json=duplicate, required_groups=1)

    unknown = '[{"id":"w0","independence_group":"org-a","admin":true}]'
    with pytest.raises(ValueError, match="schema mismatch"):
        load_witness_policy(raw_json=unknown, required_groups=1)


def test_identity_and_public_key_are_not_whitespace_normalized():
    raw_id = '[{"id":" w0","independence_group":"org-a"}]'
    with pytest.raises(ValueError, match="canonical non-empty text"):
        load_witness_policy(raw_json=raw_id, required_groups=1)

    raw_group = '[{"id":"w0","independence_group":"org-a "}]'
    with pytest.raises(ValueError, match="canonical non-empty text"):
        load_witness_policy(raw_json=raw_group, required_groups=1)

    raw_key = '[{"id":"w0","independence_group":"org-a","public_key_b64":"' + _public_key() + ' "}]'
    with pytest.raises(ValueError, match="canonical base64 text"):
        load_witness_policy(raw_json=raw_key, required_groups=1)


def test_noncanonical_environment_numbers_and_booleans_fail_closed(monkeypatch):
    monkeypatch.setenv("TRANSPARENCY_WITNESS_QUORUM", "03")
    with pytest.raises(ValueError, match="leading zeros"):
        load_witness_policy(raw_json="[]")

    monkeypatch.setenv("TRANSPARENCY_WITNESS_QUORUM", "3")
    monkeypatch.setenv("TRANSPARENCY_WITNESS_MAX_AGE_SECONDS", " 3600")
    with pytest.raises(ValueError, match="canonical positive integer"):
        load_witness_policy(raw_json="[]")

    monkeypatch.setenv("TRANSPARENCY_WITNESS_MAX_AGE_SECONDS", "3600")
    monkeypatch.setenv("TRANSPARENCY_FINALITY_REQUIRED", "TRUE")
    with pytest.raises(ValueError, match="canonical boolean string"):
        load_witness_policy(raw_json="[]")


def test_disabled_witness_does_not_satisfy_required_quorum():
    raw = '[{"id":"w0","independence_group":"org-a","enabled":false,"public_key_b64":"' + _public_key() + '"}]'
    with pytest.raises(ValueError, match="cannot satisfy quorum"):
        load_witness_policy(raw_json=raw, required_groups=1, finality_required=True)


def test_signed_finality_requires_pinned_key_groups_not_merely_ids():
    raw = '[{"id":"w0","independence_group":"org-a","enabled":true}]'
    with pytest.raises(ValueError, match="pinned Ed25519"):
        load_witness_policy(raw_json=raw, required_groups=1, signed_finality_required=True)
