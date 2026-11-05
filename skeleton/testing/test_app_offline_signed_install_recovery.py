"""End-to-end signed quarantine -> fresh original game -> replay acceptance."""
from __future__ import annotations

import json
import os

import pytest

from skeleton.app.cli import run_app_cli
from skeleton.app.offline_signed_install_recovery import (
    SignedOfflineInstallRecoveryError, recover_signed_offline_game_install,
)
from skeleton.testing.test_app_offline_archive_signature import signed


@pytest.fixture
def recovery(signed, tmp_path):
    archive, archive_pin, manifest_pin, key, signature, key_pin = signed
    partial = tmp_path / "quarantined-source"
    partial.mkdir(mode=0o700)
    (partial / "index.html").write_bytes(b"damaged-original-source")
    (partial / "index.html").chmod(0o600)
    fresh = tmp_path / "signed-fresh-install"
    return partial, archive, archive_pin, manifest_pin, key, signature, key_pin, fresh


def _call(bundle, **overrides):
    partial, archive, archive_pin, manifest_pin, key, signature, key_pin, fresh = bundle
    kwargs = {
        "quarantined_source": partial,
        "archive": archive,
        "fresh_destination": fresh,
        "public_key_file": key,
        "signature_file": signature,
        "expected_archive_sha256": archive_pin,
        "expected_manifest_sha256": manifest_pin,
        "expected_public_key_sha256": key_pin,
        "authorized": True,
    }
    kwargs.update(overrides)
    return recover_signed_offline_game_install(**kwargs)


def _cli(bundle):
    partial, archive, archive_pin, manifest_pin, key, signature, key_pin, fresh = bundle
    return [
        "recover-signed-install",
        "--quarantined", str(partial),
        "--archive", str(archive),
        "--destination", str(fresh),
        "--public-key", str(key),
        "--signature", str(signature),
        "--expected-archive-sha256", archive_pin,
        "--expected-manifest-sha256", manifest_pin,
        "--expected-public-key-sha256", key_pin,
        "--trusted-local-operator",
    ]


@pytest.mark.skipif(os.name != "posix", reason="POSIX nofollow custody")
def test_real_signed_recovery_replays_game_without_mutating_quarantine(recovery, capsys):
    partial, archive, _, manifest_pin, key, signature, _, fresh = recovery
    before = (
        (partial / "index.html").read_bytes(),
        archive.read_bytes(), key.read_bytes(), signature.read_bytes(),
    )
    assert run_app_cli(_cli(recovery)) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["source_archive_signature_verified"] is True
    assert receipt["installed_source_archive_binding_verified"] is True
    assert receipt["offline_gameplay_reexecuted"] is True
    assert receipt["original_quarantine_retained"] is True
    assert receipt["original_quarantine_cleared"] is False
    assert receipt["automatic_rollback_performed"] is False
    assert receipt["quarantined_mismatched_files"] >= 1
    assert receipt["native_device_qualified"] is False
    assert receipt["package_signed"] is False
    assert receipt["release_certified"] is False
    assert fresh.is_dir()
    assert (fresh / "release.json").is_file()
    assert run_app_cli([
        "studio-journey", "--play-existing", "--output", str(fresh),
        "--expected-manifest-sha256", manifest_pin,
        "--moves", "up,right", "--trusted-local-operator",
    ]) == 0
    assert json.loads(capsys.readouterr().out)["offline_gameplay_reexecuted"] is True
    assert (
        (partial / "index.html").read_bytes(),
        archive.read_bytes(), key.read_bytes(), signature.read_bytes(),
    ) == before


@pytest.mark.skipif(os.name != "posix", reason="POSIX nofollow custody")
@pytest.mark.parametrize("pin", ["archive", "manifest", "public_key"])
def test_wrong_independent_pin_does_not_reserve_destination(recovery, pin):
    with pytest.raises(ValueError):
        _call(recovery, **{"expected_" + pin + "_sha256": "0" * 64})
    assert not recovery[-1].exists()


@pytest.mark.skipif(os.name != "posix", reason="POSIX nofollow custody")
@pytest.mark.parametrize("kind", ["archive", "key", "signature"])
def test_tampered_signed_material_fails_before_reservation(recovery, kind):
    path = {"archive": recovery[1], "key": recovery[4], "signature": recovery[5]}[kind]
    raw = path.read_bytes()
    path.write_bytes(bytes([raw[0] ^ 1]) + raw[1:])
    with pytest.raises(ValueError):
        _call(recovery)
    assert not recovery[-1].exists()


@pytest.mark.skipif(os.name != "posix", reason="POSIX nofollow custody")
def test_existing_destination_is_never_overwritten(recovery):
    fresh = recovery[-1]
    fresh.mkdir(mode=0o700)
    marker = fresh / "keep.txt"
    marker.write_text("private", encoding="utf-8")
    with pytest.raises(ValueError):
        _call(recovery)
    assert marker.read_text(encoding="utf-8") == "private"


