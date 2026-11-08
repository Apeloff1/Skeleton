"""Live source -> archive -> install -> move -> save -> restore -> pinned handoff."""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path

import pytest

from skeleton.ai.game_builder.playable_world import GameBuildIntent
from skeleton.app.cli import run_app_cli
from skeleton.app.offline_first_playable_delivery import (
    FirstPlayableDeliveryAcceptanceError,
    inspect_first_playable_delivery,
    publish_first_playable_delivery,
)
from skeleton.app.private_game_save import (
    PrivateGameSaveError, publish_private_game_save,
)
from skeleton.app.studio_journey import build_first_playable_journey


@pytest.fixture(scope="module")
def original_source(tmp_path_factory):
    root = tmp_path_factory.mktemp("first-playable-delivery-source")
    output = root / "original-game"
    intent = GameBuildIntent(
        project_id="first-delivery-001",
        title="Original Quiet Harbor",
        subtitle="A private source-bound adventure",
        seed=1729, levels=1, width=9, height=9,
        collectibles_per_level=1, hazards_per_level=0,
        starting_health=3,
    )
    built = build_first_playable_journey(
        intent, output, authorized=True, mirror_attempts=64,
    )
    assert built["offline_gameplay_reexecuted"] is True
    pin = sha256((output / "release.json").read_bytes()).hexdigest()
    assert pin == built["trusted_in_process_manifest_sha256"]
    return output, pin


def _destinations(root: Path):
    return (
        root / "original.zip",
        root / "fresh-install",
        root / "progress.json",
        root / "delivery.json",
    )


def _publish(original_source, tmp_path):
    source, pin = original_source
    archive, install, save, receipt = _destinations(tmp_path)
    result = publish_first_playable_delivery(
        source, archive, install, save, receipt,
        expected_manifest_sha256=pin,
        moves=("up", "right", "down"), authorized=True,
    )
    return result, (archive, install, save, receipt), pin


def test_full_real_original_game_delivery_and_independent_reinspection(
    original_source, tmp_path,
):
    published, paths, pin = _publish(original_source, tmp_path)
    archive, install, save, receipt = paths
    assert published["status"] == "fresh_original_game_delivered_replayed_release_blocked"
    assert published["project_id"] == "first-delivery-001"
    assert published["action_count"] == 3
    assert published["offline_gameplay_reexecuted"] is True
    assert published["native_device_qualified"] is False
    assert published["package_signed"] is False
    assert published["rights_certified"] is False
    assert published["release_certified"] is False
    assert published["independent_pin_distribution_required"] is True
    assert archive.is_file() and save.is_file() and receipt.is_file()
    assert (install / "release.json").is_file()
    assert (install / "index.html").is_file()
    assert (install / "godot" / "project.godot").is_file()
    checked = inspect_first_playable_delivery(
        install, archive, save, receipt,
        expected_manifest_sha256=pin,
        expected_archive_sha256=published["archive_sha256"],
        expected_save_sha256=published["save_sha256"],
        expected_receipt_sha256=published["independent_receipt_sha256"],
        authorized=True,
    )
    assert checked["receipt_integrity_verified"] is True
    assert checked["independent_pin_reverified"] is True
    assert checked["live_source_and_private_replay_reexecuted"] is True
    assert checked["replay_digest"] == published["replay_digest"]
    assert checked["read_only"] is True
    assert checked["release_certified"] is False


def test_cli_publish_and_inspect_actual_live_delivery(
    original_source, tmp_path, capsys,
):
    source, pin = original_source
    archive, install, save, receipt = _destinations(tmp_path)
    command = [
        "first-playable-delivery", "--source", str(source),
        "--archive", str(archive), "--install", str(install),
        "--save", str(save), "--receipt", str(receipt),
        "--expected-manifest-sha256", pin,
        "--moves", "up,right", "--trusted-local-operator",
    ]
    assert run_app_cli(command) == 0
    published = json.loads(capsys.readouterr().out)
    assert published["action_count"] == 2
    assert run_app_cli([
        "first-playable-delivery", "--inspect",
        "--archive", str(archive), "--install", str(install),
        "--save", str(save), "--receipt", str(receipt),
        "--expected-manifest-sha256", pin,
        "--expected-archive-sha256", published["archive_sha256"],
        "--expected-save-sha256", published["save_sha256"],
        "--expected-receipt-sha256", published["independent_receipt_sha256"],
        "--trusted-local-operator",
    ]) == 0
    inspected = json.loads(capsys.readouterr().out)
    assert inspected["live_source_and_private_replay_reexecuted"] is True
    assert inspected["release_certified"] is False


