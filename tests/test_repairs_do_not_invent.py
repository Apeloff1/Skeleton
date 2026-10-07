"""A repair names the hole. It does not fill the hole and call that a pass."""

from skeleton.intelligence.learned_repair import learn_from_repair
from skeleton.intelligence.pipeline_repair import attempt_npc_repair
from skeleton.intelligence.plan_repair import attempt_plan_repair
from skeleton.intelligence.repair_telemetry import capture_telemetry


def test_npc_and_plan_repairs_do_not_rewrite_the_input() -> None:
    spec = {"persona": {}}
    repaired = attempt_npc_repair(spec, description="")
    assert repaired["ok"] == 0
    assert repaired["changed"] == 0
    assert repaired["spec"] == spec
    assert "npc_repaired" not in str(repaired["spec"])
    assert all(action["applied"] == 0 for action in repaired["actions"])

    plan = {}
    repaired_plan = attempt_plan_repair(plan, vision="")
    assert repaired_plan["ok"] == 0
    assert repaired_plan["plan"] == plan
    assert "extraction_now" not in str(repaired_plan["plan"])


def test_a_string_yes_is_not_learned_as_success(tmp_path) -> None:
    policy = learn_from_repair({"surface": "forge", "reason": "low_score", "ok": "false", "actions": []}, root=tmp_path)
    row = policy["surface_strategies"]["forge:low_score"]
    assert row["attempts"] == 1
    assert row["successes"] == 0
    telemetry = capture_telemetry(
        "forge",
        1,
        0,
        {"ok": "false", "before": {"score": 0.2}, "after": {"score": 0.9}, "reason": "no"},
        root=tmp_path,
    )
    assert telemetry.accepted is False
