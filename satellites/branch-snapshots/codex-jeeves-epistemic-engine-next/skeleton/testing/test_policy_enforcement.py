"""Policy enforcement tests."""
from __future__ import annotations

from skeleton.organism.policy_state import set_repair_class, set_repair_enabled, set_threshold


def test_disable_forge_repair_blocks_attempt(tmp_path):
    from skeleton.forge.repair import attempt_repair
    set_repair_enabled("forge", False, root=tmp_path)
    out = attempt_repair({"project.godot": "config_version=5\n"}, root=tmp_path)
    assert out["reason"] == "repair-disabled"


def test_disable_script_patch_class_blocks_script_repair(tmp_path):
    from skeleton.forge.repair import attempt_repair
    set_repair_class("script_patch", False, root=tmp_path)
    out = attempt_repair(
        {
            "project.godot": 'config_version=5\nrun/main_scene="res://scenes/levels/run_level.tscn"\n',
            "scripts/x.gd": "eval(user_input)\n",
        },
        root=tmp_path,
    )
    assert out["changed"] == 0 or all(a.get("path") != "scripts/x.gd" for a in out.get("actions", []))


def test_policy_threshold_affects_forge_verifier(tmp_path):
    from skeleton.intelligence.forge_verifier import ForgeVerifier
    set_threshold("forge", 0.95, root=tmp_path)
    verifier = ForgeVerifier(root=tmp_path)
    assert verifier.accept_at == 0.95
    report = verifier.verify(
        {"project.godot": 'config_version=5\nrun/main_scene="res://scenes/levels/run_level.tscn"\n'}
    )
    assert report.thresholds["project_accept_at"] == 0.95


def test_code_verifier_picks_up_forge_threshold(tmp_path):
    from skeleton.intelligence.verifier import CodeVerifier
    set_threshold("forge", 0.91, root=tmp_path)
    verifier = CodeVerifier(root=tmp_path)
    assert verifier.accept_at == 0.91


def test_code_verifier_picks_up_non_forge_surface(tmp_path):
    from skeleton.intelligence.verifier import CodeVerifier
    set_threshold("plan", 0.88, root=tmp_path)
    verifier = CodeVerifier(root=tmp_path, surface="plan")
    assert verifier.accept_at == 0.88


def test_code_verifier_explicit_accept_at_overrides_policy(tmp_path):
    from skeleton.intelligence.verifier import CodeVerifier
    set_threshold("forge", 0.99, root=tmp_path)
    verifier = CodeVerifier(accept_at=0.8, root=tmp_path)
    assert verifier.accept_at == 0.8


def test_code_verifier_default_fallback_without_policy():
    from skeleton.intelligence.verifier import CodeVerifier
    verifier = CodeVerifier()
    assert verifier.accept_at == 0.7


def test_plan_verifier_picks_up_policy_threshold(tmp_path):
    from skeleton.intelligence.plan_verifier import PlanVerifier
    set_threshold("plan", 0.86, root=tmp_path)
    verifier = PlanVerifier(root=tmp_path)
    assert verifier.accept_at == 0.86


def test_disable_plan_repair_blocks_attempt(tmp_path):
    from skeleton.intelligence.plan_repair import attempt_plan_repair
    set_repair_enabled("plan", False, root=tmp_path)
    out = attempt_plan_repair({"era": "extraction_now"}, root=tmp_path)
    assert out["reason"] == "repair-disabled"
    assert out["changed"] == 0


def test_disable_npc_repair_blocks_attempt(tmp_path):
    from skeleton.intelligence.pipeline_repair import attempt_npc_repair
    set_repair_enabled("npc", False, root=tmp_path)
    out = attempt_npc_repair({"name": "scout"}, root=tmp_path)
    assert out["reason"] == "repair-disabled"
    assert out["changed"] == 0
