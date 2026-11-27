"""Control-flow fixtures cannot qualify native input; real-engine tests do."""
from __future__ import annotations

from pathlib import Path
import os
from types import SimpleNamespace

import pytest

from skeleton.forge import game_builder as builder
from skeleton.forge import playtest as native
from skeleton.forge.genre_project import execute_core_loop, proof_line


@pytest.fixture
def source():
    result = builder.build_playable_game("A small top-down shooter. Theme: frost.", playtest_mode="off")
    assert result["ok"]
    return result


def verified_boot(monkeypatch, source, seen):
    def boot(files, **options):
        seen.append(options["deadline"])
        marker = execute_core_loop(source["content"], source["spec"]["genre"])
        return {"status": "passed", "passed": True, "binary": "/explicit-fixture/godot",
                "errors": [], "steps": [{"log_tail": proof_line(source["spec"]["genre"], marker)}]}
    monkeypatch.setattr(builder, "playtest", boot)


@pytest.mark.parametrize("status,passed", [("failed", False), ("unavailable", False),
    ("not_applicable", False), ("passed", False), ("passed", 1), (None, False)])
def test_required_input_quality_rejects_every_non_pass_even_without_failure_text(monkeypatch, source, status, passed):
    seen = []
    verified_boot(monkeypatch, source, seen)
    monkeypatch.setattr("skeleton.forge.quality_gate.interactive_playtest",
        lambda *args, **kwargs: {"status": status, "passed": passed, "failures": []})
    result = builder.prove_and_repair(source["files"], source["spec"], source["content"],
                                      playtest_mode="require", max_rounds=1, deadline_s=5)
    assert result["ok"] is False
    assert result["playtest"]["status"] == "failed"
    assert result["playtest"]["boot_verified"] is True
    assert result["playtest"]["quality"]["passed"] == passed
    assert len(seen) == 1


@pytest.mark.parametrize("status", ["unavailable", "not_applicable"])
def test_auto_preserves_source_with_explicit_degraded_quality_and_shared_deadline(monkeypatch, source, status):
    seen = []
    verified_boot(monkeypatch, source, seen)
    def quality(*args, **options):
        seen.append(options["deadline"])
        return {"status": status, "passed": False, "failures": []}
    monkeypatch.setattr("skeleton.forge.quality_gate.interactive_playtest", quality)
    result = builder.prove_and_repair(source["files"], source["spec"], source["content"],
                                      playtest_mode="auto", max_rounds=1, deadline_s=5)
    assert result["ok"] is True
    assert result["playtest"]["degraded"] is True
    assert result["playtest"]["quality"]["passed"] is False
    assert seen[0] == seen[1] and seen[0] is not None


@pytest.mark.parametrize("mode", ["auto", "require"])
def test_no_godot_never_calls_input_gate_or_claims_boot(monkeypatch, source, mode):
    monkeypatch.setattr(builder, "playtest", lambda *args, **kwargs:
        {"status": "unavailable", "passed": False, "binary": None, "errors": [],
         "reason": "missing-godot-binary", "steps": []})
    def forbidden(*args, **kwargs):
        raise AssertionError("a missing boot cannot establish native input quality")
    monkeypatch.setattr("skeleton.forge.quality_gate.interactive_playtest", forbidden)
    result = builder.build_playable_game(source["spec"]["brief"], playtest_mode=mode, max_rounds=1)
    assert result["ok"] is (mode == "auto")
    assert result["interactive"]["native_boot_verified"] is False
    assert result["interactive"]["input_journey_verified"] is False


def test_native_child_environment_is_private_and_does_not_mutate_global_environment(monkeypatch, tmp_path):
    previous = os.environ.get("XDG_DATA_HOME")
    home = os.environ.get("HOME")
    observed = []
    def run(command, **options):
        data = Path(options["env"]["XDG_DATA_HOME"])
        assert data.is_dir() and data != tmp_path
        assert options["env"].get("HOME") == home
        assert options["env"]["SKELETON_FORGE_NATIVE_PROOF"] == "1"
        observed.append(data)
        return SimpleNamespace(returncode=0, stdout="fixture subprocess only", stderr="")
    monkeypatch.setattr(native.subprocess, "run", run)
    assert native._run(["explicit-fixture"], tmp_path, 5)[0] == 0
    assert observed and not observed[0].exists()
    assert os.environ.get("XDG_DATA_HOME") == previous


def test_unsupported_userdata_isolation_cannot_claim_a_native_boot(monkeypatch):
    monkeypatch.setattr(native, "resolve_binary", lambda *args: ("/fixture/godot", "fixture", False))
    monkeypatch.setattr(native, "_native_userdata_supported", lambda: False)
    report = native.playtest({"project.godot": "config_version=5\n"})
    assert report["status"] == "unavailable" and report["passed"] is False
    assert report["reason"] == "native-userdata-isolation-unavailable"