def test_missing_authorization_rejects_before_any_output(
    original_source, tmp_path,
):
    source, pin = original_source
    paths = _destinations(tmp_path)
    with pytest.raises(PermissionError):
        publish_first_playable_delivery(
            source, *paths, expected_manifest_sha256=pin,
            moves=("up",), authorized=False,
        )
    assert all(not item.exists() for item in paths)


@pytest.mark.parametrize("moves", [
    (), ("wait",), ("up",) * 65, ("up", 1), "up", ("UP",),
])
def test_invalid_moves_fail_before_any_output(
    original_source, tmp_path, moves,
):
    source, pin = original_source
    paths = _destinations(tmp_path)
    with pytest.raises(FirstPlayableDeliveryAcceptanceError):
        publish_first_playable_delivery(
            source, *paths, expected_manifest_sha256=pin,
            moves=moves, authorized=True,
        )
    assert all(not item.exists() for item in paths)


def test_archive_collision_blocks_before_install_or_save(
    original_source, tmp_path,
):
    source, pin = original_source
    paths = _destinations(tmp_path)
    paths[0].write_bytes(b"operator-owned")
    with pytest.raises(FirstPlayableDeliveryAcceptanceError):
        publish_first_playable_delivery(
            source, *paths, expected_manifest_sha256=pin,
            moves=("up",), authorized=True,
        )
    assert paths[0].read_bytes() == b"operator-owned"
    assert all(not item.exists() for item in paths[1:])


def test_output_inside_source_tree_rejected_before_any_write(
    original_source, tmp_path,
):
    source, pin = original_source
    archive, install, save, receipt = _destinations(tmp_path)
    with pytest.raises(FirstPlayableDeliveryAcceptanceError):
        publish_first_playable_delivery(
            source, source / "bad.zip", install, save, receipt,
            expected_manifest_sha256=pin, moves=("up",), authorized=True,
        )
    assert not (source / "bad.zip").exists()
    assert all(not item.exists() for item in (install, save, receipt))


def test_wrong_manifest_pin_fails_without_publication(
    original_source, tmp_path,
):
    source, _ = original_source
    paths = _destinations(tmp_path)
    with pytest.raises(ValueError):
        publish_first_playable_delivery(
            source, *paths, expected_manifest_sha256="0" * 64,
            moves=("up",), authorized=True,
        )
    assert all(not item.exists() for item in paths)


def test_symlinked_archive_parent_rejected_before_any_output(
    original_source, tmp_path,
):
    source, pin = original_source
    real = tmp_path / "private"
    real.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(real, target_is_directory=True)
    archive, install, save, receipt = _destinations(tmp_path)
    with pytest.raises(ValueError):
        publish_first_playable_delivery(
            source, alias / "game.zip", install, save, receipt,
            expected_manifest_sha256=pin, moves=("up",), authorized=True,
        )
    assert not (real / "game.zip").exists()
    assert all(not item.exists() for item in (install, save, receipt))


def test_reinspection_rejects_wrong_pin_and_modified_receipt(
    original_source, tmp_path,
):
    published, paths, pin = _publish(original_source, tmp_path)
    archive, install, save, receipt = paths
    options = dict(
        expected_manifest_sha256=pin,
        expected_archive_sha256=published["archive_sha256"],
        expected_save_sha256=published["save_sha256"],
        expected_receipt_sha256=published["independent_receipt_sha256"],
        authorized=True,
    )
    with pytest.raises(ValueError):
        inspect_first_playable_delivery(
            install, archive, save, receipt,
            **{**options, "expected_archive_sha256": "0" * 64},
        )
    with pytest.raises(ValueError):
        inspect_first_playable_delivery(
            install, archive, save, receipt,
            **{**options, "expected_receipt_sha256": "0" * 64},
        )
    receipt.write_bytes(b"{}")
    with pytest.raises(ValueError):
        inspect_first_playable_delivery(
            install, archive, save, receipt, **options,
        )


def test_cli_inspect_rejects_unpinned_or_mixed_mode(
    original_source, tmp_path, capsys,
):
    source, pin = original_source
    archive, install, save, receipt = _destinations(tmp_path)
    base = [
        "first-playable-delivery", "--archive", str(archive),
        "--install", str(install), "--save", str(save),
        "--receipt", str(receipt),
        "--expected-manifest-sha256", pin,
        "--trusted-local-operator",
    ]
    assert run_app_cli(base + ["--inspect"]) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"
    assert run_app_cli(base + ["--source", str(source), "--moves", "up",
                               "--expected-save-sha256", "0" * 64]) == 2
    assert json.loads(capsys.readouterr().err)["release_certified"] is False
    assert all(not item.exists() for item in (archive, install, save, receipt))


