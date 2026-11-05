"""End-to-end pinned source archive install -> verify -> actual offline gameplay."""
from __future__ import annotations

import json

import pytest

from skeleton.app.cli import run_app_cli


def _archive(tmp_path, capsys):
    source = tmp_path / "source-game"
    assert run_app_cli([
        "studio-journey", "--onboard", "--project-id", "install-original",
        "--title", "Original Lantern", "--seed", "1729",
        "--output", str(source), "--trusted-local-operator",
    ]) == 0
    manifest = json.loads(capsys.readouterr().out)["trusted_in_process_manifest_sha256"]
    archive = tmp_path / "delivery.zip"
    assert run_app_cli([
        "studio-journey", "--package-existing", "--output", str(source),
        "--archive", str(archive), "--expected-manifest-sha256", manifest,
        "--trusted-local-operator",
    ]) == 0
    pin = json.loads(capsys.readouterr().out)["independent_archive_sha256"]
    return source, archive, pin, manifest


def _install(archive, pin, manifest, target):
    return [
        "studio-journey", "--install-archive", "--archive", str(archive),
        "--expected-archive-sha256", pin,
        "--expected-manifest-sha256", manifest,
        "--output", str(target), "--trusted-local-operator",
    ]


def test_full_first_run_archive_install_play_and_save(tmp_path, capsys):
    source, archive, pin, manifest = _archive(tmp_path, capsys)
    installed = tmp_path / "installed-game"
    assert run_app_cli(_install(archive, pin, manifest, installed)) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["schema"] == "skeleton.app.offline_source_install.v1"
    assert result["offline_gameplay_reexecuted"] is True
    assert result["source_installation_verified"] is True
    assert result["native_device_qualified"] is False
    assert result["package_signed"] is False
    assert result["release_certified"] is False
    assert (installed / "index.html").read_bytes() == (source / "index.html").read_bytes()
    assert (installed / "godot" / "project.godot").read_bytes() == (
        source / "godot" / "project.godot"
    ).read_bytes()
    assert run_app_cli([
        "studio-journey", "--verify-existing", "--output", str(installed),
        "--expected-manifest-sha256", manifest, "--trusted-local-operator",
    ]) == 0
    capsys.readouterr()
    save = tmp_path / "installed-play-save.json"
    assert run_app_cli([
        "studio-journey", "--play-existing", "--output", str(installed),
        "--expected-manifest-sha256", manifest, "--moves", "up,right",
        "--save", str(save), "--trusted-local-operator",
    ]) == 0
    play = json.loads(capsys.readouterr().out)
    assert play["action_count"] == 2
    assert play["offline_gameplay_reexecuted"] is True
    assert save.is_file()
    assert (installed / "release.json").read_bytes() == (
        source / "release.json"
    ).read_bytes()


def test_installer_never_replaces_existing_owner_directory(tmp_path, capsys):
    _source, archive, pin, manifest = _archive(tmp_path, capsys)
    target = tmp_path / "existing"
    target.mkdir()
    marker = target / "operator.txt"
    marker.write_text("preserve", encoding="utf-8")
    assert run_app_cli(_install(archive, pin, manifest, target)) == 2
    assert marker.read_text(encoding="utf-8") == "preserve"
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"


@pytest.mark.parametrize("case", ["wrong_archive", "wrong_manifest", "tampered_zip", "symlink_archive"])
def test_installer_rejects_invalid_archive_before_reserving_target(tmp_path, capsys, case):
    _source, archive, pin, manifest = _archive(tmp_path, capsys)
    target = tmp_path / "must-not-exist"
    if case == "wrong_archive":
        pin = "0" * 64
    elif case == "wrong_manifest":
        manifest = "0" * 64
    elif case == "tampered_zip":
        archive.write_bytes(archive.read_bytes() + b"tamper")
    else:
        alias = tmp_path / "alias.zip"
        alias.symlink_to(archive)
        archive = alias
    assert run_app_cli(_install(archive, pin, manifest, target)) == 2
    assert not target.exists()
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"


def test_installer_rejects_symlinked_parent_without_mutation(tmp_path, capsys):
    _source, archive, pin, manifest = _archive(tmp_path, capsys)
    owned = tmp_path / "owned"
    owned.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(owned, target_is_directory=True)
    target = alias / "new-game"
    assert run_app_cli(_install(archive, pin, manifest, target)) == 2
    assert not (owned / "new-game").exists()
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"


@pytest.mark.parametrize("extra", [
    ["--play-existing"], ["--package-existing"], ["--inspect-archive"],
    ["--compare-saves"], ["--onboard"], ["--moves", "up"],
    ["--save", "unused.json"], ["--intent", "unused.json"],
])
def test_installer_rejects_ambiguous_mode_combinations(tmp_path, capsys, extra):
    target = tmp_path / "never-reserved"
    args = _install(tmp_path / "archive.zip", "a" * 64, "b" * 64, target)
    assert run_app_cli(args + extra) == 2
    assert not target.exists()
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"


def test_installer_requires_trusted_operator_acknowledgement(tmp_path, capsys):
    target = tmp_path / "never-reserved"
    args = _install(tmp_path / "archive.zip", "a" * 64, "b" * 64, target)
    args.remove("--trusted-local-operator")
    assert run_app_cli(args) == 2
    assert not target.exists()
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"


def test_failed_installer_leaves_quarantined_partial_directory_not_success(tmp_path, capsys, monkeypatch):
    from skeleton.app import offline_archive_install

    _source, archive, pin, manifest = _archive(tmp_path, capsys)
    target = tmp_path / "quarantined"
    def fail_write(*_args, **_kwargs):
        raise offline_archive_install.OfflineSourceInstallError("injected disk failure")
    monkeypatch.setattr(offline_archive_install, "_write_file", fail_write)
    assert run_app_cli(_install(archive, pin, manifest, target)) == 2
    assert target.is_dir()
    assert not (target / "release.json").exists()
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"
