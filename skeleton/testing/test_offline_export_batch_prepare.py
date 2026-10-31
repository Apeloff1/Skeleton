"""Canonical verified batch preparation and atomic no-clobber regressions."""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path

import pytest

from skeleton.ai.game_builder.dual_runtime_export import (
    export_dual_runtime_package, render_dual_runtime_package,
)
from skeleton.ai.game_builder.offline_export_batch import (
    OfflineBatchVerificationError, verify_export_batch,
)
from skeleton.ai.game_builder.offline_export_batch_prepare import prepare_export_batch
from skeleton.ai.game_builder.offline_export_batch_prepare_cli import main
from skeleton.ai.game_builder.original_game_studio_cli import main as studio_cli
from skeleton.ai.game_builder.playable_compiler import compile_original_game
from skeleton.ai.game_builder.playable_world import GameBuildIntent


@pytest.fixture
def unpublished(tmp_path: Path):
    root = tmp_path / "cohort"
    root.mkdir(mode=0o700)
    entries = []
    for i in range(2):
        intent = GameBuildIntent(
            project_id=f"prepare-original-{i + 1:03d}",
            title=f"New Original Harbor {i + 1}",
            subtitle="Original operator-pinned safe-route expedition",
            seed=2048 + i, levels=1, width=9, height=9,
            collectibles_per_level=1, hazards_per_level=0,
            starting_health=3,
        )
        game = compile_original_game(intent, authorized=True)
        source = render_dual_runtime_package(game, authorized=True)
        directory = f"package-{i + 1:03d}"
        exported = export_dual_runtime_package(
            source, root / directory, authorized=True,
        )
        entries.append({
            "project_id": intent.project_id,
            "package_dir": directory,
            "release_sha256": sha256((exported / "release.json").read_bytes()).hexdigest(),
        })
    return root, entries


def test_prepare_then_verify_real_games(unpublished):
    root, entries = unpublished
    receipt = prepare_export_batch(root, entries=list(reversed(entries)), authorized=True)
    pin = receipt["index_sha256"]
    assert sha256((root / "batch.json").read_bytes()).hexdigest() == pin
    index = json.loads((root / "batch.json").read_bytes())
    assert [x["package_dir"] for x in index["packages"]] == [
        "package-001", "package-002",
    ]
    verified = verify_export_batch(root, expected_index_sha256=pin, authorized=True)
    assert verified["verified_packages"] == 2
    assert verified["offline_gameplay_reexecuted"] is True
    assert receipt["release_certified"] is False


def test_preparation_is_never_an_overwrite(unpublished):
    root, entries = unpublished
    prepare_export_batch(root, entries=entries, authorized=True)
    before = (root / "batch.json").read_bytes()
    with pytest.raises(OfflineBatchVerificationError):
        prepare_export_batch(root, entries=entries, authorized=True)
    assert (root / "batch.json").read_bytes() == before


@pytest.mark.parametrize("attack", [
    "wrong-pin", "wrong-project", "extra", "symlink", "duplicate",
    "invalid-dir", "untrusted",
])
def test_invalid_preparation_leaves_no_index(unpublished, attack):
    root, entries = unpublished
    if attack == "wrong-pin":
        entries[0]["release_sha256"] = "0" * 64
    elif attack == "wrong-project":
        entries[0]["project_id"] = "wrong-project"
    elif attack == "extra":
        (root / "unlisted").write_text("not a package")
    elif attack == "symlink":
        import shutil
        shutil.rmtree(root / "package-002")
        (root / "package-002").symlink_to(
            root / "package-001", target_is_directory=True,
        )
    elif attack == "duplicate":
        entries[1]["project_id"] = entries[0]["project_id"]
    elif attack == "invalid-dir":
        entries[0]["package_dir"] = "../package-001"
    elif attack == "untrusted":
        with pytest.raises(PermissionError):
            prepare_export_batch(root, entries=entries, authorized=False)
        assert not (root / "batch.json").exists()
        return
    with pytest.raises(OfflineBatchVerificationError):
        prepare_export_batch(root, entries=entries, authorized=True)
    assert not (root / "batch.json").exists()


def test_failed_atomic_publication_removes_temporary_file(unpublished, monkeypatch):
    root, entries = unpublished
    def fail_link(*args, **kwargs):
        raise OSError("simulated publication failure")
    monkeypatch.setattr(os, "link", fail_link)
    with pytest.raises(OfflineBatchVerificationError):
        prepare_export_batch(root, entries=entries, authorized=True)
    assert sorted(p.name for p in root.iterdir()) == [
        "package-001", "package-002",
    ]


def test_cli_prepares_source_and_can_be_verified(unpublished, capsys):
    root, entries = unpublished
    args = ["--root", str(root), "--trusted-local-operator"]
    for entry in entries:
        args.extend(["--package", ":".join((
            entry["project_id"], entry["package_dir"], entry["release_sha256"],
        ))])
    assert studio_cli(["prepare-batch", *args]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["prepared_packages"] == 2
    assert verify_export_batch(
        root, expected_index_sha256=receipt["index_sha256"], authorized=True,
    )["verified_packages"] == 2


def test_cli_rejects_missing_authorization(unpublished, capsys):
    root, entries = unpublished
    entry = entries[0]
    assert main(["--root", str(root), "--package", ":".join((
        entry["project_id"], entry["package_dir"], entry["release_sha256"],
    ))]) == 2
    assert json.loads(capsys.readouterr().err)["prepared"] is False



def test_preparation_root_entry_flood_never_publishes_index(unpublished):
    root, entries = unpublished
    for index in range(64):
        (root / f"unlisted-{index:04d}").write_bytes(b"x")
    with pytest.raises(OfflineBatchVerificationError, match="batch preparation rejected"):
        prepare_export_batch(root, entries=entries, authorized=True)
    assert not (root / "batch.json").exists()


def test_concurrent_sibling_after_replay_rejects_preparation_without_index(unpublished, monkeypatch):
    import skeleton.ai.game_builder.offline_export_batch_prepare as module

    root, entries = unpublished
    original = module.verify_exported_package
    calls = 0

    def inject_after_replay(*args, **kwargs):
        nonlocal calls
        receipt = original(*args, **kwargs)
        calls += 1
        if calls == 1:
            (root / "unlisted-during-replay.txt").write_bytes(b"untrusted")
        return receipt

    monkeypatch.setattr(module, "verify_exported_package", inject_after_replay)
    with pytest.raises(OfflineBatchVerificationError, match="changed during replay"):
        prepare_export_batch(root, entries=entries, authorized=True)
    assert not (root / "batch.json").exists()


def test_concurrent_sibling_during_atomic_link_rolls_back_own_index(unpublished, monkeypatch):
    root, entries = unpublished
    original_link = os.link

    def insert_during_link(*args, **kwargs):
        (root / "unlisted-at-link.txt").write_bytes(b"untrusted")
        return original_link(*args, **kwargs)

    monkeypatch.setattr(os, "link", insert_during_link)
    with pytest.raises(OfflineBatchVerificationError, match="atomic publication"):
        prepare_export_batch(root, entries=entries, authorized=True)
    assert not (root / "batch.json").exists()
    assert not any(path.name.startswith(".batch-") for path in root.iterdir())
