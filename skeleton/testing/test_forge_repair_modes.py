"""Forge repair modes: apply-by-default revise-until-green + opt-in suggest.

Pins the 2026-09-27 restoration: ``attempt_repair`` applies bounded,
policy-gated repairs by default (script patch, project closure, canonical
scaffold restoration); ``mode="suggest"`` keeps #2006's propose-only
contract as an explicit opt-in.
"""

from __future__ import annotations

import json
import re

import pytest

from skeleton.forge.eras import compile_era
from skeleton.forge.gdscript_check import check_files
from skeleton.forge.repair import REPAIR_MODES, attempt_repair
from skeleton.forge.verify_loop import forge_verify_until_green
from skeleton.kernel.errors import MaterialisationError
from skeleton.kernel.events import EventBus
from skeleton.organism.quality_state import latest_repair

MINIMAL = {
    "project.godot": 'config_version=5\nrun/main_scene="res://scenes/levels/run_level.tscn"\n',
    "scenes/levels/run_level.tscn": '[gd_scene load_steps=1 format=3]\n[node name="RunLevel" type="Node2D"]\n',
    "scripts/world/world_map.gd": "var x = 1\n",
}


def _plan(actions):
    return [(a["path"], a["action"]) for a in actions]


class TestSuggestMode:
    def test_suggest_plans_but_never_mutates(self, tmp_path):
        out = attempt_repair(
            MINIMAL, request="world map", root=tmp_path, mode="suggest"
        )
        assert out["mode"] == "suggest"
        assert out["changed"] == 0
        assert out["files"] == MINIMAL
        assert out["actions"] and all(a["applied"] == 0 for a in out["actions"])
        assert "scripts/world/world_map.gd" in out["proposed_paths"]
        assert out["before"] == out["after"]
        assert out["ok"] == 0

    def test_suggest_and_apply_plan_identical_actions(self, tmp_path):
        suggested = attempt_repair(
            MINIMAL, request="world map", root=tmp_path, mode="suggest"
        )
        applied = attempt_repair(MINIMAL, request="world map", root=tmp_path)
        assert applied["mode"] == "apply"
        assert _plan(suggested["actions"]) == _plan(applied["actions"])
        assert all(a["applied"] == 1 for a in applied["actions"])
        assert sorted(suggested["proposed_paths"]) == sorted(applied["changed_paths"])

    def test_suggest_is_persisted_as_repair_record(self, tmp_path):
        attempt_repair(MINIMAL, request="world map", root=tmp_path, mode="suggest")
        row = latest_repair(root=tmp_path, surface="forge")
        assert row["kind"] == "repair"
        assert row["metadata"]["mode"] == "suggest"
        assert "files" not in row

    def test_unknown_mode_rejected(self, tmp_path):
        assert REPAIR_MODES == ("apply", "suggest")
        with pytest.raises(ValueError):
            attempt_repair(MINIMAL, request="x", root=tmp_path, mode="yolo")

    def test_accepted_project_needs_no_actions_in_either_mode(self, tmp_path):
        from skeleton.forge.godot_emit import emit_godot

        files = emit_godot(compile_era("extraction_now"), title="Clean")
        for mode in REPAIR_MODES:
            out = attempt_repair(files, request="clean", root=tmp_path, mode=mode)
            assert out["ok"] == 1
            assert out["actions"] == []
            assert out["files"] == files


class TestApplyMode:
    def test_minimal_project_is_closed_in_one_pass(self, tmp_path):
        out = attempt_repair(MINIMAL, request="world map", root=tmp_path)
        assert out["ok"] == 1, out["after"]["blocking_issues"]
        assert check_files(out["files"]) == []

    def test_autoloads_registered_inside_autoload_section(self, tmp_path):
        project = attempt_repair(MINIMAL, request="x", root=tmp_path)["files"][
            "project.godot"
        ]
        section = project.split("[autoload]", 1)[1]
        for name in ("EventBus", "HeatSystem", "GameState", "InputBind", "Jeeves"):
            assert re.search(rf'^{name}="\*res://scripts/autoloads/', section, re.M), (
                name
            )
        assert project.count("[autoload]") == 1

    def test_ext_resources_precede_first_node(self, tmp_path):
        level = attempt_repair(MINIMAL, request="x", root=tmp_path)["files"][
            "scenes/levels/run_level.tscn"
        ]
        lines = level.splitlines()
        first_node = next(i for i, line in enumerate(lines) if line.startswith("[node"))
        ext = [i for i, line in enumerate(lines) if line.startswith("[ext_resource")]
        assert ext and max(ext) < first_node

    def test_unsafe_call_neutralised_without_emptying_block(self, tmp_path):
        files = dict(MINIMAL)
        files["scripts/world/world_map.gd"] = (
            "extends Node\nfunc tick(room):\n    eval(room)\n"
        )
        out = attempt_repair(files, request="world map room", root=tmp_path)
        src = out["files"]["scripts/world/world_map.gd"]
        assert "# eval(room)" in src
        assert "    pass  # forge-repair" in src
        assert out["after"]["reason"] != "unsafe_code"

    def test_existing_author_content_is_preserved(self, tmp_path):
        out = attempt_repair(MINIMAL, request="world map", root=tmp_path)
        assert "var x = 1" in out["files"]["scripts/world/world_map.gd"]

    def test_pack_seeds_canonical_scaffold_era(self, tmp_path):
        out = attempt_repair(
            MINIMAL, request="x", root=tmp_path, pack=compile_era("soulslike")
        )
        rooms = json.loads(out["files"]["data/rooms.json"])
        assert rooms["era"] == "soulslike"


