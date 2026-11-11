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



def test_hostile_directory_entry_flood_is_bounded(package):
    root, pin = package
    for index in range(180):
        (root / f"unlisted-{index:04d}").write_bytes(b"x")
    with pytest.raises(DualRuntimeVerificationError, match="entry budget"):
        verify_exported_package(root, expected_manifest_sha256=pin, authorized=True)


def test_scandir_enumeration_stops_at_budget_without_exhausting_iterator(monkeypatch):
    from skeleton.ai.game_builder import dual_runtime_verify as verifier

    class Entries:
        consumed = 0

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def __iter__(self):
            for index in range(10_000):
                self.consumed += 1
                yield type("Entry", (), {"name": f"entry-{index}"})()

    entries = Entries()
    monkeypatch.setattr(verifier.os, "scandir", lambda fd: entries)
    with pytest.raises(DualRuntimeVerificationError, match="entry budget"):
        verifier._bounded_names(9, 4)
    assert entries.consumed == 5



def test_malicious_world_dimensions_rejected_before_path_solver(monkeypatch):
    from skeleton.ai.game_builder import dual_runtime_verify as verifier

    intent = GameBuildIntent(
        project_id="bounded-world", title="Bounded World",
        subtitle="Adversarial source verification", seed=42,
        width=9, height=9, levels=1, collectibles_per_level=1,
        hazards_per_level=0, starting_health=3,
    )
    native = {
        "schema": "skeleton.game_builder.godot_world.v1",
        "intent": intent.to_payload(),
        "levels": [{
            "rows": ["#" * 100_000] * 9,
            "start": [1, 1],
            "collectibles": [[2, 2]],
        }],
    }
    manifest = {
        "world_algorithm": "skeleton.game_builder.maze-puzzle.v1",
        "world_digest": "0" * 64,
        "project_id": intent.project_id,
    }

    def solver_must_not_run(_):
        raise AssertionError("untrusted oversized grid reached path solver")

    monkeypatch.setattr(verifier, "solve_safe_path", solver_must_not_run)
    with pytest.raises(DualRuntimeVerificationError, match="geometry"):
        verifier._world(native, manifest)


def test_untrusted_world_level_count_rejected_before_path_solver(monkeypatch):
    from skeleton.ai.game_builder import dual_runtime_verify as verifier

    intent = GameBuildIntent(
        project_id="bounded-count", title="Bounded Count",
        subtitle="Adversarial source verification", seed=43,
        width=9, height=9, levels=1, collectibles_per_level=1,
        hazards_per_level=0, starting_health=3,
    )
    native = {
        "schema": "skeleton.game_builder.godot_world.v1",
        "intent": intent.to_payload(),
        "levels": [{"rows": ["#" * 9] * 9, "start": [1, 1],
                    "collectibles": [[2, 2]]}] * 200,
    }
    manifest = {
        "world_algorithm": "skeleton.game_builder.maze-puzzle.v1",
        "world_digest": "0" * 64,
        "project_id": intent.project_id,
    }
    monkeypatch.setattr(verifier, "solve_safe_path", lambda _: (
        pytest.fail("oversized level set reached path solver")
    ))
    with pytest.raises(DualRuntimeVerificationError, match="level count"):
        verifier._world(native, manifest)


def test_release_replacement_during_replay_is_rejected(package, monkeypatch):
    from skeleton.ai.game_builder import dual_runtime_verify as verifier

    root, pin = package
    original = verifier._read
    changed = False

    def mutate_after_source_read(fd, path, limit):
        nonlocal changed
        payload = original(fd, path, limit)
        if path == "index.html" and not changed:
            changed = True
            release = root / "release.json"
            release.write_bytes(b"x" * release.stat().st_size)
        return payload

    monkeypatch.setattr(verifier, "_read", mutate_after_source_read)
    with pytest.raises(DualRuntimeVerificationError, match="release changed"):
        verifier.verify_exported_package(
            root, expected_manifest_sha256=pin, authorized=True,
        )
    assert changed


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor identity")
def test_directory_swap_between_stat_and_open_is_rejected(package, monkeypatch):
    from skeleton.ai.game_builder import dual_runtime_verify as verifier

    root, pin = package
    real_open = verifier.os.open
    swapped = False

    def swap_before_open(path, flags, *args, **kwargs):
        nonlocal swapped
        if path == "godot" and kwargs.get("dir_fd") is not None and not swapped:
            swapped = True
            (root / "godot").rename(root / "godot-old")
            (root / "godot").mkdir()
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(verifier.os, "open", swap_before_open)
    with pytest.raises(DualRuntimeVerificationError, match="directory changed"):
        verifier.verify_exported_package(
            root, expected_manifest_sha256=pin, authorized=True,
        )
    assert swapped