def test_private_save_post_link_fsync_failure_never_unlinks_published_name(
    tmp_path, monkeypatch,
):
    from skeleton.app import private_game_save as module

    target = tmp_path / "save.json"
    actual_fsync = os.fsync
    calls = 0

    def fail_second_fsync(fd):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated parent durability uncertainty")
        return actual_fsync(fd)

    monkeypatch.setattr(module.os, "fsync", fail_second_fsync)
    with pytest.raises(PrivateGameSaveError):
        publish_private_game_save(
            b'{"replay":"private"}', target,
            protected_roots=(), authorized=True,
        )
    assert target.read_bytes() == b'{"replay":"private"}'
    assert calls >= 2
    with pytest.raises(ValueError):
        publish_private_game_save(
            b'{"replay":"different"}', target,
            protected_roots=(), authorized=True,
        )
    assert target.read_bytes() == b'{"replay":"private"}'


def test_dotdot_archive_alias_into_original_source_fails_before_publication(
    original_source, tmp_path,
):
    """Existing sibling/.. must not bypass source/output separation."""
    source, pin = original_source
    sibling = tmp_path / "existing-sibling"
    sibling.mkdir()
    archive, install, save, receipt = _destinations(tmp_path)
    disguised = sibling / ".." / source.name / "poison.zip"
    with pytest.raises(FirstPlayableDeliveryAcceptanceError, match="outside"):
        publish_first_playable_delivery(
            source, disguised, install, save, receipt,
            expected_manifest_sha256=pin, moves=("up",), authorized=True,
        )
    assert not (source / "poison.zip").exists()
    assert all(not path.exists() for path in (archive, install, save, receipt))


def test_dotdot_install_alias_into_original_source_fails_before_publication(
    original_source, tmp_path,
):
    source, pin = original_source
    sibling = tmp_path / "existing-sibling"
    sibling.mkdir()
    archive, install, save, receipt = _destinations(tmp_path)
    disguised = sibling / ".." / source.name / "new-install"
    with pytest.raises(FirstPlayableDeliveryAcceptanceError, match="disjoint"):
        publish_first_playable_delivery(
            source, archive, disguised, save, receipt,
            expected_manifest_sha256=pin, moves=("up",), authorized=True,
        )
    assert not (source / "new-install").exists()
    assert all(not path.exists() for path in (archive, install, save, receipt))


@pytest.mark.parametrize("swap_on", [1, 2])
def test_identical_byte_source_root_swap_during_preflight_fails_before_write(
    original_source, tmp_path, monkeypatch, swap_on,
):
    """Two matching game hashes do not excuse an inode substitution."""
    import shutil
    from skeleton.app import offline_first_playable_delivery as module

    source = tmp_path / "original-copy"
    replacement = tmp_path / "replacement"
    shutil.copytree(original_source[0], source)
    shutil.copytree(original_source[0], replacement)
    old = tmp_path / "old-source"
    archive, install, save, receipt = _destinations(tmp_path)
    original_verify = module.verify_exported_package
    calls = 0

    def replace_after_replay(*args, **kwargs):
        nonlocal calls
        observed = original_verify(*args, **kwargs)
        calls += 1
        if calls == swap_on:
            source.rename(old)
            replacement.rename(source)
        return observed

    monkeypatch.setattr(module, "verify_exported_package", replace_after_replay)
    with pytest.raises(
        FirstPlayableDeliveryAcceptanceError, match="source root changed",
    ):
        publish_first_playable_delivery(
            source, archive, install, save, receipt,
            expected_manifest_sha256=original_source[1],
            moves=("up", "right"), authorized=True,
        )
    assert calls == swap_on
    assert all(not item.exists() for item in (archive, install, save, receipt))
    assert old.is_dir() and source.is_dir()


def test_archive_publication_source_swap_blocks_install_and_preserves_zip(
    original_source, tmp_path, monkeypatch,
):
    """A published archive stays quarantined; no new install follows a swap."""
    import shutil
    from skeleton.app import offline_first_playable_delivery as module

    source = tmp_path / "original-copy"
    replacement = tmp_path / "replacement"
    shutil.copytree(original_source[0], source)
    shutil.copytree(original_source[0], replacement)
    archive, install, save, receipt = _destinations(tmp_path)
    original_publisher = module.publish_offline_game_archive

    def replace_after_archive(*args, **kwargs):
        published = original_publisher(*args, **kwargs)
        source.rename(tmp_path / "old-source")
        replacement.rename(source)
        return published

    monkeypatch.setattr(
        module, "publish_offline_game_archive", replace_after_archive,
    )
    with pytest.raises(
        FirstPlayableDeliveryAcceptanceError, match="install blocked",
    ):
        publish_first_playable_delivery(
            source, archive, install, save, receipt,
            expected_manifest_sha256=original_source[1],
            moves=("up",), authorized=True,
        )
    assert archive.is_file()
    assert all(not item.exists() for item in (install, save, receipt))


