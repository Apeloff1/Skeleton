"""Real app source -> deterministic offline ZIP -> independent integrity inspection."""
from __future__ import annotations

import json
import os
from zipfile import ZipFile

import pytest

from skeleton.app.cli import run_app_cli


def _build(tmp_path, capsys):
    root = tmp_path / "original-game"
    assert run_app_cli([
        "studio-journey", "--onboard", "--project-id", "zip-original",
        "--title", "Original Lantern", "--seed", "1729",
        "--output", str(root), "--trusted-local-operator",
    ]) == 0
    return root, json.loads(capsys.readouterr().out)["trusted_in_process_manifest_sha256"]


def _package(root, manifest, target):
    return [
        "studio-journey", "--package-existing", "--output", str(root),
        "--expected-manifest-sha256", manifest,
        "--archive", str(target), "--trusted-local-operator",
    ]


def _inspect(target, archive_pin, manifest):
    return [
        "studio-journey", "--inspect-archive", "--archive", str(target),
        "--expected-archive-sha256", archive_pin,
        "--expected-manifest-sha256", manifest, "--trusted-local-operator",
    ]


def test_deterministic_game_archive_and_independent_read_only_inspection(tmp_path, capsys):
    root, manifest = _build(tmp_path, capsys)
    original_release = (root / "release.json").read_bytes()
    left, right = tmp_path / "first.zip", tmp_path / "second.zip"
    assert run_app_cli(_package(root, manifest, left)) == 0
    first = json.loads(capsys.readouterr().out)
    assert run_app_cli(_package(root, manifest, right)) == 0
    second = json.loads(capsys.readouterr().out)
    assert left.read_bytes() == right.read_bytes()
    assert first["independent_archive_sha256"] == second["independent_archive_sha256"]
    assert first["source_gameplay_reexecuted"] is True
    assert first["package_signed"] is False
    assert first["native_device_qualified"] is False
    assert first["release_certified"] is False
    assert left.stat().st_mode & 0o077 == 0
    with ZipFile(left) as archive:
        names = archive.namelist()
        assert names == sorted(names)
        assert "index.html" in names
        assert "godot/project.godot" in names
        assert "proof/verified_solution.json" in names
        assert archive.read("release.json") == original_release
    before = left.read_bytes()
    assert run_app_cli(_inspect(left, first["independent_archive_sha256"], manifest)) == 0
    inspected = json.loads(capsys.readouterr().out)
    assert inspected["archive_integrity_verified"] is True
    assert inspected["source_gameplay_reexecuted_now"] is False
    assert inspected["package_signed"] is False
    assert inspected["release_certified"] is False
    assert left.read_bytes() == before
    assert (root / "release.json").read_bytes() == original_release


@pytest.mark.parametrize("case", ["wrong_archive_pin", "wrong_manifest_pin", "mutated_zip", "group_readable", "symlink", "hardlink"])
def test_archive_inspection_fails_closed_on_invalid_custody(tmp_path, capsys, case):
    root, manifest = _build(tmp_path, capsys)
    archive = tmp_path / "original.zip"
    assert run_app_cli(_package(root, manifest, archive)) == 0
    result = json.loads(capsys.readouterr().out)
    pin = result["independent_archive_sha256"]
    if case == "wrong_archive_pin":
        pin = "0" * 64
    elif case == "wrong_manifest_pin":
        manifest = "0" * 64
    elif case == "mutated_zip":
        archive.write_bytes(archive.read_bytes() + b"extra")
    elif case == "group_readable":
        archive.chmod(0o640)
    elif case == "symlink":
        alias = tmp_path / "alias.zip"
        alias.symlink_to(archive)
        archive = alias
    else:
        alias = tmp_path / "linked.zip"
        alias.hardlink_to(archive)
        archive = alias
    assert run_app_cli(_inspect(archive, pin, manifest)) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"


def test_archive_destination_collision_never_clobbers_operator_file(tmp_path, capsys):
    root, manifest = _build(tmp_path, capsys)
    target = tmp_path / "existing.zip"
    target.write_bytes(b"operator-owned")
    assert run_app_cli(_package(root, manifest, target)) == 2
    assert target.read_bytes() == b"operator-owned"
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"


def test_archive_rejects_source_tamper_without_publishing(tmp_path, capsys):
    root, manifest = _build(tmp_path, capsys)
    (root / "index.html").write_text("tampered", encoding="utf-8")
    target = tmp_path / "unpublished.zip"
    assert run_app_cli(_package(root, manifest, target)) == 2
    assert not target.exists()
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"


