"""Mission-board end-to-end production, anti-forgery and consequence acceptance."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from skeleton.game.gameplay.harbor_crafting import (
    HarborError, canonical, decode, demo_actions, digest, export_bundle, load_source,
)
from skeleton.game.gameplay.harbor_crafting_missions import (
    mission_report, solve_missions, validate_board, verify_mission_report,
)

ROOT = Path(__file__).resolve().parents[1] / "game" / "gameplay" / "fixtures"


def source():
    return load_source(ROOT / "harbor_lantern_quay.json")


def board():
    return decode((ROOT / "harbor_lantern_quay_missions.json").read_bytes())


def completed():
    return mission_report(export_bundle(source(), demo_actions(), require_win=True), board(), require_all=True)


def test_full_source_to_runtime_quest_progress_to_save_export_to_replay():
    result = completed()
    assert result["completed"] == ["salvage", "workshop", "dispatch"]
    assert result["points"] == 60
    assert len(result["journal"]) == len(demo_actions())
    assert result["journal"][-1]["completed"] == result["completed"]
    assert verify_mission_report(decode(canonical(result)), require_all=True) == {
        "completed": ["salvage", "workshop", "dispatch"], "points": 60,
    }
    assert canonical(completed()) == canonical(result)


def test_mission_completion_requires_actual_prerequisites_and_order():
    actions = demo_actions()
    early = mission_report(export_bundle(source(), actions[:11]), board())
    assert early["completed"] == ["salvage"]
    assert early["points"] == 10
    assert early["journal"][-1]["progress"]["workshop"] == [1, 0]
    with pytest.raises(HarborError, match="not fully earned"):
        mission_report(export_bundle(source(), actions[:11]), board(), require_all=True)


def test_alternate_ending_cannot_claim_signal_mission():
    actions = demo_actions()
    actions[-1] = {"op": "choose", "choice": "shelter"}
    report = mission_report(export_bundle(source(), actions, require_win=True), board())
    assert report["completed"] == ["salvage", "workshop"]
    assert report["points"] == 30
    assert verify_mission_report(report)["points"] == 30
    with pytest.raises(HarborError, match="not fully earned"):
        verify_mission_report(report, require_all=True)


def test_solver_produces_real_victory_with_all_missions_or_fails_closed():
    report = solve_missions(source(), board())
    assert report["bundle"]["state"]["ending"] == "beacon"
    assert verify_mission_report(report, require_all=True)["points"] == 60
    with pytest.raises(HarborError, match="not fully earned"):
        solve_missions(source(), board(), choice="shelter")


@pytest.mark.parametrize("change", [
    lambda b: b["missions"][0].update({"id": "dispatch"}),
    lambda b: b["missions"][1].update({"requires": ["dispatch"]}),
    lambda b: b["missions"][0]["objectives"][0].update({"count": True}),
    lambda b: b["missions"][0]["objectives"][0].update({"item": "phantom"}),
    lambda b: b["missions"][2]["objectives"][1].update({"choice": "root"}),
    lambda b: b["missions"][0]["objectives"].append({"kind": "visit", "at": [0, 0]}),
    lambda b: b["missions"][0].update({"deadline": 0}),
    lambda b: b.update({"source_id": "other-world"}),
])
def test_bad_authored_boards_rejected(change):
    authored = board()
    change(authored)
    with pytest.raises(HarborError):
        validate_board(authored, source())


@pytest.mark.parametrize("change", [
    lambda r: r["journal"][0].update({"points": 999}),
    lambda r: r["journal"][-1]["completed"].append("forged"),
    lambda r: r["completed"].append("forged"),
    lambda r: r.update({"points": 999}),
    lambda r: r["journal"][2]["progress"]["salvage"].__setitem__(0, 2),
    lambda r: r["board"]["missions"][0].update({"points": 100}),
    lambda r: r["bundle"]["events"][0]["action"].update({"direction": "west"}),
    lambda r: r.update({"source_digest": "f" * 64}),
])
def test_resealed_report_forgery_fails_full_source_bound_replay(change):
    report = completed()
    change(report)
    report["board_digest"] = digest(report["board"])
    report["report_digest"] = digest({k: v for k, v in report.items() if k != "report_digest"})
    with pytest.raises(HarborError):
        verify_mission_report(report)


def test_empty_history_has_no_unearned_mission_rewards():
    result = mission_report(export_bundle(source(), []), board())
    assert result["journal"] == []
    assert result["completed"] == []
    assert result["points"] == 0


def test_mission_engine_does_not_mutate_inputs():
    bundle = export_bundle(source(), demo_actions())
    authored = board()
    old_bundle, old_board = deepcopy(bundle), deepcopy(authored)
    mission_report(bundle, authored, require_all=True)
    assert bundle == old_bundle
    assert authored == old_board


def test_mission_board_enforces_global_objective_budget():
    authored = board()
    authored["missions"] = [
        {"id": f"mission_{i}", "requires": [], "points": 1, "deadline": 256,
         "objectives": [{"kind": "deliver"} for _ in range(12)]}
        for i in range(6)
    ]
    with pytest.raises(HarborError, match="budget"):
        validate_board(authored, source())


def test_solver_gathers_quest_stock_before_crafting_and_uses_real_transitions():
    result = solve_missions(source(), board())
    actions = [event["action"] for event in result["bundle"]["events"]]
    wood_gathers = [
        index for index, event in enumerate(result["bundle"]["events"])
        if event["action"]["op"] == "gather"
        and event["after"] != event["before"]
    ]
    first_craft = next(i for i, action in enumerate(actions) if action["op"] == "craft")
    assert len(wood_gathers) >= 3
    assert first_craft > 2
    assert result["bundle"]["state"]["delivered"]
    assert result["journal"][-1]["points"] == 60


def test_solver_rejects_unobtainable_repeat_objective_instead_of_claiming_win():
    authored = board()
    authored["missions"][0]["objectives"][0]["count"] = 3
    with pytest.raises(HarborError):
        solve_missions(source(), authored)


def test_malformed_prerequisite_types_fail_closed_with_domain_error():
    authored = board()
    authored["missions"][1]["requires"] = [["salvage"]]
    with pytest.raises(HarborError, match="prerequisite"):
        validate_board(authored, source())
