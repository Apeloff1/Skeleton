"""Exported original-game package can be verified and played without the source file."""
from copy import deepcopy
from pathlib import Path
import pytest
from skeleton.game.gameplay.ridge_rescue.schema import parse_world
from skeleton.game.gameplay.ridge_rescue.package import build_package, verify_package, play_package, PackageError
from skeleton.game.gameplay.ridge_rescue.custody import verify_run, digest
from skeleton.game.gameplay.ridge_rescue.acceptance import acceptance_actions, ACCEPTANCE_SOURCE

WORLD = parse_world(ACCEPTANCE_SOURCE.read_bytes())

def test_package_source_manifest_roundtrip():
    package = build_package(WORLD)
    verified = verify_package(package)
    assert verified["world"] == WORLD
    assert verified["manifest"]["source_sha256"] == digest(package["payload"]["world"])
    assert verified["manifest"]["offline"] is True

def test_package_runs_real_protection_ending():
    package = build_package(WORLD)
    bundle = play_package(package, acceptance_actions("protect"))
    assert verify_run(bundle)["state"]["status"] == "won:protect"

def test_manifest_and_source_tamper_rejected_even_when_rehashed():
    package = build_package(WORLD)
    package["payload"]["manifest"]["max_turns"] = 999
    package["sha256"] = digest(package["payload"])
    with pytest.raises(PackageError):
        verify_package(package)
    package = build_package(WORLD)
    package["payload"]["world"]["start"] = [100, 0]
    package["sha256"] = digest(package["payload"])
    with pytest.raises(PackageError):
        verify_package(package)

def test_unsupported_and_oversized_packages_fail_closed():
    with pytest.raises(PackageError):
        verify_package(b"x" * 192001)
    package = build_package(WORLD)
    package["payload"]["schema"] = "ridge.rescue.package.v2"
    package["sha256"] = digest(package["payload"])
    with pytest.raises(PackageError):
        verify_package(package)
