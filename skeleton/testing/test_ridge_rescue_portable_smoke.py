"""Executable consumer qualification: real portable Python zipapp gameplay.

A pass here is host-specific smoke evidence, never a Windows/device release.
"""
from __future__ import annotations

from skeleton.game.gameplay.ridge_rescue.consumer_smoke import (
    run_smoke, run_portable_smoke,
)


def test_source_consumer_process_rejects_mutation_and_keeps_earned_save():
    report = run_smoke()
    assert report["result"] == "passed-on-current-host"
    assert report["invalid_mutation_rejected"]
    assert not report["portable_zipapp_verified"]
    assert report["actions"] > 20
    assert report["portable_export_verified"]
    assert not report["windows_device_certified"]


def test_real_zipapp_play_quit_restart_victory_and_export():
    report = run_portable_smoke()
    assert report["result"] == "passed-on-current-host"
    assert report["portable_zipapp_verified"]
    assert report["source_checkout_dependency"] is False
    assert report["archive_files"] > 20
    assert len(report["archive_sha256"]) == 64
    assert report["actions"] > 20
    assert report["chapters"] == 2
    assert report["invalid_mutation_rejected"]
    assert report["portable_export_verified"]
    assert not report["windows_device_certified"]
    assert not report["installer_certified"]
    assert not report["release_certified"]
