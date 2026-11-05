"""Read-only source key rotation with independent policy pins and revocations."""
from __future__ import annotations

from hashlib import sha256
import json
import os

import pytest

from skeleton.app.cli import run_app_cli
from skeleton.app.offline_source_trust_policy import SCHEMA as POLICY_SCHEMA
from skeleton.app.offline_trust_policy_transition import (
    OfflineTrustPolicyTransitionError,
    inspect_offline_trust_policy_transition,
)


@pytest.fixture
def transition(tmp_path):
    archive = "a" * 64
    manifest = "b" * 64
    old_key = "c" * 64
    new_key = "d" * 64
    old = {
        "schema": POLICY_SCHEMA, "epoch": 2,
        "archive_sha256": archive, "manifest_sha256": manifest,
        "authorized_key_sha256": [old_key], "revoked_key_sha256": [],
    }
    new = {
        "schema": POLICY_SCHEMA, "epoch": 3,
        "archive_sha256": archive, "manifest_sha256": manifest,
        "authorized_key_sha256": [new_key], "revoked_key_sha256": [old_key],
    }
    current = tmp_path / "current-trust.json"
    proposed = tmp_path / "proposed-trust.json"
    for path, payload in ((current, old), (proposed, new)):
        path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
        path.chmod(0o600)
    kwargs = {
        "current_policy": current, "proposed_policy": proposed,
        "expected_current_policy_sha256": sha256(current.read_bytes()).hexdigest(),
        "expected_proposed_policy_sha256": sha256(proposed.read_bytes()).hexdigest(),
        "expected_archive_sha256": archive,
        "expected_manifest_sha256": manifest,
        "authorized": True,
    }
    return kwargs, old, new


def _rewrite(path, payload):
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    path.chmod(0o600)
    return sha256(path.read_bytes()).hexdigest()


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_real_read_only_key_rotation_transition(transition):
    kwargs, old, new = transition
    before = (kwargs["current_policy"].read_bytes(),
              kwargs["proposed_policy"].read_bytes())
    result = inspect_offline_trust_policy_transition(**kwargs)
    assert result["added_active_key_sha256"] == new["authorized_key_sha256"]
    assert result["removed_active_key_sha256"] == old["authorized_key_sha256"]
    assert result["newly_revoked_key_sha256"] == old["authorized_key_sha256"]
    assert result["revocation_monotonic_in_supplied_pair"] is True
    assert result["policy_transition_published"] is False
    assert result["persistent_epoch_rollback_protection"] is False
    assert result["release_certified"] is False
    assert (kwargs["current_policy"].read_bytes(),
            kwargs["proposed_policy"].read_bytes()) == before


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_revocation_cannot_be_dropped(transition):
    kwargs, old, new = transition
    old["revoked_key_sha256"] = ["e" * 64]
    kwargs["expected_current_policy_sha256"] = _rewrite(kwargs["current_policy"], old)
    with pytest.raises(OfflineTrustPolicyTransitionError, match="revocations"):
        inspect_offline_trust_policy_transition(**kwargs)


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_epoch_cannot_go_backwards(transition):
    kwargs, _, new = transition
    new["epoch"] = 1
    kwargs["expected_proposed_policy_sha256"] = _rewrite(kwargs["proposed_policy"], new)
    with pytest.raises(OfflineTrustPolicyTransitionError, match="epoch"):
        inspect_offline_trust_policy_transition(**kwargs)


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_noop_epoch_bump_is_not_rotation(transition):
    kwargs, old, new = transition
    new["authorized_key_sha256"] = old["authorized_key_sha256"]
    new["revoked_key_sha256"] = []
    kwargs["expected_proposed_policy_sha256"] = _rewrite(kwargs["proposed_policy"], new)
    with pytest.raises(OfflineTrustPolicyTransitionError, match="no-op"):
        inspect_offline_trust_policy_transition(**kwargs)


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_no_active_signer_is_denied(transition):
    kwargs, _, new = transition
    new["revoked_key_sha256"] = new["authorized_key_sha256"]
    kwargs["expected_proposed_policy_sha256"] = _rewrite(kwargs["proposed_policy"], new)
    with pytest.raises(OfflineTrustPolicyTransitionError, match="no active"):
        inspect_offline_trust_policy_transition(**kwargs)


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_wrong_independent_pin_denied(transition):
    kwargs, _, _ = transition
    with pytest.raises(OfflineTrustPolicyTransitionError, match="pin mismatch"):
        inspect_offline_trust_policy_transition(
            **{**kwargs, "expected_proposed_policy_sha256": "0" * 64},
        )


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_policy_symlink_rejected(transition, tmp_path):
    kwargs, _, _ = transition
    alias = tmp_path / "alias-trust.json"
    alias.symlink_to(kwargs["proposed_policy"])
    with pytest.raises((OSError, ValueError)):
        inspect_offline_trust_policy_transition(
            **{**kwargs, "proposed_policy": alias},
        )


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_authority_denied_before_policy_read(transition, monkeypatch):
    import skeleton.app.offline_trust_policy_transition as module
    kwargs, _, _ = transition

    def forbidden(*args, **inner):
        raise AssertionError("unauthorized policy read")

    monkeypatch.setattr(module, "_read_policy", forbidden)
    with pytest.raises(PermissionError):
        inspect_offline_trust_policy_transition(
            **{**kwargs, "authorized": False},
        )


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_cli_rotation_inspection_and_authority(transition, capsys):
    kwargs, _, _ = transition
    args = ["inspect-trust-policy-transition"]
    for name, key in (
        ("current-policy", "current_policy"),
        ("proposed-policy", "proposed_policy"),
        ("expected-current-policy-sha256", "expected_current_policy_sha256"),
        ("expected-proposed-policy-sha256", "expected_proposed_policy_sha256"),
        ("expected-archive-sha256", "expected_archive_sha256"),
        ("expected-manifest-sha256", "expected_manifest_sha256"),
    ):
        args.extend(["--" + name, str(kwargs[key])])
    assert run_app_cli(args) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"
    assert run_app_cli(args + ["--trusted-local-operator"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["read_only"] is True
    assert result["policy_transition_published"] is False
    assert result["release_certified"] is False