def test_source_replaced_during_replay_fails_final_integrity_pass(package, monkeypatch):
    from skeleton.ai.game_builder import dual_runtime_verify as verifier

    root, pin = package
    real_play = verifier.play_actions

    def swap_after_replay(*args, **kwargs):
        result = real_play(*args, **kwargs)
        (root / "index.html").write_bytes(b"forged browser source")
        return result

    monkeypatch.setattr(verifier, "play_actions", swap_after_replay)
    with pytest.raises(DualRuntimeVerificationError, match="source changed"):
        verifier.verify_exported_package(
            root, expected_manifest_sha256=pin, authorized=True,
        )


@pytest.mark.skipif(os.name != "posix", reason="POSIX pinned directory root")
def test_replaced_package_root_during_replay_cannot_receive_receipt(package, monkeypatch):
    from skeleton.ai.game_builder import dual_runtime_verify as verifier

    root, pin = package
    original = root.parent / "original-export"
    real_play = verifier.play_actions

    def move_root_after_replay(*args, **kwargs):
        result = real_play(*args, **kwargs)
        root.rename(original)
        root.mkdir()
        return result

    monkeypatch.setattr(verifier, "play_actions", move_root_after_replay)
    with pytest.raises(DualRuntimeVerificationError, match="root changed"):
        verifier.verify_exported_package(
            root, expected_manifest_sha256=pin, authorized=True,
        )
    assert original.is_dir()


@pytest.mark.skipif(os.name != "posix", reason="POSIX atomic receipt custody")
def test_verify_export_cli_publishes_no_clobber_receipt(package, tmp_path, capsys):
    root, pin = package
    receipt_file = tmp_path / "verification.json"
    command = ["--package", str(root), "--expected-manifest-sha256", pin,
               "--trusted-local-operator", "--receipt-output", str(receipt_file)]
    assert main(command) == 0
    payload = json.loads(capsys.readouterr().out)
    assert json.loads(receipt_file.read_text()) == payload
    from skeleton.ai.game_builder.dual_runtime_verify import _canonical_bytes
    assert receipt_file.read_bytes() == _canonical_bytes(payload)
    assert receipt_file.stat().st_mode & 0o077 == 0
    assert main(command) == 2
    assert json.loads(receipt_file.read_text()) == payload


@pytest.mark.skipif(os.name != "posix", reason="POSIX atomic receipt custody")
def test_verify_export_receipt_rejects_source_write_and_symlink_parent(package, tmp_path):
    root, pin = package
    base = ["--package", str(root), "--expected-manifest-sha256", pin,
            "--trusted-local-operator", "--receipt-output"]
    assert main([*base, str(root / "receipt.json")]) == 2
    assert not (root / "receipt.json").exists()
    outside = tmp_path / "outside"
    outside.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(outside, target_is_directory=True)
    assert main([*base, str(alias / "receipt.json")]) == 2
    assert not (outside / "receipt.json").exists()


@pytest.mark.skipif(os.name != "posix", reason="POSIX pinned receipt inspection")
def test_inspect_receipt_roundtrip_and_tamper_rejection(package, tmp_path, capsys):
    from skeleton.ai.game_builder.original_game_studio_cli import main as studio
    root, pin = package
    output = tmp_path / "verification.json"
    assert studio([
        "verify-export", "--package", str(root),
        "--expected-manifest-sha256", pin, "--trusted-local-operator",
        "--receipt-output", str(output),
    ]) == 0
    capsys.readouterr()
    trusted = sha256(output.read_bytes()).hexdigest()
    inspect = ["inspect-receipt", "--receipt", str(output),
               "--expected-sha256", trusted, "--trusted-local-operator"]
    assert studio(inspect) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["receipt_integrity_verified"] is True
    assert result["gameplay_reexecuted_now"] is False
    assert result["release_certified"] is False
    assert studio(inspect[:-1]) == 2
    capsys.readouterr()
    output.write_bytes(output.read_bytes() + b" ")
    assert studio(inspect) == 2


@pytest.mark.skipif(os.name != "posix", reason="POSIX pinned receipt inspection")
def test_inspect_receipt_rejects_hardlink_and_noncanonical_json(tmp_path):
    from skeleton.ai.game_builder.offline_receipt_inspection import (
        ReceiptInspectionError, inspect_verified_receipt,
    )
    source = tmp_path / "receipt.json"
    source.write_bytes(b'{"schema":"untrusted"}\\n')
    alias = tmp_path / "alias.json"
    os.link(source, alias)
    with pytest.raises(ReceiptInspectionError):
        inspect_verified_receipt(
            alias, expected_sha256=sha256(source.read_bytes()).hexdigest(),
            authorized=True,
        )
    source.unlink()
    with pytest.raises(ReceiptInspectionError):
        inspect_verified_receipt(
            alias, expected_sha256=sha256(alias.read_bytes()).hexdigest(),
            authorized=True,
        )


