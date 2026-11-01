"""End-to-end source trust admission and no-clobber policy-bound installation."""
from __future__ import annotations

from hashlib import sha256
import json
import os

import pytest

from skeleton.app.cli import run_app_cli
from skeleton.app.offline_source_trust_policy import (
    SCHEMA, OfflineSourceTrustPolicyError, verify_policy_signed_offline_source,
)
from skeleton.app.offline_policy_signed_install import (
    install_policy_signed_offline_game_source,
)
from skeleton.testing.test_app_offline_archive_signature import signed


@pytest.fixture
def trust(signed, tmp_path):
    archive, archive_pin, manifest_pin, key, signature, _ = signed
    key_pin = sha256(key.read_bytes()).hexdigest()
    payload = {
        "schema": SCHEMA,
        "epoch": 1,
        "archive_sha256": archive_pin,
        "manifest_sha256": manifest_pin,
        "authorized_key_sha256": [key_pin],
        "revoked_key_sha256": [],
    }
    policy = tmp_path / "operator-trust.json"
    policy.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    policy.chmod(0o600)
    return (archive, key, signature, policy, payload, {
        "expected_archive_sha256": archive_pin,
        "expected_manifest_sha256": manifest_pin,
        "expected_public_key_sha256": key_pin,
        "expected_policy_sha256": sha256(policy.read_bytes()).hexdigest(),
        "authorized": True,
    })


def _check(trust, **changes):
    archive, key, signature, policy, _, kwargs = trust
    return verify_policy_signed_offline_source(
        archive, key, signature, policy, **{**kwargs, **changes},
    )


