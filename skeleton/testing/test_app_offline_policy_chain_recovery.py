"""Quarantined original-game recovery under independently pinned signer history."""
from __future__ import annotations

from hashlib import sha256
import json
import os

import pytest

from skeleton.app.cli import run_app_cli
from skeleton.app.offline_policy_chain_recovery import (
    PolicyChainSignedRecoveryError, recover_policy_chain_signed_install,
    preflight_policy_chain_signed_recovery,
)
from skeleton.app.offline_source_trust_policy import SCHEMA as POLICY_SCHEMA
from skeleton.testing.test_app_offline_policy_signed_install_recovery import policy_recovery

pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")


@pytest.fixture
def chain_recovery(policy_recovery, tmp_path):
    data, _ = policy_recovery
    old = tmp_path / "old-recovery-policy.json"
    old.write_text(json.dumps({
        "schema": POLICY_SCHEMA, "epoch": 3,
        "archive_sha256": data["expected_archive_sha256"],
        "manifest_sha256": data["expected_manifest_sha256"],
        "authorized_key_sha256": ["f" * 64],
        "revoked_key_sha256": [],
    }, sort_keys=True), encoding="utf-8")
    old.chmod(0o600)
    return {
        "quarantined_source": data["quarantined_source"],
        "archive": data["archive"],
        "fresh_destination": data["fresh_destination"],
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


def test_read_only_quarantine_recovery_preflight(chain_recovery):
    damaged = (chain_recovery["quarantined_source"] / "index.html").read_bytes()
    receipt = preflight_policy_chain_signed_recovery(**chain_recovery)
    assert receipt["policy_epoch_chain"] == [3, 4]
    assert receipt["original_quarantine_retained"] is True
    assert receipt["destination_reserved"] is False
    assert receipt["read_only"] is True
    assert receipt["release_certified"] is False
    assert not chain_recovery["fresh_destination"].exists()
    assert (chain_recovery["quarantined_source"] / "index.html").read_bytes() == damaged


def test_real_signed_original_game_recovery_preserves_quarantine(chain_recovery):
    damaged = (chain_recovery["quarantined_source"] / "index.html").read_bytes()
    receipt = recover_policy_chain_signed_install(**chain_recovery)
    assert receipt["policy_epoch_chain"] == [3, 4]
    assert receipt["source_archive_signature_verified"] is True
    assert receipt["installed_source_archive_binding_verified"] is True
    assert receipt["offline_gameplay_reexecuted"] is True
    assert receipt["original_quarantine_retained"] is True
    assert receipt["original_quarantine_cleared"] is False
    assert receipt["original_quarantine_mutated"] is False
    assert receipt["automatic_rollback_performed"] is False
    assert receipt["release_certified"] is False
    assert chain_recovery["fresh_destination"].is_dir()
    assert (chain_recovery["quarantined_source"] / "index.html").read_bytes() == damaged


def test_wrong_archive_pin_blocks_recovery(chain_recovery):
    with pytest.raises(ValueError):
        recover_policy_chain_signed_install(**{
            **chain_recovery, "expected_archive_sha256": "0" * 64,
        })
    assert not chain_recovery["fresh_destination"].exists()


def test_final_policy_disallows_signer_before_reservation(chain_recovery):
    final = chain_recovery["policies"][-1]
    payload = json.loads(final.read_text(encoding="utf-8"))
    payload["authorized_key_sha256"] = ["e" * 64]
    final.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    final.chmod(0o600)
    with pytest.raises(PolicyChainSignedRecoveryError, match="not active"):
        recover_policy_chain_signed_install(**{
            **chain_recovery,
            "expected_policy_sha256": [
                chain_recovery["expected_policy_sha256"][0],
                sha256(final.read_bytes()).hexdigest(),
            ],
        })
    assert not chain_recovery["fresh_destination"].exists()


def test_early_policy_swap_after_recovery_keeps_both_directories(
    chain_recovery, tmp_path, monkeypatch,
):
    import skeleton.app.offline_policy_chain_recovery as module
    original = module.recover_policy_signed_install
    old = chain_recovery["policies"][0]

    def swap(*args, **kwargs):
        receipt = original(*args, **kwargs)
        replacement = tmp_path / "replaced-history.json"
        replacement.write_bytes(old.read_bytes())
        replacement.chmod(0o600)
        os.replace(replacement, old)
        return receipt

    monkeypatch.setattr(module, "recover_policy_signed_install", swap)
    with pytest.raises(PolicyChainSignedRecoveryError, match="changed"):
        recover_policy_chain_signed_install(**chain_recovery)
    assert chain_recovery["fresh_destination"].is_dir()
    assert chain_recovery["quarantined_source"].is_dir()


def test_unauthorized_before_policy_read(chain_recovery, monkeypatch):
    import skeleton.app.offline_policy_chain_recovery as module
    monkeypatch.setattr(
        module, "inspect_offline_trust_policy_chain",
        lambda *_a, **_k: pytest.fail("unauthorized read"),
    )
    with pytest.raises(PermissionError):
        recover_policy_chain_signed_install(**{
            **chain_recovery, "authorized": False,
        })


def test_cli_preflight_and_real_recovery(chain_recovery, capsys):
    argv = ["recover-policy-chain-signed-install"]
    for name, key in (
        ("quarantined", "quarantined_source"), ("archive", "archive"),
        ("destination", "fresh_destination"), ("public-key", "public_key_file"),
        ("signature", "signature_file"),
        ("expected-archive-sha256", "expected_archive_sha256"),
        ("expected-manifest-sha256", "expected_manifest_sha256"),
        ("expected-public-key-sha256", "expected_public_key_sha256"),
    ):
        argv += ["--" + name, str(chain_recovery[key])]
    for path, pin in zip(
        chain_recovery["policies"], chain_recovery["expected_policy_sha256"],
    ):
        argv += ["--policy", str(path), "--expected-policy-sha256", pin]
    assert run_app_cli(argv) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"
    assert run_app_cli(argv + ["--trusted-local-operator", "--preflight-only"]) == 0
    assert json.loads(capsys.readouterr().out)["read_only"] is True
    assert run_app_cli(argv + ["--trusted-local-operator"]) == 0
    assert json.loads(capsys.readouterr().out)["offline_gameplay_reexecuted"] is True