def test_archive_cannot_be_placed_inside_source_package(tmp_path, capsys):
    root, manifest = _build(tmp_path, capsys)
    target = root / "archive.zip"
    assert run_app_cli(_package(root, manifest, target)) == 2
    assert not target.exists()
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"


def test_archive_rejects_symlinked_parent_before_source_mutation(tmp_path, capsys):
    root, manifest = _build(tmp_path, capsys)
    owned = tmp_path / "owned"
    owned.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(owned, target_is_directory=True)
    target = alias / "archive.zip"
    assert run_app_cli(_package(root, manifest, target)) == 2
    assert not (owned / "archive.zip").exists()
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"


@pytest.mark.parametrize("case", ["no_authority", "inspect_with_output", "package_with_archive_pin", "missing_manifest", "mixed_play", "mixed_compare"])
def test_archive_modes_require_exact_authority_and_inputs(tmp_path, capsys, case):
    root = tmp_path / "source"
    archive = tmp_path / "out.zip"
    base = [
        "studio-journey", "--package-existing", "--output", str(root),
        "--expected-manifest-sha256", "a" * 64, "--archive", str(archive),
        "--trusted-local-operator",
    ]
    if case == "no_authority":
        base.remove("--trusted-local-operator")
    elif case == "inspect_with_output":
        base.remove("--package-existing")
        base.append("--inspect-archive")
        base.extend(["--expected-archive-sha256", "b" * 64])
    elif case == "package_with_archive_pin":
        base.extend(["--expected-archive-sha256", "b" * 64])
    elif case == "missing_manifest":
        base.remove("--expected-manifest-sha256")
        base.remove("a" * 64)
    elif case == "mixed_play":
        base.append("--play-existing")
    else:
        base.append("--compare-saves")
    assert run_app_cli(base) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"


def test_archive_options_not_accepted_during_new_game_onboarding(tmp_path, capsys):
    root = tmp_path / "never-built"
    assert run_app_cli([
        "studio-journey", "--onboard", "--project-id", "original",
        "--title", "Original", "--seed", "1", "--output", str(root),
        "--archive", str(tmp_path / "out.zip"), "--trusted-local-operator",
    ]) == 2
    assert not root.exists()
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"


def test_archive_write_error_does_not_leave_partial_publication(tmp_path, capsys, monkeypatch):
    from skeleton.app import offline_delivery_archive
    root, manifest = _build(tmp_path, capsys)
    target = tmp_path / "no-partial.zip"
    original_link = offline_delivery_archive.os.link
    def fail_link(*_args, **_kwargs):
        raise OSError("injected archive link failure")
    monkeypatch.setattr(offline_delivery_archive.os, "link", fail_link)
    assert run_app_cli(_package(root, manifest, target)) == 2
    assert not target.exists()
    assert not list(tmp_path.glob(".offline-archive-*"))
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"
    monkeypatch.setattr(offline_delivery_archive.os, "link", original_link)

