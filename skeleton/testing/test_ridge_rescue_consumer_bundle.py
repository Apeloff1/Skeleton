"""Portable Python zipapp: original source, deterministic archive and runnable play."""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import zipfile

import pytest

from skeleton.game.gameplay.ridge_rescue.consumer_bundle import (
    build_bytes, verify_bytes, build_bundle, BundleError,
)
from skeleton.game.gameplay.ridge_rescue.consumer_store import SlotStore


def test_zipapp_is_deterministic_and_source_bound():
    first = build_bytes()
    second = build_bytes()
    assert first == second
    verified = verify_bytes(first)
    assert verified["sha256"] == hashlib.sha256(first).hexdigest()
    assert not verified["release_certified"]
    with zipfile.ZipFile(__import__("io").BytesIO(first)) as archive:
        names = archive.namelist()
        assert "ridge_rescue/consumer_cli.py" in names
        assert "ridge_rescue/cinder_ridge_campaign.json" in names
        assert not any("__pycache__" in name for name in names)


def test_zipapp_rejects_corrupt_bytes():
    with pytest.raises(BundleError):
        verify_bytes(b"not a zip")
    with pytest.raises(BundleError):
        verify_bytes(b"0" * 2_000_001)


def test_bundle_publication_create_only(tmp_path):
    store = SlotStore(tmp_path / "saves")
    report = build_bundle(store)
    assert report["python_required"]
    assert os.path.isfile(report["path"])
    with pytest.raises(BundleError, match="create-only"):
        build_bundle(store)


def test_packaged_game_acceptance_executes_without_checkout(tmp_path):
    store = SlotStore(tmp_path / "saves")
    bundle = build_bundle(store)
    environment = os.environ.copy()
    environment["PYTHONPATH"] = ""
    environment["XDG_DATA_HOME"] = str(tmp_path / "user-data")
    result = subprocess.run(
        [sys.executable, bundle["path"], "acceptance"],
        cwd=str(tmp_path), env=environment, capture_output=True, text=True,
        timeout=90, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert '"portable_export_verified":true' in result.stdout