def _studio_verification_fixture(tmp_path):
    """Create correctly pinned studio-source metadata over a real playable."""
    from skeleton.ai.game_builder.contracts import canonical_digest
    from skeleton.ai.game_builder.dual_runtime_export import (
        DualRuntimePackage, render_dual_runtime_package, export_dual_runtime_package,
    )
    from skeleton.ai.game_builder.playable_compiler import compile_original_game
    from skeleton.ai.game_builder.playable_world import GameBuildIntent

    intent = GameBuildIntent(
        project_id="studio-verified-001", title="Studio Lantern",
        subtitle="Source-bound first playable", seed=1735,
        levels=1, width=9, height=9, collectibles_per_level=1,
        hazards_per_level=0, starting_health=3,
    )
    project = compile_original_game(intent, authorized=True)
    original = render_dual_runtime_package(project, authorized=True)
    file_data = {path: payload for path, payload in original.files.items()
                 if path != "release.json"}
    studio_paths = (
        "studio/pipeline.json",
        "studio/jeeves_dragon_tools.json",
        "studio/executed_tool_receipts.json",
        "studio/mirror_room.json",
        "studio/consumer_gate.json",
        "studio/companion_mirror_room.json",
        "studio/companion_almanac.json",
        "studio/companion_practice.json",
    )
    consumer = {
        "schema": "skeleton.game_builder.consumer_review.v1",
        "status": "release-blocked",
        "evidence": {
            "approved_for_publication": False,
            "rights_reviewed": False,
            "human_playtested": False,
            "platform_hardware_tested": False,
        },
        "not_a_legal_opinion": True,
    }
    for path in studio_paths:
        if path == "studio/consumer_gate.json":
            obj = consumer
        elif path == "studio/pipeline.json":
            obj = {
                "schema": "skeleton.game_builder.studio_pipeline.v1",
                "project_id": original.manifest["project_id"],
                "not_automatically_published": True,
                "original_game_claim": "generated-or-user-authored-geometry",
            }
        else:
            obj = {
                "schema": "skeleton.game_builder.original_studio_test_metadata.v1",
            }
        file_data[path] = (
            json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False)
            + "\n"
        ).encode("utf-8")
    manifest_body = {
        key: value for key, value in original.manifest.items()
        if key not in {"files", "manifest_digest"}
    }
    manifest_body["schema"] = "skeleton.game_builder.studio_package.v1"
    manifest_body["files"] = {
        path: sha256(data).hexdigest() for path, data in sorted(file_data.items())
    }
    manifest = {
        **manifest_body, "manifest_digest": canonical_digest(manifest_body),
    }
    file_data["release.json"] = (
        json.dumps(manifest, sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n"
    ).encode("utf-8")
    root = export_dual_runtime_package(
        DualRuntimePackage(file_data, manifest),
        tmp_path / "studio-export",
        authorized=True,
    )
    return root, sha256((root / "release.json").read_bytes()).hexdigest()


def test_verified_studio_package_preserves_original_playable_and_release_holds(tmp_path):
    root, pin = _studio_verification_fixture(tmp_path)
    verified = verify_exported_package(
        root, expected_manifest_sha256=pin, authorized=True,
    )
    assert verified["offline_gameplay_reexecuted"] is True
    assert verified["godot_executed"] is False
    assert verified["rights_certified"] is False
    assert verified["release_certified"] is False


@pytest.mark.parametrize("change", ["missing-mirror", "missing-consumer", "claim-published"])
def test_studio_schema_rejects_missing_or_false_release_evidence(tmp_path, change):
    from skeleton.ai.game_builder.contracts import canonical_digest

    root, _pin = _studio_verification_fixture(tmp_path)
    release = json.loads((root / "release.json").read_bytes())
    if change == "missing-mirror":
        release["files"].pop("studio/mirror_room.json")
        (root / "studio/mirror_room.json").unlink()
    elif change == "missing-consumer":
        release["files"].pop("studio/consumer_gate.json")
        (root / "studio/consumer_gate.json").unlink()
    else:
        consumer_path = root / "studio/consumer_gate.json"
        consumer = json.loads(consumer_path.read_bytes())
        consumer["status"] = "ready-for-authorized-publication"
        consumer["evidence"]["approved_for_publication"] = True
        bytes_ = (
            json.dumps(consumer, sort_keys=True, separators=(",", ":"), allow_nan=False)
            + "\n"
        ).encode("utf-8")
        consumer_path.write_bytes(bytes_)
        release["files"]["studio/consumer_gate.json"] = sha256(bytes_).hexdigest()
    release["manifest_digest"] = canonical_digest({
        key: value for key, value in release.items() if key != "manifest_digest"
    })
    (root / "release.json").write_bytes((
        json.dumps(release, sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n"
    ).encode("utf-8"))
    pin = sha256((root / "release.json").read_bytes()).hexdigest()
    with pytest.raises(DualRuntimeVerificationError):
        verify_exported_package(root, expected_manifest_sha256=pin, authorized=True)
