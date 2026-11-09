"""A missing report is not a green gate, and a target is not files produced."""

import pytest

from skeleton.forge.phase_gates import build


def _manifest():
    return {
        "awareness": {"era": "industrial", "choices_logged": 2},
        "ladder": [
            {"stage": "world", "parity_ok": True, "quality": {"all_passed": True}, "grade_floor": 1},
            {"stage": "play", "grade_floor": 2},
        ],
        "parity_locked": True,
        "plan_hash": "abc123def",
        "storage": {"used_pct": 40, "used_label": "4", "cap_label": "10"},
        "capacity": {"assets_forged": 2, "asset_capacity": 10, "utilization_pct": 20},
        "choice_gates": {"all_reflected": True},
    }


def test_string_flags_and_a_missing_choice_report_do_not_pass() -> None:
    empty = build({})
    assert empty["all_gates_green"] is False
    assert empty["phases_passed"] == 0
    assert empty["file_plan"]["files_produced"] == 0

    lied = _manifest()
    lied["ladder"][0]["parity_ok"] = "yes"
    assert build(lied, {"forged": 2})["all_gates_green"] is False

    missing_choices = _manifest()
    missing_choices.pop("choice_gates")
    result = build(missing_choices, {"forged": 2})
    assert result["bands"][-1]["passed"] is False
    assert result["file_plan"]["files_produced"] == 0

    green = build(_manifest(), {"forged": 2})
    assert green["all_gates_green"] is True
    assert green["file_plan"]["files_produced"] == 0
    with pytest.raises(ValueError):
        build(_manifest(), {"forged": True})
    with pytest.raises(ValueError):
        build(_manifest(), {"forged": 2}, file_target=-1)
