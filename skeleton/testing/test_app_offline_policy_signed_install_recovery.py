"""Real quarantine -> pinned policy -> signed original source -> fresh replay."""
from __future__ import annotations

from hashlib import sha256
import json
import os

import pytest

from skeleton.app.cli import run_app_cli
from skeleton.app.offline_policy_signed_install_recovery import (
    preflight_policy_signed_install_recovery, recover_policy_signed_install,
)
from skeleton.app.offline_source_trust_policy import SCHEMA
from skeleton.testing.test_app_offline_signed_install_recovery import recovery


@pytest.fixture
def policy_recovery(recovery, tmp_path):
    partial, archive, archive_pin, manifest_pin, key, signature, key_pin, fresh = recovery
    payload = {
        "schema": SCHEMA,
        "epoch": 4,
        "archive_sha256": archive_pin,
        "manifest_sha256": manifest_pin,
        "authorized_key_sha256": [key_pin],
        "revoked_key_sha256": [],
    }
    policy = tmp_path / "recovery-trust.json"
    policy.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    policy.chmod(0o600)
    return {
        "quarantined_source": partial,
        "archive": archive,
        "fresh_destination": fresh,
        "public_key_file": key,
        "signature_file": signature,
        "policy_file": policy,
        "expected_archive_sha256": archive_pin,
        "expected_manifest_sha256": manifest_pin,
        "expected_public_key_sha256": key_pin,
        "expected_policy_sha256": sha256(policy.read_bytes()).hexdigest(),
        "authorized": True,
    }, payload


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_policy_signed_recovery_preflight_read_only(policy_recovery):
    data, _ = policy_recovery
    before = (data["quarantined_source"] / "index.html").read_bytes()
    result = preflight_policy_signed_install_recovery(**data)
    assert result["destination_reserved"] is False
    assert result["original_quarantine_retained"] is True
    assert result["original_quarantine_cleared"] is False
    assert result["read_only"] is True
    assert result["release_certified"] is False
    assert not data["fresh_destination"].exists()
    assert (data["quarantined_source"] / "index.html").read_bytes() == before


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_policy_signed_recovery_replays_fresh_game(policy_recovery):
    data, _ = policy_recovery
    before = (data["quarantined_source"] / "index.html").read_bytes()
    result = recover_policy_signed_install(**data)
    assert result["key_authorized_by_pinned_policy"] is True
    assert result["source_archive_signature_verified"] is True
    assert result["installed_source_archive_binding_verified"] is True
    assert result["offline_gameplay_reexecuted"] is True
    assert result["original_quarantine_retained"] is True
    assert result["original_quarantine_cleared"] is False
    assert result["late_failure_requires_quarantine"] is True
    assert result["release_certified"] is False
    assert data["fresh_destination"].is_dir()
    assert (data["quarantined_source"] / "index.html").read_bytes() == before


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_revocation_denies_recovery_before_reservation(policy_recovery):
    data, payload = policy_recovery
    payload["revoked_key_sha256"] = [data["expected_public_key_sha256"]]
    data["policy_file"].write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    data["policy_file"].chmod(0o600)
    data["expected_policy_sha256"] = sha256(data["policy_file"].read_bytes()).hexdigest()
    with pytest.raises(ValueError):
        recover_policy_signed_install(**data)
    assert not data["fresh_destination"].exists()


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_policy_swap_after_recovery_keeps_quarantine(
    policy_recovery, tmp_path, monkeypatch,
):
    import skeleton.app.offline_policy_signed_install_recovery as module
    data, _ = policy_recovery
    original = module.recover_signed_offline_game_install
    policy = data["policy_file"]

    def swap(*args, **kwargs):
        result = original(*args, **kwargs)
        replacement = tmp_path / "same-policy.json"
        replacement.write_bytes(policy.read_bytes())
        replacement.chmod(0o600)
        os.replace(replacement, policy)
        return result

    monkeypatch.setattr(module, "recover_signed_offline_game_install", swap)
    with pytest.raises(ValueError):
        recover_policy_signed_install(**data)
    assert data["fresh_destination"].is_dir()
    assert data["quarantined_source"].is_dir()


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_no_authority_before_policy_access(policy_recovery, monkeypatch):
    import skeleton.app.offline_policy_signed_install_recovery as module
    data, _ = policy_recovery

    def forbidden(*args, **kwargs):
        raise AssertionError("unauthorized policy read")

    monkeypatch.setattr(module, "_read_policy", forbidden)
    with pytest.raises(PermissionError):
        recover_policy_signed_install(**{**data, "authorized": False})
    assert not data["fresh_destination"].exists()


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_cli_preflight_and_authority_denial(policy_recovery, capsys):
    data, _ = policy_recovery
    args = ["recover-policy-signed-install"]
    for name, key in (
        ("quarantined", "quarantined_source"), ("archive", "archive"),
        ("destination", "fresh_destination"), ("public-key", "public_key_file"),
        ("signature", "signature_file"), ("policy", "policy_file"),
        ("expected-archive-sha256", "expected_archive_sha256"),
        ("expected-manifest-sha256", "expected_manifest_sha256"),
        ("expected-public-key-sha256", "expected_public_key_sha256"),
        ("expected-policy-sha256", "expected_policy_sha256"),
    ):
        args.extend(["--" + name, str(data[key])])
    assert run_app_cli(args + ["--preflight-only"]) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"
    assert run_app_cli(args + ["--preflight-only", "--trusted-local-operator"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["destination_reserved"] is False
    assert result["release_certified"] is False
