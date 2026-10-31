"""Real offline game export cohort verification and hostile index regression."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import shutil

import pytest

from skeleton.ai.game_builder.dual_runtime_export import (
    export_dual_runtime_package, render_dual_runtime_package,
)
from skeleton.ai.game_builder.offline_export_batch import (
    OfflineBatchVerificationError, SCHEMA, verify_export_batch,
)
from skeleton.ai.game_builder.offline_export_batch_cli import main as batch_cli
from skeleton.ai.game_builder.original_game_studio_cli import main as studio_cli
from skeleton.ai.game_builder.playable_compiler import compile_original_game
from skeleton.ai.game_builder.playable_world import GameBuildIntent


def _write_index(root: Path, entries: list[dict[str, str]]) -> str:
    index = {"schema": SCHEMA, "packages": entries}
    data = (json.dumps(index, sort_keys=True, ensure_ascii=True,
                       separators=(",", ":")) + "\n").encode()
    (root / "batch.json").write_bytes(data)
    return sha256(data).hexdigest()


@pytest.fixture
def batch(tmp_path: Path) -> tuple[Path, str, list[dict[str, str]]]:
    root = tmp_path / "batch"
    root.mkdir()
    entries = []
    for i in range(2):
        intent = GameBuildIntent(
            project_id=f"original-batch-{i + 1:03d}",
            title=f"Original Lantern Route {i + 1}",
            subtitle="Independent source-bound safe-route expedition",
            seed=1729 + i, levels=1, width=9, height=9,
            collectibles_per_level=1, hazards_per_level=0,
            starting_health=3,
        )
        project = compile_original_game(intent, authorized=True)
        package = render_dual_runtime_package(project, authorized=True)
        directory = f"game-{i + 1:03d}"
        exported = export_dual_runtime_package(
            package, root / directory, authorized=True,
        )
        entries.append({
            "project_id": intent.project_id,
            "package_dir": directory,
            "release_sha256": sha256((exported / "release.json").read_bytes()).hexdigest(),
        })
    return root, _write_index(root, entries), entries


def test_two_real_playable_exports_verified_with_canonical_replay(batch):
    root, pin, _ = batch
    result = verify_export_batch(root, expected_index_sha256=pin, authorized=True)
    assert result["verified_packages"] == 2
    assert result["replayed_actions"] > 0
    assert result["offline_gameplay_reexecuted"] is True
    assert result["godot_executed"] is False
    assert result["release_certified"] is False
    assert len(result["receipt_digest"]) == 64
    assert verify_export_batch(root, expected_index_sha256=pin, authorized=True) == result


def test_studio_cli_routes_to_canonical_batch_verifier(batch, capsys):
    root, pin, _ = batch
    assert studio_cli(["verify-batch", "--root", str(root),
                       "--expected-index-sha256", pin,
                       "--trusted-local-operator"]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["verified_packages"] == 2


def test_batch_cli_requires_operator_acknowledgement(batch, capsys):
    root, pin, _ = batch
    assert batch_cli(["--root", str(root), "--expected-index-sha256", pin]) == 2
    assert json.loads(capsys.readouterr().err)["verified"] is False


@pytest.mark.parametrize("attack", [
    "wrong-pin", "tamper-html", "unlisted-file", "missing-package",
    "symlink-package", "duplicate-id", "duplicate-dir", "reversed",
    "wrong-project", "traversal", "duplicate-json-key", "noncanonical",
])
def test_hostile_batch_rejected(batch, attack):
    root, pin, entries = batch
    if attack == "wrong-pin":
        pin = "0" * 64
    elif attack == "tamper-html":
        (root / "game-001" / "index.html").write_text("changed")
    elif attack == "unlisted-file":
        (root / "rogue.txt").write_text("rogue")
    elif attack == "missing-package":
        shutil.rmtree(root / "game-002")
    elif attack == "symlink-package":
        shutil.rmtree(root / "game-002")
        (root / "game-002").symlink_to(root / "game-001", target_is_directory=True)
    elif attack == "duplicate-id":
        entries[1]["project_id"] = entries[0]["project_id"]
        pin = _write_index(root, entries)
    elif attack == "duplicate-dir":
        entries[1]["package_dir"] = entries[0]["package_dir"]
        pin = _write_index(root, entries)
    elif attack == "reversed":
        pin = _write_index(root, list(reversed(entries)))
    elif attack == "wrong-project":
        entries[0]["project_id"] = "other-project"
        pin = _write_index(root, entries)
    elif attack == "traversal":
        entries[0]["package_dir"] = "../game-001"
        pin = _write_index(root, entries)
    elif attack == "duplicate-json-key":
        raw = (root / "batch.json").read_bytes()
        (root / "batch.json").write_bytes(
            raw.replace(b'"schema":', b'"schema":"other","schema":', 1)
        )
        pin = sha256((root / "batch.json").read_bytes()).hexdigest()
    elif attack == "noncanonical":
        raw = json.loads((root / "batch.json").read_bytes())
        (root / "batch.json").write_text(json.dumps(raw, indent=2))
        pin = sha256((root / "batch.json").read_bytes()).hexdigest()
    with pytest.raises(OfflineBatchVerificationError):
        verify_export_batch(root, expected_index_sha256=pin, authorized=True)


def test_concurrent_unlisted_sibling_rejected_after_replay(batch, monkeypatch):
    import skeleton.ai.game_builder.offline_export_batch as batch_module

    root, pin, _ = batch
    original = batch_module._child_fd
    inserted = False

    def insert_sibling_after_initial_inventory(root_fd, parts, *, directory):
        nonlocal inserted
        if not inserted:
            (root / "unlisted-during-replay.txt").write_text("untrusted")
            inserted = True
        return original(root_fd, parts, directory=directory)

    monkeypatch.setattr(batch_module, "_child_fd", insert_sibling_after_initial_inventory)
    with pytest.raises(OfflineBatchVerificationError, match="changed during verification"):
        verify_export_batch(root, expected_index_sha256=pin, authorized=True)


def test_root_symlink_rejected(batch, tmp_path):
    root, pin, _ = batch
    alias = tmp_path / "alias"
    alias.symlink_to(root, target_is_directory=True)
    with pytest.raises(OfflineBatchVerificationError):
        verify_export_batch(alias, expected_index_sha256=pin, authorized=True)


def test_invalid_pin_and_authorization_rejected_before_filesystem(batch):
    root, pin, _ = batch
    with pytest.raises(PermissionError):
        verify_export_batch(root, expected_index_sha256=pin, authorized=False)
    for invalid in ("", "A" * 64, "a" * 65, "z" * 64):
        with pytest.raises(OfflineBatchVerificationError):
            verify_export_batch(root, expected_index_sha256=invalid, authorized=True)


def test_index_package_count_bounded(batch):
    root, _, entries = batch
    pin = _write_index(root, entries * 17)
    with pytest.raises(OfflineBatchVerificationError, match="count"):
        verify_export_batch(root, expected_index_sha256=pin, authorized=True)



def test_batch_root_entry_flood_rejected_before_replay(batch):
    root, pin, _ = batch
    for index in range(64):
        (root / f"unlisted-{index:04d}").write_bytes(b"x")
    with pytest.raises(OfflineBatchVerificationError, match="batch verification rejected"):
        verify_export_batch(root, expected_index_sha256=pin, authorized=True)
