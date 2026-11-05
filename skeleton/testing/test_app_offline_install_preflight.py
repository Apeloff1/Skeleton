"""Read-only preflight -> atomic install -> replay acceptance and denial paths."""
from __future__ import annotations

import json
import pytest

from skeleton.app.cli import run_app_cli


@pytest.fixture
def package(tmp_path, capsys):
    source = tmp_path / "source"
    assert run_app_cli([
        "studio-journey", "--onboard", "--project-id", "preflight-original",
        "--title", "Original Passage", "--seed", "1733",
        "--output", str(source), "--trusted-local-operator",
    ]) == 0
    manifest = json.loads(capsys.readouterr().out)[
        "trusted_in_process_manifest_sha256"
    ]
    archive = tmp_path / "delivery.zip"
    assert run_app_cli([
        "studio-journey", "--package-existing", "--output", str(source),
        "--archive", str(archive), "--expected-manifest-sha256", manifest,
        "--trusted-local-operator",
    ]) == 0
    pin = json.loads(capsys.readouterr().out)["independent_archive_sha256"]
    return archive, pin, manifest


def args(archive, pin, manifest, target, *, preflight=True):
    return [
        "studio-journey", "--preflight-install" if preflight else "--install-archive",
        "--archive", str(archive), "--expected-archive-sha256", pin,
        "--expected-manifest-sha256", manifest,
        "--output", str(target), "--trusted-local-operator",
    ]


def test_preflight_does_not_reserve_and_installer_rechecks(package, tmp_path, capsys):
    archive, pin, manifest = package
    target = tmp_path / "installed"
    assert run_app_cli(args(archive, pin, manifest, target)) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["archive_integrity_verified"] is True
    assert receipt["destination_reserved"] is False
    assert receipt["source_installation_verified"] is False
    assert receipt["offline_gameplay_reexecuted"] is False
    assert receipt["release_certified"] is False
    assert not target.exists()
    assert run_app_cli(args(archive, pin, manifest, target, preflight=False)) == 0
    installed = json.loads(capsys.readouterr().out)
    assert installed["source_installation_verified"] is True
    assert installed["offline_gameplay_reexecuted"] is True
    assert run_app_cli(args(archive, pin, manifest, target)) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"


@pytest.mark.parametrize("fault", ["archive_pin", "manifest_pin", "archive_tamper"])
def test_preflight_rejects_untrusted_package_without_destination(package, tmp_path, capsys, fault):
    archive, pin, manifest = package
    target = tmp_path / "not-reserved"
    if fault == "archive_pin":
        pin = "0" * 64
    elif fault == "manifest_pin":
        manifest = "0" * 64
    else:
        archive.write_bytes(archive.read_bytes() + b"tamper")
    assert run_app_cli(args(archive, pin, manifest, target)) == 2
    assert not target.exists()
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"


def test_preflight_rejects_symlinked_parent(package, tmp_path, capsys):
    archive, pin, manifest = package
    owned = tmp_path / "owned"
    owned.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(owned, target_is_directory=True)
    assert run_app_cli(args(archive, pin, manifest, alias / "game")) == 2
    assert not (owned / "game").exists()
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"


@pytest.mark.parametrize("extra", [
    ["--install-archive"], ["--reconcile-install"], ["--onboard"],
    ["--migrate-progress"], ["--preflight-migration"],
    ["--check-archive-save"], ["--moves", "up"], ["--save", "new.json"],
    ["--receipt", "receipt.json"], ["--mirror-attempts", "65"],
])
def test_preflight_rejects_ambiguous_mode(package, tmp_path, capsys, extra):
    archive, pin, manifest = package
    target = tmp_path / "never-created"
    assert run_app_cli(args(archive, pin, manifest, target) + extra) == 2
    assert not target.exists()
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"


def test_preflight_requires_explicit_operator(package, tmp_path, capsys):
    archive, pin, manifest = package
    target = tmp_path / "never-created"
    command = args(archive, pin, manifest, target)
    command.remove("--trusted-local-operator")
    assert run_app_cli(command) == 2
    assert not target.exists()
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"