def _rewrite(trust, *, payload=None):
    policy = trust[3]
    policy.write_text(json.dumps(payload or trust[4], sort_keys=True), encoding="utf-8")
    policy.chmod(0o600)
    return sha256(policy.read_bytes()).hexdigest()


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_read_only_policy_signature_acceptance(trust):
    archive, key, signature, policy, _, _ = trust
    before = (archive.read_bytes(), key.read_bytes(),
              signature.read_bytes(), policy.read_bytes())
    result = _check(trust)
    assert result["key_authorized_by_pinned_policy"] is True
    assert result["source_archive_signature_verified"] is True
    assert result["policy_freshness_independently_proven"] is False
    assert result["native_device_qualified"] is False
    assert result["release_certified"] is False
    assert (archive.read_bytes(), key.read_bytes(),
            signature.read_bytes(), policy.read_bytes()) == before


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_cli_policy_check_is_bound_and_read_only(trust, capsys):
    archive, key, signature, policy, _, kwargs = trust
    args = [
        "verify-policy-signed-source",
        "--archive", str(archive), "--public-key", str(key),
        "--signature", str(signature), "--policy", str(policy),
        "--expected-archive-sha256", kwargs["expected_archive_sha256"],
        "--expected-manifest-sha256", kwargs["expected_manifest_sha256"],
        "--expected-public-key-sha256", kwargs["expected_public_key_sha256"],
        "--expected-policy-sha256", kwargs["expected_policy_sha256"],
        "--trusted-local-operator",
    ]
    assert run_app_cli(args) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["read_only"] is True
    assert result["release_certified"] is False
    assert run_app_cli(args[:-1]) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_explicitly_revoked_signer_rejected(trust):
    payload = dict(trust[4])
    payload["revoked_key_sha256"] = [trust[5]["expected_public_key_sha256"]]
    pin = _rewrite(trust, payload=payload)
    with pytest.raises(OfflineSourceTrustPolicyError, match="revoked"):
        _check(trust, expected_policy_sha256=pin)


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_unlisted_signer_rejected(trust):
    payload = dict(trust[4])
    payload["authorized_key_sha256"] = ["a" * 64]
    pin = _rewrite(trust, payload=payload)
    with pytest.raises(OfflineSourceTrustPolicyError, match="not authorized"):
        _check(trust, expected_policy_sha256=pin)


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_old_policy_pin_cannot_accept_mutated_policy(trust):
    payload = dict(trust[4])
    payload["epoch"] = 2
    _rewrite(trust, payload=payload)
    with pytest.raises(OfflineSourceTrustPolicyError, match="hash mismatch"):
        _check(trust)


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
@pytest.mark.parametrize("bad", [
    '{"schema":"x","schema":"x"}',
    '{"schema":NaN}',
    "[]",
    "x" * 9000,
])
def test_malformed_ambiguous_or_oversized_policy_fails(trust, bad):
    policy = trust[3]
    policy.write_text(bad, encoding="utf-8")
    policy.chmod(0o600)
    with pytest.raises((OfflineSourceTrustPolicyError, ValueError)):
        _check(trust, expected_policy_sha256=sha256(policy.read_bytes()).hexdigest())


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_symlink_policy_rejected_before_source_admission(trust, tmp_path):
    alias = tmp_path / "alias.json"
    alias.symlink_to(trust[3])
    archive, key, signature, _, _, kwargs = trust
    with pytest.raises((OSError, OfflineSourceTrustPolicyError)):
        verify_policy_signed_offline_source(archive, key, signature, alias, **kwargs)


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_world_readable_policy_rejected(trust):
    trust[3].chmod(0o644)
    with pytest.raises(OfflineSourceTrustPolicyError):
        _check(trust)


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_same_bytes_policy_inode_swap_during_signature_rejected(
    trust, tmp_path, monkeypatch,
):
    import skeleton.app.offline_source_trust_policy as module
    original = module.verify_offline_source_archive_signature
    policy = trust[3]

    def swap(*args, **kwargs):
        replacement = tmp_path / "replacement.json"
        replacement.write_bytes(policy.read_bytes())
        replacement.chmod(0o600)
        os.replace(replacement, policy)
        return original(*args, **kwargs)

    monkeypatch.setattr(module, "verify_offline_source_archive_signature", swap)
    with pytest.raises(OfflineSourceTrustPolicyError, match="changed"):
        _check(trust)


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_authority_rejected_before_policy_read(trust, monkeypatch):
    import skeleton.app.offline_source_trust_policy as module

    def forbidden(*args, **kwargs):
        raise AssertionError("unauthorized policy access")

    monkeypatch.setattr(module, "_read_policy", forbidden)
    with pytest.raises(PermissionError):
        _check(trust, authorized=False)


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_policy_bound_signed_install_replays_real_game(trust, tmp_path):
    archive, key, signature, policy, _, kwargs = trust
    destination = tmp_path / "policy-signed-installed"
    result = install_policy_signed_offline_game_source(
        archive, destination, key, signature, policy, **kwargs,
    )
    assert destination.is_dir()
    assert result["key_authorized_by_pinned_policy"] is True
    assert result["installed_source_archive_binding_verified"] is True
    assert result["offline_gameplay_reexecuted"] is True
    assert result["late_failure_requires_quarantine"] is True
    assert result["release_certified"] is False
    with pytest.raises((FileExistsError, ValueError, OSError)):
        install_policy_signed_offline_game_source(
            archive, destination, key, signature, policy, **kwargs,
        )


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_revoked_signer_cannot_reserve_destination(trust, tmp_path):
    payload = dict(trust[4])
    payload["revoked_key_sha256"] = [trust[5]["expected_public_key_sha256"]]
    pin = _rewrite(trust, payload=payload)
    archive, key, signature, policy, _, kwargs = trust
    destination = tmp_path / "never-reserved"
    with pytest.raises(OfflineSourceTrustPolicyError):
        install_policy_signed_offline_game_source(
            archive, destination, key, signature, policy,
            **{**kwargs, "expected_policy_sha256": pin},
        )
    assert not destination.exists()


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_post_install_policy_replacement_requires_quarantine(
    trust, tmp_path, monkeypatch,
):
    import skeleton.app.offline_policy_signed_install as module
    archive, key, signature, policy, _, kwargs = trust
    original = module.install_signed_offline_game_source
    destination = tmp_path / "quarantine-me"

    def replace_after_install(*args, **inner):
        result = original(*args, **inner)
        replacement = tmp_path / "replacement-policy.json"
        replacement.write_bytes(policy.read_bytes())
        replacement.chmod(0o600)
        os.replace(replacement, policy)
        return result

    monkeypatch.setattr(module, "install_signed_offline_game_source",
                        replace_after_install)
    with pytest.raises(ValueError, match="policy"):
        install_policy_signed_offline_game_source(
            archive, destination, key, signature, policy, **kwargs,
        )
    assert destination.is_dir()
