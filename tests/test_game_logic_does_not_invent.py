"""A repair does not turn a broken economy into a passing one."""

from skeleton.intelligence.game_logic_repair import attempt_game_logic_repair
from skeleton.intelligence.pipeline_verifier import PipelineVerifier


def _spec(**changes):
    spec = {
        "combat": {"damage_formula": "atk - def", "base_values": {"atk": 5}},
        "economy": {"currency": "credits", "starting_balance": 10},
        "progression": {"curve": "quadratic", "max_level": 20},
    }
    spec.update(changes)
    return spec


def test_a_negative_balance_stays_negative_and_is_not_accepted() -> None:
    spec = _spec(economy={"currency": "credits", "starting_balance": -50})
    verdict = PipelineVerifier(accept_at=0.7).verify_game_logic(spec, description="credits quadratic")
    assert verdict.accepted is False
    assert any(issue.startswith("hard:") for issue in verdict.issues)
    repaired = attempt_game_logic_repair(spec, description="credits quadratic")
    assert repaired["ok"] == 0
    assert repaired["changed"] == 0
    assert repaired["spec"]["economy"]["starting_balance"] == -50
    assert all(action["applied"] == 0 for action in repaired["actions"])


def test_a_complete_spec_can_pass_without_being_rewritten() -> None:
    spec = _spec()
    verdict = PipelineVerifier(accept_at=0.7).verify_game_logic(spec, description="credits quadratic")
    assert verdict.accepted is True
    repaired = attempt_game_logic_repair(spec, description="credits quadratic")
    assert repaired["ok"] == 1
    assert repaired["spec"] == spec