@pytest.mark.skipif(os.name != "posix", reason="POSIX nofollow custody")
@pytest.mark.parametrize("where", ["same", "child", "parent"])
def test_nested_destination_is_rejected_before_mutation(recovery, where):
    partial = recovery[0]
    target = {"same": partial, "child": partial / "new",
              "parent": partial.parent}[where]
    with pytest.raises(SignedOfflineInstallRecoveryError):
        _call(recovery, fresh_destination=target)
    assert not (partial / "new").exists()


@pytest.mark.skipif(os.name != "posix", reason="POSIX nofollow custody")
def test_unauthorized_call_never_reads_quarantine(recovery, monkeypatch):
    import skeleton.app.offline_signed_install_recovery as module

    def unexpected(*args, **kwargs):
        raise AssertionError("unauthorized filesystem access")

    monkeypatch.setattr(module, "_custody", unexpected)
    with pytest.raises(PermissionError):
        _call(recovery, authorized=False)
    assert not recovery[-1].exists()


@pytest.mark.skipif(os.name != "posix", reason="POSIX nofollow custody")
def test_quarantine_symlink_root_is_rejected(recovery, tmp_path):
    alias = tmp_path / "quarantine-alias"
    alias.symlink_to(recovery[0], target_is_directory=True)
    with pytest.raises((ValueError, OSError)):
        _call(recovery, quarantined_source=alias)
    assert not recovery[-1].exists()


@pytest.mark.skipif(os.name != "posix", reason="POSIX nofollow custody")
def test_same_byte_signature_inode_swap_after_install_fails_closed(recovery, tmp_path, monkeypatch):
    import skeleton.app.offline_signed_install_recovery as module
    original = module.recover_quarantined_offline_install
    signature = recovery[5]

    def swap_after_recovery(*args, **kwargs):
        receipt = original(*args, **kwargs)
        replacement = tmp_path / "replacement.sig"
        replacement.write_bytes(signature.read_bytes())
        replacement.chmod(0o600)
        os.replace(replacement, signature)
        return receipt

    monkeypatch.setattr(module, "recover_quarantined_offline_install", swap_after_recovery)
    with pytest.raises(SignedOfflineInstallRecoveryError):
        _call(recovery)
    assert recovery[-1].is_dir()
    assert recovery[0].is_dir()


@pytest.mark.skipif(os.name != "posix", reason="POSIX nofollow custody")
def test_quarantine_mutation_after_install_fails_closed_without_rollback(
    recovery, monkeypatch,
):
    import skeleton.app.offline_signed_install_recovery as module
    original = module.recover_quarantined_offline_install

    def mutate_after_recovery(*args, **kwargs):
        receipt = original(*args, **kwargs)
        (recovery[0] / "index.html").write_bytes(b"changed-after-recovery")
        return receipt

    monkeypatch.setattr(module, "recover_quarantined_offline_install",
                        mutate_after_recovery)
    with pytest.raises((SignedOfflineInstallRecoveryError, ValueError)):
        _call(recovery)
    assert recovery[-1].is_dir()
    assert recovery[0].is_dir()


@pytest.mark.skipif(os.name != "posix", reason="POSIX nofollow custody")
def test_cli_without_operator_acknowledgement_is_blocked(recovery, capsys):
    args = _cli(recovery)
    args.remove("--trusted-local-operator")
    assert run_app_cli(args) == 2
    receipt = json.loads(capsys.readouterr().err)
    assert receipt["status"] == "blocked"
    assert receipt["release_certified"] is False
    assert not recovery[-1].exists()

@pytest.mark.skipif(os.name != "posix", reason="POSIX nofollow custody")
def test_read_only_signed_recovery_preflight_does_not_reserve(recovery, capsys):
    args = _cli(recovery) + ["--preflight-only"]
    before = (recovery[0] / "index.html").read_bytes()
    assert run_app_cli(args) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["schema"] == "skeleton.app.signed_offline_install_recovery_preflight.v1"
    assert receipt["source_archive_signature_verified"] is True
    assert receipt["destination_reserved"] is False
    assert receipt["source_installation_verified"] is False
    assert receipt["read_only"] is True
    assert receipt["release_certified"] is False
    assert not recovery[-1].exists()
    assert (recovery[0] / "index.html").read_bytes() == before


@pytest.mark.skipif(os.name != "posix", reason="POSIX nofollow custody")
def test_preflight_wrong_key_pin_never_reserves(recovery, capsys):
    args = _cli(recovery) + ["--preflight-only"]
    pos = args.index("--expected-public-key-sha256") + 1
    args[pos] = "0" * 64
    assert run_app_cli(args) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"
    assert not recovery[-1].exists()
