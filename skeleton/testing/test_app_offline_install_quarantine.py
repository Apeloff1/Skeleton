"""Real archive -> partial installation quarantine -> read-only inspection."""
from __future__ import annotations

import json
from zipfile import ZipFile

import pytest

from skeleton.app.cli import run_app_cli


@pytest.fixture
def package(tmp_path, capsys):
    source = tmp_path / "original"
    assert run_app_cli([
        "studio-journey", "--onboard", "--project-id", "quarantine-original",
        "--title", "Original Harbor", "--seed", "1735",
        "--output", str(source), "--trusted-local-operator",
    ]) == 0
    manifest = json.loads(capsys.readouterr().out)[
        "trusted_in_process_manifest_sha256"
    ]
    archive = tmp_path / "original.zip"
    assert run_app_cli([
        "studio-journey", "--package-existing", "--output", str(source),
        "--archive", str(archive), "--expected-manifest-sha256", manifest,
        "--trusted-local-operator",
    ]) == 0
    pin = json.loads(capsys.readouterr().out)["independent_archive_sha256"]
    return archive, pin, manifest


def args(root, archive, pin, manifest):
    return [
        "studio-journey", "--inspect-install-quarantine", "--output", str(root),
        "--archive", str(archive), "--expected-archive-sha256", pin,
        "--expected-manifest-sha256", manifest, "--trusted-local-operator",
    ]


def test_partial_directory_is_classified_without_mutation(package, tmp_path, capsys):
    archive, pin, manifest = package
    partial = tmp_path / "quarantine"
    partial.mkdir(mode=0o700)
    with ZipFile(archive) as bundle:
        release = bundle.read("release.json")
    (partial / "release.json").write_bytes(release)
    assert run_app_cli(args(partial, archive, pin, manifest)) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["missing_files"] > 0
    assert receipt["mismatched_files"] == 0
    assert receipt["offline_gameplay_reexecuted"] is False
    assert receipt["quarantine_cleared"] is False
    assert receipt["release_certified"] is False
    assert (partial / "release.json").read_bytes() == release


def test_extra_and_corrupt_regular_files_are_reported(package, tmp_path, capsys):
    archive, pin, manifest = package
    partial = tmp_path / "quarantine"
    partial.mkdir(mode=0o700)
    (partial / "release.json").write_bytes(b"corrupted")
    (partial / "extra.txt").write_bytes(b"not in canonical package")
    assert run_app_cli(args(partial, archive, pin, manifest)) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["extra_files"] == 1
    assert receipt["mismatched_files"] == 1
    assert receipt["missing_files"] > 0
    assert receipt["installation_approved"] is False


def test_complete_installed_source_can_be_replayed_but_not_released(package, tmp_path, capsys):
    archive, pin, manifest = package
    installed = tmp_path / "installed"
    command = [
        "studio-journey", "--install-archive", "--output", str(installed),
        "--archive", str(archive), "--expected-archive-sha256", pin,
        "--expected-manifest-sha256", manifest, "--trusted-local-operator",
    ]
    assert run_app_cli(command) == 0
    capsys.readouterr()
    assert run_app_cli(args(installed, archive, pin, manifest)) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["complete_inventory_matches_archive"] is True
    assert receipt["offline_gameplay_reexecuted"] is True
    assert receipt["quarantine_cleared"] is False
    assert receipt["native_device_qualified"] is False


def test_symlinked_quarantine_entry_fails_closed(package, tmp_path, capsys):
    archive, pin, manifest = package
    partial = tmp_path / "quarantine"
    partial.mkdir(mode=0o700)
    (partial / "release.json").symlink_to(archive)
    assert run_app_cli(args(partial, archive, pin, manifest)) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"


@pytest.mark.parametrize("extra", [
    ["--install-archive"], ["--reconcile-install"], ["--preflight-install"],
    ["--migrate-progress"], ["--check-archive-save"],
    ["--moves", "up"], ["--save", "save.json"],
])
def test_quarantine_inspection_rejects_mode_mixing(package, tmp_path, capsys, extra):
    archive, pin, manifest = package
    partial = tmp_path / "quarantine"
    partial.mkdir(mode=0o700)
    assert run_app_cli(args(partial, archive, pin, manifest) + extra) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"

def test_real_failed_install_remains_quarantined_and_inspectable(
    package, tmp_path, capsys, monkeypatch,
):
    from skeleton.app import offline_archive_install

    archive, pin, manifest = package
    target = tmp_path / "partial-install"
    original = offline_archive_install._write_file
    written = 0

    def fail_after_first(*args, **kwargs):
        nonlocal written
        if written >= 1:
            raise offline_archive_install.OfflineSourceInstallError(
                "injected write failure"
            )
        written += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(offline_archive_install, "_write_file", fail_after_first)
    assert run_app_cli([
        "studio-journey", "--install-archive", "--output", str(target),
        "--archive", str(archive), "--expected-archive-sha256", pin,
        "--expected-manifest-sha256", manifest, "--trusted-local-operator",
    ]) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"
    assert target.is_dir()
    assert run_app_cli(args(target, archive, pin, manifest)) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["missing_files"] > 0
    assert receipt["quarantine_cleared"] is False
    assert receipt["source_mutated"] is False


def test_source_mutation_during_partial_inspection_fails_closed(
    package, tmp_path, monkeypatch,
):
    from skeleton.app import offline_install_quarantine

    archive, pin, manifest = package
    target = tmp_path / "partial-install"
    target.mkdir(mode=0o700)
    with ZipFile(archive) as bundle:
        original_release = bundle.read("release.json")
    (target / "release.json").write_bytes(original_release)
    original_read = offline_install_quarantine._read
    mutated = False

    def mutate_after_read(fd, name, limit, *, owner_controlled=False):
        nonlocal mutated
        data = original_read(fd, name, limit, owner_controlled=owner_controlled)
        if name == "release.json" and not mutated:
            mutated = True
            (target / "release.json").write_bytes(b"x" * len(data))
        return data

    monkeypatch.setattr(offline_install_quarantine, "_read", mutate_after_read)
    with pytest.raises(offline_install_quarantine.OfflineInstallQuarantineError):
        offline_install_quarantine.inspect_offline_install_quarantine(
            target, archive, expected_archive_sha256=pin,
            expected_manifest_sha256=manifest, authorized=True,
        )
