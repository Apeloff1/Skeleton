"""Actual exported browser/Godot package verification and hostile filesystem paths."""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path

import pytest

from skeleton.ai.game_builder.dual_runtime_export import (
    export_dual_runtime_package, render_dual_runtime_package,
)
from skeleton.ai.game_builder.dual_runtime_verify import (
    DualRuntimeVerificationError, verify_exported_package,
)
from skeleton.ai.game_builder.dual_runtime_verify_cli import main
from skeleton.ai.game_builder.playable_compiler import compile_original_game
from skeleton.ai.game_builder.playable_world import GameBuildIntent


@pytest.fixture
def package(tmp_path: Path) -> tuple[Path, str]:
    intent = GameBuildIntent(
        project_id="offline-verified-001", title="Lantern Trail",
        subtitle="Original safe-route expedition", seed=1729,
        levels=1, width=9, height=9, collectibles_per_level=1,
        hazards_per_level=0, starting_health=3,
    )
    project = compile_original_game(intent, authorized=True)
    source = render_dual_runtime_package(project, authorized=True)
    root = export_dual_runtime_package(source, tmp_path / "export", authorized=True)
    return root, sha256((root / "release.json").read_bytes()).hexdigest()


def test_offline_export_replays_canonical_winning_game(package):
    root, pin = package
    receipt = verify_exported_package(root, expected_manifest_sha256=pin, authorized=True)
    assert receipt["offline_gameplay_reexecuted"] is True
    assert receipt["replayed_actions"] > 0
    assert receipt["verified_files"] >= 10
    assert receipt["godot_executed"] is False
    assert receipt["release_certified"] is False


def test_existing_studio_cli_routes_to_readonly_verifier(package, capsys):
    from skeleton.ai.game_builder.original_game_studio_cli import main as studio
    root, pin = package
    assert studio(["verify-export", "--package", str(root),
                   "--expected-manifest-sha256", pin,
                   "--trusted-local-operator"]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["manifest_sha256"] == pin
    assert receipt["offline_gameplay_reexecuted"] is True


@pytest.mark.parametrize("mutate", ["html", "proof", "extra", "symlink"])
def test_mutated_or_injected_package_is_rejected(package, tmp_path, mutate):
    root, pin = package
    if mutate == "html":
        (root / "index.html").write_bytes(b"<html>tampered</html>")
    elif mutate == "proof":
        (root / "godot" / "proof.json").write_text("{}", encoding="utf-8")
    elif mutate == "extra":
        (root / "untracked.txt").write_text("extra", encoding="utf-8")
    else:
        (root / "foreign").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(DualRuntimeVerificationError):
        verify_exported_package(root, expected_manifest_sha256=pin, authorized=True)


def test_root_symlink_is_never_followed(package, tmp_path):
    root, pin = package
    alias = tmp_path / "alias"
    alias.symlink_to(root, target_is_directory=True)
    with pytest.raises(DualRuntimeVerificationError):
        verify_exported_package(alias, expected_manifest_sha256=pin, authorized=True)


def test_manifest_pin_is_independent_and_mandatory(package):
    root, pin = package
    for wrong in ("", "f" * 64, "A" * 64, "0" * 65):
        with pytest.raises(DualRuntimeVerificationError):
            verify_exported_package(root, expected_manifest_sha256=wrong, authorized=True)
    with pytest.raises(PermissionError):
        verify_exported_package(root, expected_manifest_sha256=pin, authorized=False)


def test_readonly_cli_fails_closed_without_operator_ack(package, capsys):
    root, pin = package
    assert main(["--package", str(root), "--expected-manifest-sha256", pin]) == 2
    assert json.loads(capsys.readouterr().err)["verified"] is False


def test_duplicate_manifest_key_rejected_even_with_recomputed_pin(package):
    root, _ = package
    release = root / "release.json"
    raw = release.read_bytes()
    release.write_bytes(raw.replace(b'"schema":', b'"schema":"duplicate","schema":', 1))
    pin = sha256(release.read_bytes()).hexdigest()
    with pytest.raises(DualRuntimeVerificationError, match="duplicate"):
        verify_exported_package(root, expected_manifest_sha256=pin, authorized=True)


def test_untrusted_hardlink_is_rejected(package, tmp_path):
    root, pin = package
    original = root / "index.html"
    os.link(original, tmp_path / "alias.html")
    with pytest.raises(DualRuntimeVerificationError):
        verify_exported_package(root, expected_manifest_sha256=pin, authorized=True)