def test_archive_destination_race_preserves_unrelated_owner_file(tmp_path, capsys, monkeypatch):
    from skeleton.app import offline_delivery_archive

    root, manifest = _build(tmp_path, capsys)
    target = tmp_path / "raced.zip"
    original_link = offline_delivery_archive.os.link

    def race_link(src, dst, *, src_dir_fd, dst_dir_fd, follow_symlinks):
        handle = os.open(dst, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600,
                         dir_fd=dst_dir_fd)
        try:
            os.write(handle, b"other-operator-data")
            os.fsync(handle)
        finally:
            os.close(handle)
        return original_link(src, dst, src_dir_fd=src_dir_fd,
                             dst_dir_fd=dst_dir_fd, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(offline_delivery_archive.os, "link", race_link)
    assert run_app_cli(_package(root, manifest, target)) == 2
    assert target.read_bytes() == b"other-operator-data"
    assert not list(tmp_path.glob(".offline-archive-*"))
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"


def test_archive_postpublication_mutation_never_reports_success(tmp_path, capsys, monkeypatch):
    from skeleton.app import offline_delivery_archive

    root, manifest = _build(tmp_path, capsys)
    target = tmp_path / "quarantine.zip"
    original_publish = offline_delivery_archive._publish_private_archive

    def mutate_after_publish(data, destination):
        original_publish(data, destination)
        with open(destination, "ab") as output:
            output.write(b"untrusted-mutation")

    monkeypatch.setattr(offline_delivery_archive, "_publish_private_archive",
                        mutate_after_publish)
    assert run_app_cli(_package(root, manifest, target)) == 2
    assert target.exists()  # explicit owner quarantine; never unsafe path deletion
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"


def test_archive_source_mutation_after_publication_is_not_certified(tmp_path, capsys, monkeypatch):
    from skeleton.app import offline_delivery_archive

    root, manifest = _build(tmp_path, capsys)
    target = tmp_path / "source-changed.zip"
    original_publish = offline_delivery_archive._publish_private_archive

    def mutate_source_after_publish(data, destination):
        original_publish(data, destination)
        (root / "index.html").write_text("mutated after snapshot", encoding="utf-8")

    monkeypatch.setattr(offline_delivery_archive, "_publish_private_archive",
                        mutate_source_after_publish)
    assert run_app_cli(_package(root, manifest, target)) == 2
    assert target.exists()  # source archive may be intact; handoff still blocked
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"


def test_independently_pinned_noncanonical_zip_is_rejected(tmp_path, capsys):
    from hashlib import sha256
    from io import BytesIO
    from zipfile import ZipFile, ZipInfo, ZIP_STORED

    root, manifest = _build(tmp_path, capsys)
    target = tmp_path / "canonical.zip"
    assert run_app_cli(_package(root, manifest, target)) == 0
    capsys.readouterr()
    with ZipFile(target) as original:
        files = {name: original.read(name) for name in original.namelist()}
    changed = BytesIO()
    with ZipFile(changed, "w", compression=ZIP_STORED) as archive:
        for name in sorted(files):
            info = ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_STORED
            info.create_system = 3
            info.external_attr = (0o100600 << 16)
            archive.writestr(info, files[name])
    target.write_bytes(changed.getvalue())
    pin = sha256(target.read_bytes()).hexdigest()
    assert run_app_cli(_inspect(target, pin, manifest)) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"


def test_independently_pinned_zip_with_unexpected_entry_is_rejected(tmp_path, capsys):
    from hashlib import sha256
    from zipfile import ZIP_STORED

    root, manifest = _build(tmp_path, capsys)
    target = tmp_path / "extra-entry.zip"
    assert run_app_cli(_package(root, manifest, target)) == 0
    capsys.readouterr()
    with ZipFile(target, "a", compression=ZIP_STORED) as archive:
        archive.writestr("unexpected.txt", b"extra")
    pin = sha256(target.read_bytes()).hexdigest()
    assert run_app_cli(_inspect(target, pin, manifest)) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"


def test_archive_readback_preserves_original_export_files(tmp_path, capsys):
    root, manifest = _build(tmp_path, capsys)
    source_before = {
        "index.html": (root / "index.html").read_bytes(),
        "release.json": (root / "release.json").read_bytes(),
        "godot/project.godot": (root / "godot" / "project.godot").read_bytes(),
    }
    target = tmp_path / "handoff.zip"
    assert run_app_cli(_package(root, manifest, target)) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["source_gameplay_reexecuted"] is True
    assert result["archived_files"] >= 7
    for path, expected_bytes in source_before.items():
        assert (root / path).read_bytes() == expected_bytes
    assert run_app_cli(_inspect(
        target, result["independent_archive_sha256"], manifest,
    )) == 0
    assert json.loads(capsys.readouterr().out)["archive_integrity_verified"] is True



@pytest.mark.skipif(os.name != "posix" or not hasattr(os, "mkfifo"),
                    reason="POSIX FIFO rejection contract")
def test_archive_inspection_rejects_fifo_without_blocking(tmp_path, capsys):
    fifo = tmp_path / "not-a-regular-archive.zip"
    os.mkfifo(fifo, 0o600)
    assert run_app_cli(_inspect(fifo, "a" * 64, "b" * 64)) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"


def test_archive_dotdot_alias_into_original_source_is_rejected(
    tmp_path, capsys,
):
    """Archive publisher must not write through an existing sibling/.. alias."""
    from skeleton.app.offline_delivery_archive import (
        OfflineGameArchiveError, publish_offline_game_archive,
    )

    root, manifest = _build(tmp_path, capsys)
    sibling = tmp_path / "existing-archive-sibling"
    sibling.mkdir()
    disguised = sibling / ".." / root.name / "untrusted.zip"
    with pytest.raises(OfflineGameArchiveError, match="inside game source"):
        publish_offline_game_archive(
            root, disguised, expected_manifest_sha256=manifest,
            authorized=True,
        )
    assert not (root / "untrusted.zip").exists()
    assert not list(root.glob("*.zip"))
