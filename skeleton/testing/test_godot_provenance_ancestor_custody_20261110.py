"""Godot provenance regression: current paths, not orphaned file descriptors.

These are offline adversarial source tests. They do not certify actual Godot,
export templates, Windows/WSL2, native devices or release provenance.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from skeleton.godot_export import provenance


pytestmark = pytest.mark.skipif(
    os.name != "posix" or not hasattr(os, "O_NOFOLLOW"),
    reason="requires descriptor-anchored POSIX artifact custody",
)


def test_digest_refuses_symlinked_parent_swapped_during_hash(tmp_path):
    root = tmp_path / "source"
    parent = root / "build"
    parent.mkdir(parents=True)
    current = parent / "game.pck"
    content = b"a" * 8192
    current.write_bytes(content)
    other = tmp_path / "outside"
    other.mkdir()
    (other / "game.pck").write_bytes(content)
    orphan = root / "orphaned"
    actual_read = os.read
    swapped = False

    def replace_ancestor_after_read(fd, count):
        nonlocal swapped
        result = actual_read(fd, count)
        if result and not swapped:
            swapped = True
            parent.rename(orphan)
            parent.symlink_to(other, target_is_directory=True)
        return result

    with patch.object(provenance.os, "read", side_effect=replace_ancestor_after_read):
        with pytest.raises(ValueError, match="ancestor path"):
            provenance._digest_beneath(root, "build/game.pck")
    assert swapped
    assert (orphan / "game.pck").read_bytes() == content
    assert (other / "game.pck").read_bytes() == content


def test_digest_refuses_real_directory_replaced_with_identical_contents(tmp_path):
    root = tmp_path / "source"
    parent = root / "build"
    parent.mkdir(parents=True)
    current = parent / "game.bin"
    payload = b"byte-identical-content" * 600
    current.write_bytes(payload)
    other = root / "waiting"
    other.mkdir()
    (other / "game.bin").write_bytes(payload)
    orphan = root / "orphaned"
    actual_read = os.read
    swapped = False

    def replace_parent_after_read(fd, count):
        nonlocal swapped
        result = actual_read(fd, count)
        if result and not swapped:
            swapped = True
            parent.rename(orphan)
            other.rename(parent)
        return result

    with patch.object(provenance.os, "read", side_effect=replace_parent_after_read):
        with pytest.raises(ValueError, match="ancestor path replaced"):
            provenance._digest_beneath(root, "build/game.bin")
    assert swapped
    assert (parent / "game.bin").read_bytes() == payload


def test_digest_refuses_whole_source_root_replaced_during_read(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    payload = b"identical" * 1024
    (root / "game.pck").write_bytes(payload)
    replacement = tmp_path / "replacement"
    replacement.mkdir()
    (replacement / "game.pck").write_bytes(payload)
    detached = tmp_path / "old-source"
    actual_read = os.read
    swapped = False

    def replace_root_after_read(fd, count):
        nonlocal swapped
        result = actual_read(fd, count)
        if result and not swapped:
            swapped = True
            root.rename(detached)
            replacement.rename(root)
        return result

    with patch.object(provenance.os, "read", side_effect=replace_root_after_read):
        with pytest.raises(ValueError, match="ancestor path replaced"):
            provenance._digest_beneath(root, "game.pck")
    assert swapped
    assert (detached / "game.pck").read_bytes() == payload


def test_stable_parent_and_leaf_remain_identically_hashable(tmp_path):
    root = tmp_path / "source"
    output = root / "artifacts" / "linux"
    output.mkdir(parents=True)
    payload = b"real-godot-binary" * 256
    (output / "game.pck").write_bytes(payload)
    observed = provenance._digest_beneath(root, "artifacts/linux/game.pck")
    assert observed == (hashlib.sha256(payload).hexdigest(), len(payload))


def test_source_tree_avoids_full_materialized_rglob_sort(tmp_path):
    root = tmp_path / "project"
    source = root / "scripts"
    source.mkdir(parents=True)
    (source / "c.gd").write_text("extends Node\n", encoding="utf-8")
    (source / "a.gd").write_text("extends Node2D\n", encoding="utf-8")
    (root / "project.godot").write_text("[application]\n", encoding="utf-8")
    expected = provenance.tree_digest(root)
    with patch.object(
        Path, "rglob",
        side_effect=AssertionError("unbounded rglob cannot be used"),
    ):
        assert provenance.tree_digest(root) == expected


def test_source_file_cap_fails_closed_before_large_materialization(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    for index in range(4):
        (root / f"file_{index}.gd").write_text("extends Node\n")
    with patch.object(provenance, "MAX_SOURCE_FILES", 2):
        with pytest.raises(ValueError, match="source file budget"):
            provenance.tree_digest(root)


def test_source_directory_count_has_independent_budget(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    for index in range(6):
        (root / f"dir_{index}").mkdir()
    with patch.object(provenance, "MAX_SOURCE_ENTRIES", 3):
        with pytest.raises(ValueError, match="entry budget"):
            provenance.tree_digest(root)


def test_ignored_build_tree_is_pruned_before_security_scan(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    (root / "project.godot").write_text("[application]\n", encoding="utf-8")
    baseline = provenance.tree_digest(root)
    # The build folder is an ignored generated artifact subtree. Neither
    # its size nor its internal links should enter the source tree digest.
    ignored = root / "build"
    ignored.mkdir()
    for index in range(20):
        (ignored / f"generated_{index}.bin").write_bytes(b"x")
    (ignored / "linked.bin").symlink_to(root / "project.godot")
    with patch.object(provenance, "MAX_SOURCE_ENTRIES", 3):
        assert provenance.tree_digest(root) == baseline


def test_special_fifo_is_not_accepted_as_source_file(tmp_path):
    if not hasattr(os, "mkfifo"):
        pytest.skip("FIFO unavailable")
    root = tmp_path / "project"
    root.mkdir()
    os.mkfifo(root / "surprise.pipe")
    with pytest.raises(ValueError, match="special"):
        provenance.tree_digest(root)


def test_source_root_changed_after_scan_cannot_qualify(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    (root / "main.gd").write_bytes(b"extends Node\n")
    waiting = tmp_path / "replacement"
    waiting.mkdir()
    (waiting / "main.gd").write_bytes(b"extends Node\n")
    previous = tmp_path / "old-project"
    original = provenance._digest_beneath
    switched = False

    def digest_then_swap(dir_root, relative):
        nonlocal switched
        result = original(dir_root, relative)
        if not switched:
            root.rename(previous)
            waiting.rename(root)
            switched = True
        return result

    with patch.object(provenance, "_digest_beneath", side_effect=digest_then_swap):
        with pytest.raises(ValueError, match="source root changed"):
            provenance.tree_digest(root)
    assert switched



def test_directory_replaced_by_symlink_between_listing_and_open(tmp_path):
    root = tmp_path / "project"
    original = root / "nested"
    original.mkdir(parents=True)
    (original / "game.gd").write_text("extends Node\n")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "game.gd").write_text("extends Node\n")
    moved = root / "detached"
    actual_open = provenance._open_tree_directory
    swapped = False

    def swap_before_reopen(root_fd, parts):
        nonlocal swapped
        if parts == ("nested",) and not swapped:
            original.rename(moved)
            original.symlink_to(outside, target_is_directory=True)
            swapped = True
        return actual_open(root_fd, parts)

    with patch.object(
        provenance, "_open_tree_directory", side_effect=swap_before_reopen,
    ):
        with pytest.raises(ValueError, match="source directory changed"):
            provenance.tree_digest(root)
    assert swapped


def test_empty_directory_identity_rechecked_before_certification(tmp_path):
    root = tmp_path / "project"
    original = root / "empty"
    original.mkdir(parents=True)
    replacement = root / "replacement"
    replacement.mkdir()
    detached = root / "detached"
    original_open = provenance._open_tree_directory
    opens = 0

    def replace_after_listing(root_fd, parts):
        nonlocal opens
        if parts == ("empty",):
            opens += 1
            if opens == 2:
                original.rename(detached)
                replacement.rename(original)
        return original_open(root_fd, parts)

    with patch.object(
        provenance, "_open_tree_directory", side_effect=replace_after_listing,
    ):
        with pytest.raises(ValueError, match="source directory changed"):
            provenance.tree_digest(root)
    assert opens == 2
    assert detached.is_dir()


def test_rejects_directory_mutation_after_it_was_enumerated(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    nested = root / "nested"
    nested.mkdir()
    original_open = provenance._open_tree_directory
    visits = 0

    def mutate_at_final_check(root_fd, parts):
        nonlocal visits
        if parts == ("nested",):
            visits += 1
            if visits == 2:
                (nested / "late.gd").write_text("extends Node\n")
        return original_open(root_fd, parts)

    with patch.object(
        provenance, "_open_tree_directory", side_effect=mutate_at_final_check,
    ):
        with pytest.raises(ValueError, match="source directory changed"):
            provenance.tree_digest(root)
    assert visits == 2



def test_symlink_manifest_result_preserves_unsafe_and_symlink_contract(tmp_path):
    root = tmp_path / "project"
    output = root / "output"
    output.mkdir(parents=True)
    (root / "project.godot").write_text("[application]\n", encoding="utf-8")
    artifact = output / "game.pck"
    artifact.write_bytes(b"fixed-output")
    manifest = provenance.build(root, "4.7", "SHIP", {"Linux": artifact})
    artifact.unlink()
    artifact.symlink_to(root / "project.godot")
    problems = provenance.verify(manifest, root)
    assert len(problems) == 1
    assert "unsafe" in problems[0]
    assert "symlink artifact path" in problems[0]


def test_manifest_sha_cannot_be_qualified_from_detached_parent(tmp_path):
    root = tmp_path / "project"
    target_dir = root / "artifacts"
    target_dir.mkdir(parents=True)
    (root / "project.godot").write_text("[application]\n")
    target = target_dir / "native.bin"
    target.write_bytes(b"payload" * 256)
    manifest = provenance.build(root, "4.7", "SHIP", {"Linux": target})
    assert provenance.verify(manifest, root, root) == []
    target_dir.rename(root / "detached")
    new_dir = root / "artifacts"
    new_dir.mkdir()
    (new_dir / "native.bin").write_bytes(b"modified" * 256)
    problems = provenance.verify(manifest, root, root)
    assert any("mismatch" in issue or "changed" in issue for issue in problems)


def _manifest_fixture() -> provenance.Manifest:
    return provenance.Manifest(
        "example", "a" * 64, "Godot 4.x", "NO-SHIP",
    )


def test_bounded_manifest_file_roundtrip_preserves_schema(tmp_path):
    path = tmp_path / "manifest.json"
    fixture = _manifest_fixture()
    path.write_text(fixture.dumps(), encoding="utf-8")
    loaded = provenance.read_manifest_file(path)
    assert loaded.to_dict() == fixture.to_dict()
    assert loaded.dumps() == path.read_text(encoding="utf-8")


def test_manifest_byte_bound_rejects_before_unbounded_read(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_bytes(b"X" * 1000)
    with patch.object(provenance, "MAX_MANIFEST_BYTES", 64):
        with patch.object(
            provenance.os, "read",
            side_effect=AssertionError("oversized manifest must not be read"),
        ):
            with pytest.raises(ValueError, match="oversized"):
                provenance.read_manifest_file(path)


def test_manifest_reader_rejects_symlinked_intermediate_parent(tmp_path):
    external = tmp_path / "external"
    external.mkdir()
    (external / "manifest.json").write_text(_manifest_fixture().dumps())
    alias = tmp_path / "alias"
    alias.symlink_to(external, target_is_directory=True)
    with pytest.raises(OSError):
        provenance.read_manifest_file(alias / "manifest.json")


def test_manifest_reader_rejects_parent_swap_after_read(tmp_path):
    parent = tmp_path / "safe"
    parent.mkdir()
    (parent / "manifest.json").write_text(_manifest_fixture().dumps())
    external = tmp_path / "external"
    external.mkdir()
    (external / "manifest.json").write_text(_manifest_fixture().dumps())
    detached = tmp_path / "detached"
    original_read = os.read
    swapped = False

    def replace_parent_during_read(fd, count):
        nonlocal swapped
        data = original_read(fd, count)
        if data and not swapped:
            parent.rename(detached)
            parent.symlink_to(external, target_is_directory=True)
            swapped = True
        return data

    with patch.object(provenance.os, "read", side_effect=replace_parent_during_read):
        with pytest.raises((OSError, ValueError)):
            provenance.read_manifest_file(parent / "manifest.json")
    assert swapped
    assert (detached / "manifest.json").is_file()


def test_manifest_reader_rejects_same_size_data_mutation(tmp_path):
    path = tmp_path / "manifest.json"
    text = _manifest_fixture().dumps()
    path.write_text(text, encoding="utf-8")
    original_read = os.read
    changed = False

    def rewrite_after_read(fd, count):
        nonlocal changed
        data = original_read(fd, count)
        if data and not changed:
            changed = True
            path.write_text(text.replace("NO-SHIP", "UN-SHIP"), encoding="utf-8")
        return data

    with patch.object(provenance.os, "read", side_effect=rewrite_after_read):
        with pytest.raises(ValueError, match="changed during read"):
            provenance.read_manifest_file(path)
    assert changed


def test_cli_verify_fails_closed_on_oversized_manifest(tmp_path, capsys):
    from skeleton.godot_export.cli import main as godot_main
    path = tmp_path / "manifest.json"
    path.write_bytes(b"X" * 2048)
    with patch.object(provenance, "MAX_MANIFEST_BYTES", 128):
        status = godot_main([
            "verify", str(path), "--base", str(tmp_path),
        ])
    observed = capsys.readouterr().out
    assert status != 0
    result = __import__("json").loads(observed)
    assert result["ok"] is False
    assert result["problems"] == ["unsafe or malformed provenance manifest"]


def test_manifest_special_fifo_fails_without_blocking(tmp_path):
    if not hasattr(os, "mkfifo"):
        pytest.skip("FIFO unavailable")
    target = tmp_path / "manifest.json"
    os.mkfifo(target)
    with pytest.raises(ValueError, match="unsafe"):
        provenance.read_manifest_file(target)


def test_manifest_writer_create_only_roundtrip(tmp_path):
    path = tmp_path / "manifest.json"
    manifest = _manifest_fixture()
    provenance.write_manifest_file_new(path, manifest)
    assert path.read_bytes() == manifest.dumps().encode("utf-8")
    assert provenance.read_manifest_file(path).to_dict() == manifest.to_dict()
    assert path.stat().st_nlink == 1


def test_manifest_writer_cannot_replace_existing_receipt(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_bytes(b"original receipt")
    with pytest.raises(FileExistsError):
        provenance.write_manifest_file_new(path, _manifest_fixture())
    assert path.read_bytes() == b"original receipt"


def test_manifest_writer_refuses_final_symlink_and_intermediate_symlink(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    private = outside / "private.txt"
    private.write_bytes(b"untouched")
    existing = tmp_path / "linked.json"
    existing.symlink_to(private)
    with pytest.raises(FileExistsError):
        provenance.write_manifest_file_new(existing, _manifest_fixture())
    assert private.read_bytes() == b"untouched"

    alias = tmp_path / "alias"
    alias.symlink_to(outside, target_is_directory=True)
    with pytest.raises(OSError):
        provenance.write_manifest_file_new(alias / "new.json", _manifest_fixture())
    assert not (outside / "new.json").exists()


def test_manifest_writer_removes_partial_publication_on_fsync_failure(tmp_path):
    path = tmp_path / "manifest.json"
    with patch.object(provenance.os, "fsync", side_effect=OSError("disk full")):
        with pytest.raises(OSError, match="disk full"):
            provenance.write_manifest_file_new(path, _manifest_fixture())
    assert not path.exists()


def test_manifest_writer_refuses_same_size_in_place_tampering(tmp_path):
    path = tmp_path / "manifest.json"
    fixture = _manifest_fixture()
    original = provenance._read_manifest_bytes
    mutated = False

    def rewrite_before_readback(current):
        nonlocal mutated
        if not mutated:
            mutated = True
            data = path.read_bytes()
            assert b"NO-SHIP" in data
            path.write_bytes(data.replace(b"NO-SHIP", b"UN-SHIP"))
        return original(current)

    with patch.object(
        provenance, "_read_manifest_bytes", side_effect=rewrite_before_readback,
    ):
        with pytest.raises(ValueError, match="contents changed"):
            provenance.write_manifest_file_new(path, fixture)
    assert mutated
    assert not path.exists()


def test_manifest_writer_refuses_parent_substitution_during_readback(tmp_path):
    parent = tmp_path / "approved"
    parent.mkdir()
    path = parent / "manifest.json"
    outside = tmp_path / "outside"
    outside.mkdir()
    old = tmp_path / "old-approved"
    original = provenance._read_manifest_bytes
    swapped = False

    def substitute_parent(current):
        nonlocal swapped
        if not swapped:
            parent.rename(old)
            parent.symlink_to(outside, target_is_directory=True)
            swapped = True
        return original(current)

    with patch.object(
        provenance, "_read_manifest_bytes", side_effect=substitute_parent,
    ):
        with pytest.raises(OSError):
            provenance.write_manifest_file_new(path, _manifest_fixture())
    assert swapped
    assert not (outside / "manifest.json").exists()
    assert not (old / "manifest.json").exists()


def test_manifest_writer_refuses_oversized_output_without_creation(tmp_path):
    path = tmp_path / "manifest.json"
    with patch.object(provenance, "MAX_MANIFEST_BYTES", 32):
        with pytest.raises(ValueError, match="byte bound"):
            provenance.write_manifest_file_new(path, _manifest_fixture())
    assert not path.exists()


def test_cli_provenance_output_is_create_only(tmp_path, capsys):
    from skeleton.godot_export.cli import main as godot_main

    project = tmp_path / "project"
    project.mkdir()
    (project / "project.godot").write_text("[application]\n", encoding="utf-8")
    output = tmp_path / "receipt.json"
    args = [
        "provenance", str(project), "--verdict", "NO-SHIP",
        "--out", str(output),
    ]
    assert godot_main(args) == 0
    previous = output.read_bytes()
    assert provenance.read_manifest_file(output).verdict == "NO-SHIP"
    assert godot_main(args) == 2
    result = __import__("json").loads(capsys.readouterr().out)
    assert result == {"error": "unsafe or occupied provenance manifest output"}
    assert output.read_bytes() == previous



def _bound_project_manifest(tmp_path):
    """Project and output are separate to keep tree re-check deterministic."""
    root = tmp_path / "project"
    root.mkdir()
    (root / "project.godot").write_text("[application]\n", encoding="utf-8")
    artifact = tmp_path / "native.bin"
    artifact.write_bytes(b"sample-native-export" * 24)
    manifest = provenance.build(
        root, "Godot 4.7", "SHIP", {"Linux": artifact}, base=tmp_path,
    )
    assert provenance.verify(manifest, tmp_path, root) == []
    return root, artifact, manifest


def test_provenance_verifier_refuses_identical_tree_with_wrong_project_name(tmp_path):
    root, _artifact, manifest = _bound_project_manifest(tmp_path)
    impostor = tmp_path / "another-project"
    root.rename(impostor)
    # The file set and SHA remain identical; only the authorial identity is
    # different. A manifest for one project must not qualify another.
    assert provenance.tree_digest(impostor) == manifest.tree
    problems = provenance.verify(manifest, tmp_path, impostor)
    assert "project identity differs from manifest" in problems
    assert "project tree changed since manifest" not in problems


def test_provenance_verifier_binds_git_pin_to_exact_source_revision(tmp_path):
    root, _artifact, manifest = _bound_project_manifest(tmp_path)
    manifest.git = "a" * 40
    with patch.object(provenance, "git_head", return_value="b" * 40):
        problems = provenance.verify(manifest, tmp_path, root)
    assert "git source pin differs from manifest" in problems
    with patch.object(provenance, "git_head", return_value="a" * 40):
        assert provenance.verify(manifest, tmp_path, root) == []


def test_provenance_verifier_rejects_unavailable_pinned_git_revision(tmp_path):
    root, _artifact, manifest = _bound_project_manifest(tmp_path)
    manifest.git = "b" * 40
    with patch.object(provenance, "git_head", return_value=None):
        problems = provenance.verify(manifest, tmp_path, root)
    assert "git source pin differs from manifest" in problems


def test_provenance_cli_requires_source_to_claim_ok(tmp_path, capsys):
    from skeleton.godot_export import cli

    root, _artifact, manifest = _bound_project_manifest(tmp_path)
    path = tmp_path / "manifest.json"
    provenance.write_manifest_file_new(path, manifest)
    assert cli.main([
        "verify", str(path), "--base", str(tmp_path),
    ]) == 1
    result = __import__("json").loads(capsys.readouterr().out)
    assert result["ok"] is False
    assert "project source tree was not supplied for verification" in result["problems"]
    assert cli.main([
        "verify", str(path), "--base", str(tmp_path),
        "--project", str(root),
    ]) == 0
    qualified = __import__("json").loads(capsys.readouterr().out)
    assert qualified == {"ok": True, "problems": []}


def test_artifact_identity_requires_nonempty_payload_and_safe_label():
    digest = "a" * 64
    with pytest.raises(ValueError, match="invalid artifact size"):
        provenance.Artifact("Linux", "linux/game.bin", digest, 0)
    for preset in ("Linux\nSHIP", "Linux\r", "\tWeb", "Linux\x7f", " Web"):
        with pytest.raises(ValueError, match="invalid artifact preset"):
            provenance.Artifact(preset, "linux/game.bin", digest, 1)
    assert provenance.Artifact("Linux", "linux/game.bin", digest, 1).size == 1


def test_manifest_identity_rejects_control_chars_and_whitespace():
    digest = "a" * 64
    for bad in ("project\nSHIP", "\tproject", "project ", "\x7fproject"):
        with pytest.raises(ValueError, match="invalid project identity"):
            provenance.Manifest(bad, digest, "Godot 4.7", "SHIP")
    for bad in ("Godot\nSHIP", " Godot", "Godot\t", "Godot\x7f"):
        with pytest.raises(ValueError, match="invalid engine identity"):
            provenance.Manifest("project", digest, bad, "SHIP")


def test_distinct_export_presets_cannot_reuse_one_artifact_path():
    digest = "a" * 64
    with pytest.raises(ValueError, match="artifact path reused"):
        provenance.Manifest(
            "project", digest, "Godot 4.7", "SHIP",
            artifacts=[
                provenance.Artifact("Linux", "same/file.bin", digest, 10),
                provenance.Artifact("Web", "same/file.bin", digest, 10),
            ],
        )
    distinct = provenance.Manifest(
        "project", digest, "Godot 4.7", "SHIP",
        artifacts=[
            provenance.Artifact("Linux", "linux/game.bin", digest, 10),
            provenance.Artifact("Web", "web/index.html", digest, 10),
        ],
    )
    assert len(distinct.artifacts) == 2


def test_zero_byte_export_cannot_mint_ship_artifact_receipt(tmp_path):
    source = tmp_path / "project"
    source.mkdir()
    (source / "project.godot").write_text("[application]\n", encoding="utf-8")
    empty = tmp_path / "empty.bin"
    empty.write_bytes(b"")
    with pytest.raises(ValueError, match="invalid artifact size"):
        provenance.build(
            source, "Godot 4.7", "SHIP", {"Linux": empty}, base=tmp_path,
        )
