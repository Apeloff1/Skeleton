"""Runnable Godot 4 full playthrough: source-bound route and engine evidence."""

from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys

import pytest

from skeleton.jeeves.game_frontier_expedition import (
    ExpeditionError, Traveler,
)
from skeleton.jeeves.game_frontier_expedition_godot import (
    emit_expedition_godot_project, make_expedition_autoplay,
    verify_expedition_godot_project,
)
from skeleton.jeeves.game_frontier_expedition_native_runner import (
    COMPLETE_PREFIX, run_headless_expedition,
)
from tests.test_game_frontier_expedition import world
from tests.test_game_frontier_expedition_native_verify import (
    player, sample_records, as_stdout,
)


def test_native_autoplay_compiles_real_route_and_player_bound_source():
    w,p=world(),player()
    recipe=make_expedition_autoplay(w,p)
    assert recipe["schema"]=="skeleton.game.expedition_autoplay.v1"
    assert recipe["source_digest"]==w.source_digest
    assert recipe["world_digest"]==w.digest
    assert recipe["steps"]
    assert recipe["steps"][-1]["target"]=="exit"
    assert len(recipe["receipt_digest"])==64
    assert recipe==make_expedition_autoplay(world(),player())


def test_native_project_includes_autoplay_only_on_explicit_request():
    w,p=world(),player()
    normal=emit_expedition_godot_project(w,p)
    assert "game/frontier/autoplay.json" not in normal
    files=emit_expedition_godot_project(w,p,include_autoplay=True)
    assert len(files)==len(normal)+1
    payload=json.loads(files["game/frontier/autoplay.json"])
    assert payload["route_digest"]==make_expedition_autoplay(w,p)["route_digest"]
    proof=verify_expedition_godot_project(
        files,w,p,include_autoplay=True,
    )
    assert proof["asset_count"]==len(files)
    with pytest.raises(ExpeditionError,match="differs"):
        verify_expedition_godot_project(files,w,p)


def test_unreachable_autoplay_cannot_fabricate_game_completion():
    w=world()
    p=Traveler(permitted_modes=frozenset(("walk",)))
    with pytest.raises(ExpeditionError,match="no traversable route"):
        make_expedition_autoplay(w,p)


def test_driver_fails_closed_for_absent_binary_and_invalid_timeout():
    w,p=world(),player()
    with pytest.raises(ExpeditionError,match="timeout"):
        run_headless_expedition(w,p,timeout_seconds=301)
    with pytest.raises(ExpeditionError,match="does not exist"):
        run_headless_expedition(w,p,godot_executable="/nonexistent/godot4")


def test_driver_requires_godot4_version_before_any_game_source_run(monkeypatch):
    w,p=world(),player()
    def old_engine(argv,**kwargs):
        assert argv[-1]=="--version"
        return subprocess.CompletedProcess(argv,0,stdout="3.5.2.stable\n")
    monkeypatch.setattr(
        "skeleton.jeeves.game_frontier_expedition_native_runner.subprocess.run",
        old_engine,
    )
    with pytest.raises(ExpeditionError,match="Godot 4"):
        run_headless_expedition(w,p,godot_executable=sys.executable)


def test_driver_rejects_fake_native_completion_and_unknown_exit(monkeypatch):
    w,p=world(),player()
    def bogus(argv,**kwargs):
        if argv[-1]=="--version":
            return subprocess.CompletedProcess(argv,0,stdout="4.4.1.stable\n")
        kwargs["stdout"].write(b"EXPEDITION_READY but no game transcript\n")
        return subprocess.CompletedProcess(argv,0)
    monkeypatch.setattr(
        "skeleton.jeeves.game_frontier_expedition_native_runner.subprocess.run",
        bogus,
    )
    with pytest.raises(ExpeditionError,match="never emitted"):
        run_headless_expedition(w,p,godot_executable=sys.executable)


def test_mock_process_transcript_is_replayed_but_not_a_real_engine_proof(monkeypatch):
    """Fixture verifies process adapter validation, NOT actual Godot execution."""
    w,p,records=sample_records()
    recipe=make_expedition_autoplay(w,p)
    transcript=as_stdout(records)+COMPLETE_PREFIX+json.dumps({
        "world_digest":w.digest,
        "route_digest":recipe["route_digest"],
        "completed":True,
        "steps":len(recipe["steps"]),
        "candidate_receipt_head":records[-1]["receipt_head"],
    })+"\n"
    def host_run(argv,**kwargs):
        if argv[-1]=="--version":
            return subprocess.CompletedProcess(argv,0,stdout="4.4.1.stable\n")
        kwargs["stdout"].write(transcript.encode())
        return subprocess.CompletedProcess(argv,0)
    monkeypatch.setattr(
        "skeleton.jeeves.game_frontier_expedition_native_runner.subprocess.run",
        host_run,
    )
    report=run_headless_expedition(w,p,godot_executable=sys.executable)
    assert report["completed"]
    assert report["native_gameplay_consistent"]
    assert report["authored_route_steps"]==len(recipe["steps"])
    assert not report["native_origin_independently_signed"]
    assert len(report["native_executable_sha256"])==64


def test_game_runner_executes_actual_installed_godot_when_available():
    path=shutil.which("godot4") or shutil.which("godot")
    if path is None:
        pytest.skip("Godot 4 not installed: engine run must not be simulated")
    version=subprocess.run(
        [path,"--version"],capture_output=True,text=True,timeout=20,check=False,
    )
    if not version.stdout.startswith("4."):
        pytest.skip("Installed executable is not Godot 4")
    proof=run_headless_expedition(
        world(),player(),godot_executable=path,timeout_seconds=90,
    )
    assert proof["native_process_executed"]
    assert proof["native_gameplay_consistent"]
    assert proof["completed"]
    assert not proof["native_origin_independently_signed"]
    assert len(proof["observed_replay_receipt"])==64