def test_consumer_first_run_evidence_replays_real_installed_game(
    original_source, tmp_path, capsys,
):
    """Canonical CLI checks actual install/save twice, without release claims."""
    published, (archive, install, save, receipt), manifest_pin = _publish(
        original_source, tmp_path,
    )
    command = [
        "consumer-first-run-readiness",
        "--installed", str(install),
        "--archive", str(archive),
        "--save", str(save),
        "--receipt", str(receipt),
        "--expected-manifest-sha256", manifest_pin,
        "--expected-archive-sha256", published["archive_sha256"],
        "--expected-save-sha256", published["save_sha256"],
        "--expected-receipt-sha256", published["independent_receipt_sha256"],
        "--trusted-local-operator",
    ]
    before = {path: path.read_bytes() for path in (archive, save, receipt)}
    assert run_app_cli(command) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["source_level_replay_passes"] == 2
    assert result["installed_game_and_private_save_reexecuted"] is True
    assert result["all_input_inodes_stable_during_inspection"] is True
    assert result["files_published"] == 0
    assert result["read_only"] is True
    assert result["native_device_qualified"] is False
    assert result["windows_laptop_qualified"] is False
    assert result["installer_qualified"] is False
    assert result["guarded_local_ai_qualified"] is False
    assert result["package_signed"] is False
    assert result["rights_certified"] is False
    assert result["release_certified"] is False
    assert "NATIVE_DEVICE_QUALIFICATION_ABSENT" in result["release_holds"]
    assert all(path.read_bytes() == data for path, data in before.items())
    assert run_app_cli(command[:-1]) == 2
    assert json.loads(capsys.readouterr().err)["release_certified"] is False
    wrong_pin = list(command)
    wrong_pin[wrong_pin.index("--expected-save-sha256") + 1] = "0" * 64
    assert run_app_cli(wrong_pin) == 2
    assert json.loads(capsys.readouterr().err)["native_device_qualified"] is False


def test_consumer_first_run_rejects_forged_upstream_evidence(
    monkeypatch,
):
    from skeleton.app import consumer_first_run_readiness as module

    pinned = {
        "manifest": "a" * 64,
        "archive": "b" * 64,
        "save": "c" * 64,
        "receipt": "d" * 64,
    }
    observed = {
        "project_id": "original-game",
        "world_digest": "e" * 64,
        "replay_digest": "f" * 64,
        "manifest_sha256": pinned["manifest"],
        "archive_sha256": pinned["archive"],
        "save_sha256": pinned["save"],
        "independent_receipt_sha256": pinned["receipt"],
        "action_count": 2,
        "live_source_and_private_replay_reexecuted": True,
        "receipt_integrity_verified": True,
        "independent_pin_reverified": True,
        "offline_gameplay_reexecuted": True,
        "read_only": True,
        "release_certified": False,
        "native_device_qualified": False,
        "package_signed": False,
        "rights_certified": False,
        "persistent_rollback_protection": False,
    }
    monkeypatch.setattr(module, "_custody", lambda *args: ((1, 2),) * 4)
    # Claim-forgery tests do not access a real installed game. Supply the
    # canonical immutable inode inventory shape rather than a dict or path:
    # the digest function must still validate it and must not be disabled.
    fixed_inventory = (("", (1, 2, 3, 4, 1, 0, 0, 0)),)
    monkeypatch.setattr(module, "snapshot_installed_tree",
                        lambda *_args: fixed_inventory)
    def inspect(**overrides):
        monkeypatch.setattr(
            module, "inspect_first_playable_delivery",
            lambda *args, **kwargs: {**observed, **overrides},
        )
        return module.inspect_consumer_first_run(
            "/game", "/archive", "/save", "/receipt",
            expected_manifest_sha256=pinned["manifest"],
            expected_archive_sha256=pinned["archive"],
            expected_save_sha256=pinned["save"],
            expected_receipt_sha256=pinned["receipt"],
            authorized=True,
        )
    assert inspect()["release_certified"] is False
    for forged in (
        {"world_digest": "not-a-digest"},
        {"replay_digest": True},
        {"project_id": "../foreign"},
        {"action_count": True},
        {"save_sha256": "0" * 64},
        {"release_certified": True},
        {"package_signed": True},
    ):
        with pytest.raises(module.ConsumerFirstRunReadinessError):
            inspect(**forged)
