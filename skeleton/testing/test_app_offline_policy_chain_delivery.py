"""Real original-game archive, Ed25519 signature, policy chain and saved replay."""
from __future__ import annotations

from hashlib import sha256
import json
import os

import pytest

from skeleton.app.cli import run_app_cli
from skeleton.app.offline_policy_chain_delivery import (
    PolicyChainSignedDeliveryError, assure_policy_chain_signed_delivery,
)
from skeleton.app.offline_source_trust_policy import SCHEMA as POLICY_SCHEMA
from skeleton.testing.test_app_offline_policy_signed_delivery import delivered
from skeleton.testing.test_app_offline_policy_signed_delivery import policy_migration  # noqa: F401  (transitive fixture)
from skeleton.testing.test_app_offline_policy_signed_progress_migration import migration  # noqa: F401  (transitive fixture)
from skeleton.testing.test_app_offline_signed_progress_migration import signed  # noqa: F401  (transitive fixture)

pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")


@pytest.fixture
def chain_delivery(delivered, tmp_path):
    kwargs, _, _ = delivered
    old = tmp_path / "old-chain-policy.json"
    old_key = "f" * 64
    payload = {
        "schema": POLICY_SCHEMA, "epoch": 2,
        "archive_sha256": kwargs["expected_archive_sha256"],
        "manifest_sha256": kwargs["expected_manifest_sha256"],
        "authorized_key_sha256": [old_key],
        "revoked_key_sha256": [],
    }
    old.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    old.chmod(0o600)
    return {
        "installed_source": kwargs["installed_source"],
        "archive": kwargs["archive"],
        "private_save": kwargs["private_save"],
        "public_key_file": kwargs["public_key_file"],
        "signature_file": kwargs["signature_file"],
        "policies": [old, kwargs["policy_file"]],
        "expected_policy_sha256": [
            sha256(old.read_bytes()).hexdigest(), kwargs["expected_policy_sha256"],
        ],
        "expected_archive_sha256": kwargs["expected_archive_sha256"],
        "expected_manifest_sha256": kwargs["expected_manifest_sha256"],
        "expected_save_sha256": kwargs["expected_save_sha256"],
        "expected_public_key_sha256": kwargs["expected_public_key_sha256"],
        "authorized": True,
    }


def test_real_signed_installed_game_and_private_save_under_policy_chain(chain_delivery):
    save_before = chain_delivery["private_save"].read_bytes()
    policy_before = [p.read_bytes() for p in chain_delivery["policies"]]
    receipt = assure_policy_chain_signed_delivery(**chain_delivery)
    assert receipt["policy_epoch_chain"] == [2, 3]
    assert receipt["policy_transition_count"] == 1
    assert receipt["source_archive_signature_verified"] is True
    assert receipt["installed_source_archive_binding_verified"] is True
    assert receipt["private_save_world_binding_verified"] is True
    assert receipt["offline_gameplay_reexecuted"] is True
    assert receipt["snapshots_unchanged_during_replay"] is True
    assert receipt["native_device_qualified"] is False
    assert receipt["policy_freshness_independently_proven"] is False
    assert receipt["release_certified"] is False
    assert chain_delivery["private_save"].read_bytes() == save_before
    assert [p.read_bytes() for p in chain_delivery["policies"]] == policy_before


def test_wrong_save_pin_blocks_handoff(chain_delivery):
    with pytest.raises(ValueError):
        assure_policy_chain_signed_delivery(**{
            **chain_delivery, "expected_save_sha256": "0" * 64,
        })


def test_missing_signer_in_final_policy_blocks_before_delivery(chain_delivery):
    final = chain_delivery["policies"][-1]
    payload = json.loads(final.read_text(encoding="utf-8"))
    payload["authorized_key_sha256"] = ["e" * 64]
    final.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    final.chmod(0o600)
    with pytest.raises(PolicyChainSignedDeliveryError, match="not active"):
        assure_policy_chain_signed_delivery(**{
            **chain_delivery,
            "expected_policy_sha256": [
                chain_delivery["expected_policy_sha256"][0],
                sha256(final.read_bytes()).hexdigest(),
            ],
        })


def test_old_snapshot_replacement_during_playable_replay_denied(
    chain_delivery, tmp_path, monkeypatch,
):
    import skeleton.app.offline_policy_chain_delivery as module
    original = module.assure_policy_signed_offline_delivery
    old = chain_delivery["policies"][0]

    def replace(*args, **kwargs):
        receipt = original(*args, **kwargs)
        replacement = tmp_path / "replacement-chain.json"
        replacement.write_bytes(old.read_bytes())
        replacement.chmod(0o600)
        os.replace(replacement, old)
        return receipt

    monkeypatch.setattr(module, "assure_policy_signed_offline_delivery", replace)
    with pytest.raises(PolicyChainSignedDeliveryError, match="changed"):
        assure_policy_chain_signed_delivery(**chain_delivery)


def test_no_operator_authority_precedes_any_policy_reads(chain_delivery, monkeypatch):
    import skeleton.app.offline_policy_chain_delivery as module
    monkeypatch.setattr(
        module, "inspect_offline_trust_policy_chain",
        lambda *_a, **_k: pytest.fail("unauthorized policy read"),
    )
    with pytest.raises(PermissionError):
        assure_policy_chain_signed_delivery(**{
            **chain_delivery, "authorized": False,
        })


def test_cli_full_signed_playable_acceptance_and_denial(chain_delivery, capsys):
    argv = ["policy-chain-delivery-assurance"]
    for name, key in (
        ("installed", "installed_source"),
        ("archive", "archive"),
        ("save", "private_save"),
        ("public-key", "public_key_file"),
        ("signature", "signature_file"),
        ("expected-archive-sha256", "expected_archive_sha256"),
        ("expected-manifest-sha256", "expected_manifest_sha256"),
        ("expected-save-sha256", "expected_save_sha256"),
        ("expected-public-key-sha256", "expected_public_key_sha256"),
    ):
        argv += ["--" + name, str(chain_delivery[key])]
    for path, pin in zip(
        chain_delivery["policies"], chain_delivery["expected_policy_sha256"],
    ):
        argv += ["--policy", str(path), "--expected-policy-sha256", pin]
    assert run_app_cli(argv) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"
    assert run_app_cli(argv + ["--trusted-local-operator"]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["offline_gameplay_reexecuted"] is True
    assert receipt["release_certified"] is False
