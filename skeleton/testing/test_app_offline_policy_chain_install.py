"""End-to-end source installation with independently pinned signer history."""
from __future__ import annotations

from hashlib import sha256
import json
import os

import pytest

from skeleton.app.cli import run_app_cli
from skeleton.app.offline_policy_chain_install import (
    PolicyChainSignedInstallError, install_policy_chain_signed_game_source,
)
from skeleton.app.offline_source_trust_policy import SCHEMA as POLICY_SCHEMA
from skeleton.testing.test_app_offline_policy_signed_progress_migration import policy_migration

pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")


@pytest.fixture
def chain_install(policy_migration, tmp_path):
    data, _ = policy_migration
    old = tmp_path / "old-install-policy.json"
    old.write_text(json.dumps({
        "schema": POLICY_SCHEMA, "epoch": 2,
        "archive_sha256": data["expected_archive_sha256"],
        "manifest_sha256": data["expected_manifest_sha256"],
        "authorized_key_sha256": ["f" * 64],
        "revoked_key_sha256": [],
    }, sort_keys=True), encoding="utf-8")
    old.chmod(0o600)
    return {
        "archive": data["archive"],
        "destination": data["destination"],
        "public_key_file": data["public_key_file"],
        "signature_file": data["signature_file"],
        "policies": [old, data["policy_file"]],
        "expected_policy_sha256": [
            sha256(old.read_bytes()).hexdigest(), data["expected_policy_sha256"],
        ],
        "expected_archive_sha256": data["expected_archive_sha256"],
        "expected_manifest_sha256": data["expected_manifest_sha256"],
        "expected_public_key_sha256": data["expected_public_key_sha256"],
        "authorized": True,
    }


def test_real_signed_original_game_install_and_replay(chain_install):
    policy_bytes = [p.read_bytes() for p in chain_install["policies"]]
    receipt = install_policy_chain_signed_game_source(**chain_install)
    assert receipt["policy_epoch_chain"] == [2, 3]
    assert receipt["policy_transition_count"] == 1
    assert receipt["source_archive_signature_verified"] is True
    assert receipt["installed_source_archive_binding_verified"] is True
    assert receipt["offline_gameplay_reexecuted"] is True
    assert receipt["fresh_destination_no_clobber"] is True
    assert receipt["automatic_rollback_performed"] is False
    assert receipt["release_certified"] is False
    assert chain_install["destination"].is_dir()
    assert [p.read_bytes() for p in chain_install["policies"]] == policy_bytes
    with pytest.raises((ValueError, OSError, FileExistsError)):
        install_policy_chain_signed_game_source(**chain_install)


def test_bad_archive_pin_denied_without_destination(chain_install):
    with pytest.raises(ValueError):
        install_policy_chain_signed_game_source(**{
            **chain_install, "expected_archive_sha256": "0" * 64,
        })
    assert not chain_install["destination"].exists()


def test_final_policy_does_not_authorize_signer(chain_install):
    final = chain_install["policies"][-1]
    payload = json.loads(final.read_text(encoding="utf-8"))
    payload["authorized_key_sha256"] = ["e" * 64]
    final.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    final.chmod(0o600)
    with pytest.raises(PolicyChainSignedInstallError, match="not admitted"):
        install_policy_chain_signed_game_source(**{
            **chain_install,
            "expected_policy_sha256": [
                chain_install["expected_policy_sha256"][0],
                sha256(final.read_bytes()).hexdigest(),
            ],
        })
    assert not chain_install["destination"].exists()


def test_old_policy_replaced_after_install_quarantines_destination(
    chain_install, tmp_path, monkeypatch,
):
    import skeleton.app.offline_policy_chain_install as module
    original = module.install_policy_signed_offline_game_source
    old = chain_install["policies"][0]

    def replace(*args, **kwargs):
        receipt = original(*args, **kwargs)
        replacement = tmp_path / "new-inode-policy.json"
        replacement.write_bytes(old.read_bytes())
        replacement.chmod(0o600)
        os.replace(replacement, old)
        return receipt

    monkeypatch.setattr(module, "install_policy_signed_offline_game_source", replace)
    with pytest.raises(PolicyChainSignedInstallError, match="changed"):
        install_policy_chain_signed_game_source(**chain_install)
    assert chain_install["destination"].exists()


def test_unauthorized_operator_denied_before_io(chain_install, monkeypatch):
    import skeleton.app.offline_policy_chain_install as module
    monkeypatch.setattr(
        module, "inspect_offline_trust_policy_chain",
        lambda *_a, **_k: pytest.fail("read before authority"),
    )
    with pytest.raises(PermissionError):
        install_policy_chain_signed_game_source(**{
            **chain_install, "authorized": False,
        })
    assert not chain_install["destination"].exists()


def test_cli_installs_signed_original_game_under_policy_history(chain_install, capsys):
    argv = ["install-policy-chain-signed-source"]
    for name, key in (
        ("archive", "archive"), ("destination", "destination"),
        ("public-key", "public_key_file"), ("signature", "signature_file"),
        ("expected-archive-sha256", "expected_archive_sha256"),
        ("expected-manifest-sha256", "expected_manifest_sha256"),
        ("expected-public-key-sha256", "expected_public_key_sha256"),
    ):
        argv += ["--" + name, str(chain_install[key])]
    for path, pin in zip(
        chain_install["policies"], chain_install["expected_policy_sha256"],
    ):
        argv += ["--policy", str(path), "--expected-policy-sha256", pin]
    assert run_app_cli(argv) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"
    assert not chain_install["destination"].exists()
    assert run_app_cli(argv + ["--trusted-local-operator"]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["offline_gameplay_reexecuted"] is True
    assert receipt["release_certified"] is False
