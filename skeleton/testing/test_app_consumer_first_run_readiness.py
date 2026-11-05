"""Consumer first-run acceptance against actual original-game installation and save."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from skeleton.app.cli import run_app_cli
from skeleton.app.consumer_first_run_readiness import (
    ConsumerFirstRunReadinessError, inspect_consumer_first_run,
)
from skeleton.app.offline_first_playable_delivery import publish_first_playable_delivery
from skeleton.testing.test_app_offline_first_playable_delivery import original_source


@pytest.fixture(scope="module")
def delivered_first_run(original_source, tmp_path_factory):
    root = tmp_path_factory.mktemp("consumer-first-run")
    source, manifest_pin = original_source
    archive = root / "game.zip"
    install = root / "installed"
    save = root / "private-save.json"
    receipt = root / "delivery-receipt.json"
    published = publish_first_playable_delivery(
        source, archive, install, save, receipt,
        expected_manifest_sha256=manifest_pin,
        moves=("up", "right", "down"), authorized=True,
    )
    pins = {
        "expected_manifest_sha256": manifest_pin,
        "expected_archive_sha256": published["archive_sha256"],
        "expected_save_sha256": published["save_sha256"],
        "expected_receipt_sha256": published["independent_receipt_sha256"],
        "authorized": True,
    }
    return (install, archive, save, receipt), pins


def test_real_installed_game_and_private_save_replayed_without_release_claim(
    delivered_first_run,
):
    paths, pins = delivered_first_run
    before = tuple(path.read_bytes() for path in paths[1:])
    result = inspect_consumer_first_run(*paths, **pins)
    assert result["schema"] == "skeleton.app.consumer_first_run_evidence.v1"
    assert result["status"] == "source_level_first_run_replayed_release_blocked"
    assert result["source_level_replay_passes"] == 2
    assert result["installed_game_and_private_save_reexecuted"] is True
    assert result["all_input_inodes_stable_during_inspection"] is False
    assert result["root_and_evidence_inodes_stable_during_inspection"] is True
    assert result["nested_asset_inode_inventory_attested"] is True
    assert result["nested_asset_inode_snapshots_equal"] is True
    assert len(result["installed_tree_snapshot_sha256"]) == 64
    assert "PERSISTENT_NESTED_ASSET_CUSTODY_UNQUALIFIED" in result["release_holds"]
    assert result["read_only"] is True
    assert result["files_published"] == 0
    assert result["action_count"] == 3
    assert result["manifest_sha256"] == pins["expected_manifest_sha256"]
    assert result["receipt_sha256"] == pins["expected_receipt_sha256"]
    assert result["release_holds"]
    for key in (
        "native_device_qualified", "native_godot_executed",
        "windows_laptop_qualified", "installer_qualified",
        "guarded_local_ai_qualified", "package_signed",
        "rights_certified", "persistent_rollback_protection",
        "release_certified",
    ):
        assert result[key] is False
    assert before == tuple(path.read_bytes() for path in paths[1:])


def test_cli_replays_real_delivery_and_rejects_missing_operator_acknowledgement(
    delivered_first_run, capsys,
):
    paths, pins = delivered_first_run
    install, archive, save, receipt = paths
    args = [
        "consumer-first-run-readiness", "--installed", str(install),
        "--archive", str(archive), "--save", str(save),
        "--receipt", str(receipt),
        "--expected-manifest-sha256", pins["expected_manifest_sha256"],
        "--expected-archive-sha256", pins["expected_archive_sha256"],
        "--expected-save-sha256", pins["expected_save_sha256"],
        "--expected-receipt-sha256", pins["expected_receipt_sha256"],
    ]
    assert run_app_cli(args) == 2
    denied = json.loads(capsys.readouterr().err)
    assert denied["status"] == "blocked"
    assert denied["release_certified"] is False
    assert run_app_cli(args + ["--trusted-local-operator"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["source_level_replay_passes"] == 2
    assert result["native_device_qualified"] is False
    assert result["release_certified"] is False


@pytest.mark.parametrize("pin_name", [
    "expected_manifest_sha256", "expected_archive_sha256",
    "expected_save_sha256", "expected_receipt_sha256",
])
def test_each_independent_pin_must_match(delivered_first_run, pin_name):
    paths, pins = delivered_first_run
    with pytest.raises(ValueError):
        inspect_consumer_first_run(
            *paths, **{**pins, pin_name: "0" * 64},
        )


def test_untrusted_or_noncanonical_pins_fail_closed(delivered_first_run):
    paths, pins = delivered_first_run
    with pytest.raises(PermissionError):
        inspect_consumer_first_run(*paths, **{**pins, "authorized": False})
    with pytest.raises(ValueError):
        inspect_consumer_first_run(*paths, **{
            **pins, "expected_receipt_sha256":
                "A" * 64,
        })


def test_same_byte_receipt_inode_swap_during_first_replay_rejected(
    delivered_first_run, tmp_path, monkeypatch,
):
    from skeleton.app import consumer_first_run_readiness as module

    paths, pins = delivered_first_run
    install, archive, save, receipt = paths
    isolated_receipt = tmp_path / "receipt.json"
    isolated_receipt.write_bytes(receipt.read_bytes())
    isolated_receipt.chmod(0o600)
    original = module.inspect_first_playable_delivery
    changed = False

    def swap(*args, **kwargs):
        nonlocal changed
        result = original(*args, **kwargs)
        if not changed:
            changed = True
            new_inode = tmp_path / "replacement.json"
            new_inode.write_bytes(isolated_receipt.read_bytes())
            new_inode.chmod(0o600)
            os.replace(new_inode, isolated_receipt)
        return result

    monkeypatch.setattr(module, "inspect_first_playable_delivery", swap)
    with pytest.raises(ConsumerFirstRunReadinessError, match="changed"):
        inspect_consumer_first_run(
            install, archive, save, isolated_receipt, **pins,
        )


def test_forged_release_claim_from_canonical_adapter_rejected(
    delivered_first_run, monkeypatch,
):
    from skeleton.app import consumer_first_run_readiness as module

    paths, pins = delivered_first_run
    original = module.inspect_first_playable_delivery

    def forged(*args, **kwargs):
        return {**original(*args, **kwargs), "release_certified": True}

    monkeypatch.setattr(module, "inspect_first_playable_delivery", forged)
    with pytest.raises(ConsumerFirstRunReadinessError, match="contracts"):
        inspect_consumer_first_run(*paths, **pins)


def test_same_byte_nested_asset_swap_during_consumer_replay_fails_closed(
    delivered_first_run, tmp_path, monkeypatch,
):
    import shutil
    from skeleton.app import consumer_first_run_readiness as module

    paths, pins = delivered_first_run
    original_install, archive, save, receipt = paths
    isolated_install = tmp_path / "installed"
    shutil.copytree(original_install, isolated_install)
    target = isolated_install / "godot" / "scripts" / "main.gd"
    original = module.inspect_first_playable_delivery
    changed = False

    def swap_nested_asset(*args, **kwargs):
        nonlocal changed
        result = original(*args, **kwargs)
        if not changed:
            changed = True
            replacement = tmp_path / "replacement.gd"
            replacement.write_bytes(target.read_bytes())
            replacement.chmod(target.stat().st_mode & 0o777)
            os.replace(replacement, target)
        return result

    monkeypatch.setattr(
        module, "inspect_first_playable_delivery", swap_nested_asset,
    )
    with pytest.raises(ConsumerFirstRunReadinessError, match="changed"):
        inspect_consumer_first_run(
            isolated_install, archive, save, receipt, **pins,
        )


def test_same_inode_receipt_parent_directory_swap_rejected(
    delivered_first_run, tmp_path, monkeypatch,
):
    from skeleton.app import consumer_first_run_readiness as module

    paths, pins = delivered_first_run
    install, archive, save, original_receipt = paths
    parent = tmp_path / "private-receipt"
    parent.mkdir(mode=0o700)
    receipt = parent / "receipt.json"
    receipt.write_bytes(original_receipt.read_bytes())
    receipt.chmod(0o600)
    before = receipt.stat()
    original = module.inspect_first_playable_delivery
    swapped = False

    def replace_parent_after_first_replay(*args, **kwargs):
        nonlocal swapped
        result = original(*args, **kwargs)
        if not swapped:
            swapped = True
            old_parent = tmp_path / "retired-receipt-parent"
            os.rename(parent, old_parent)
            parent.mkdir(mode=0o700)
            os.rename(old_parent / receipt.name, receipt)
            # Same bytes and SAME file inode, but a different directory
            # inode now controls the evidence pathname.
            assert receipt.stat().st_ino == before.st_ino
            assert receipt.read_bytes() == original_receipt.read_bytes()
        return result

    monkeypatch.setattr(
        module, "inspect_first_playable_delivery",
        replace_parent_after_first_replay,
    )
    with pytest.raises(ConsumerFirstRunReadinessError, match="changed"):
        inspect_consumer_first_run(
            install, archive, save, receipt, **pins,
        )