class TestLoopAndMaterialise:
    def test_loop_suggest_mode_reports_without_repairing(self, tmp_path):
        out = forge_verify_until_green(
            MINIMAL,
            request="world map",
            root=tmp_path,
            max_rounds=3,
            repair_mode="suggest",
        )
        assert out["accepted"] is False
        assert out["repair_mode"] == "suggest"
        assert out["files"] == MINIMAL
        assert out["repairs"] and all(r["changed"] == 0 for r in out["repairs"])

    def test_loop_apply_mode_goes_green(self, tmp_path):
        out = forge_verify_until_green(
            MINIMAL, request="world map", root=tmp_path, max_rounds=3
        )
        assert out["accepted"] is True
        assert out["repair_mode"] == "apply"

    def test_loop_rejects_unknown_mode(self, tmp_path):
        with pytest.raises(ValueError):
            forge_verify_until_green(
                MINIMAL, request="x", root=tmp_path, repair_mode="maybe"
            )

    def _weak_forge(self, tmp_path, monkeypatch):
        from skeleton.forge.universal import Forge

        forge = Forge(root=tmp_path)
        bp = forge.new_blueprint("Weak")
        forge.instantiate(bp, "player", "player")
        monkeypatch.setattr(
            "skeleton.forge.godot_emit.emit_godot", lambda *a, **k: dict(MINIMAL)
        )
        return forge, bp

    def test_materialise_suggest_fails_closed(self, tmp_path, monkeypatch):
        forge, bp = self._weak_forge(tmp_path, monkeypatch)
        with pytest.raises(MaterialisationError):
            forge.materialise(bp, target="godot", repair=True, repair_mode="suggest")

    def test_materialise_apply_is_default_and_green(self, tmp_path, monkeypatch):
        forge, bp = self._weak_forge(tmp_path, monkeypatch)
        out = forge.materialise(bp, target="godot", repair=True)
        assert out["verification"]["accepted"] is True
        assert out["verify_loop"]["repair_mode"] == "apply"
        assert out["repair"]["changed"] == 1


class TestEventBusUnsubscribe:
    def test_subscribe_returns_idempotent_unsubscribe(self):
        bus = EventBus()
        seen = []
        unsub = bus.subscribe("a.b", lambda e: seen.append(e.topic), name="probe")
        assert bus.subscriptions()["a.b"] == ["probe"]
        bus.emit("a.b", {})
        unsub()
        unsub()
        bus.emit("a.b", {})
        assert seen == ["a.b"]
        assert "a.b" not in bus.subscriptions()

    def test_unsubscribe_during_dispatch_is_safe(self):
        bus = EventBus()
        seen = []
        holder = {}

        def once(event):
            seen.append("once")
            holder["unsub"]()

        holder["unsub"] = bus.subscribe("t", once)
        bus.subscribe("t", lambda e: seen.append("other"))
        bus.emit("t", {})
        bus.emit("t", {})
        assert seen == ["once", "other", "other"]


def test_missing_extends_falls_below_default_bar():
    from skeleton.intelligence.forge_verifier import ForgeVerifier

    report = ForgeVerifier(accept_at=0.7)._verify_gdscript(
        "scripts/world/door.gd", "func open():\n    return true\n"
    )
    assert report.score < 0.7
    with_extends = ForgeVerifier(accept_at=0.7)._verify_gdscript(
        "scripts/world/door.gd", "extends Area2D\nfunc open():\n    return true\n"
    )
    assert with_extends.score >= 0.7
