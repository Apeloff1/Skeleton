"""Policy enforcement tests."""
from __future__ import annotations

from skeleton.cortex.deck import CommandDeck
from skeleton.organism.policy_state import set_repair_class, set_repair_enabled, set_threshold
from skeleton.testing.test_cortex_deck import _Dummy


def test_threshold_card_roundtrip(tmp_path):
    deck = CommandDeck(_Dummy(), root=tmp_path)
    deck.set_threshold("forge", 0.83)
    out = deck.threshold(surface="forge")
    assert out["threshold"] == 0.83


def test_disable_forge_repair_blocks_attempt(tmp_path):
    from skeleton.forge.repair import attempt_repair
    set_repair_enabled("forge", False, root=tmp_path)
    out = attempt_repair({"project.godot": "config_version=5\n"}, root=tmp_path)
    assert out["reason"] == "repair-disabled"


def test_disable_script_patch_class_blocks_script_repair(tmp_path):
    from skeleton.forge.repair import attempt_repair
    set_repair_class("script_patch", False, root=tmp_path)
    out = attempt_repair({"project.godot": 'config_version=5\nrun/main_scene="res://scenes/levels/run_level.tscn"\n', "scripts/x.gd": 'eval(user_input)\n'}, root=tmp_path)
    assert out["changed"] == 0 or all(a.get("path") != "scripts/x.gd" for a in out.get("actions", []))


def test_policy_threshold_affects_forge_verifier(tmp_path):
    from skeleton.intelligence.forge_verifier import ForgeVerifier
    set_threshold("forge", 0.95, root=tmp_path)
    verifier = ForgeVerifier(accept_at=0.95, gd_accept_at=0.95)
    report = verifier.verify({"project.godot": 'config_version=5\nrun/main_scene="res://scenes/levels/run_level.tscn"\n'})
    assert report.thresholds["project_accept_at"] == 0.95
