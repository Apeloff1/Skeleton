"""Player guidance is actually playable and survives save/replay/export."""
from __future__ import annotations

from copy import deepcopy
from io import StringIO
from pathlib import Path
import subprocess
import sys

import pytest

from skeleton.game.gameplay.harbor_crafting import (
    HarborError, canonical, decode, demo_actions, digest, export_bundle,
    initial_state, load_source, step, verify_bundle,
)
from skeleton.game.gameplay.harbor_crafting_guidance import (
    legal_action_report, legal_actions, verify_legal_action_report,
)
from skeleton.game.gameplay.harbor_crafting_ui import parse_command, play_live

WORLD = Path(__file__).resolve().parents[1] / "game" / "gameplay" / "fixtures" / "harbor_lantern_quay.json"


def world():
    return load_source(WORLD)


def test_every_hint_is_a_real_legal_transition_with_exact_delta():
    source = world()
    bundle = export_bundle(source, demo_actions()[:10])
    original = deepcopy(bundle)
    report = legal_action_report(bundle)
    assert verify_legal_action_report(decode(canonical(report))) == report["legal_actions"]
    for option in report["legal_actions"]:
        result = step(source, bundle["state"], option["action"])
        assert digest(result) == option["next_state_digest"]
        assert option["next_tick"] == result["tick"]
        assert option["next_pos"] == result["pos"]
    assert bundle == original


def test_earned_victory_choices_only_appear_after_delivery():
    source = world()
    start = export_bundle(source, [])
    before = legal_action_report(start)["legal_actions"]
    assert all(option["action"]["op"] != "choose" for option in before)
    ready = export_bundle(source, demo_actions()[:-1])
    choices = [
        option for option in legal_action_report(ready)["legal_actions"]
        if option["action"]["op"] == "choose"
    ]
    assert len(choices) == 2
    assert {option["ending"] for option in choices} == {"beacon", "safe_harbor"}
    complete = export_bundle(source, demo_actions(), require_win=True)
    assert legal_action_report(complete)["legal_actions"] == []


def test_movement_hints_never_include_wall_or_npc_collision():
    source = world()
    state = initial_state(source)
    hints = legal_actions(source, state)
    for hint in hints:
        if hint["action"]["op"] == "move":
            assert hint["next_pos"] != state["npc_pos"]
            assert source["map"][hint["next_pos"][1]][hint["next_pos"][0]] == "."


def test_exhausted_tick_budget_returns_no_fictitious_hint():
    source = world()
    source["max_ticks"] = 1
    bundle = export_bundle(source, [{"op": "wait"}])
    assert legal_action_report(bundle)["legal_actions"] == []


@pytest.mark.parametrize("mutation", [
    lambda r: r["legal_actions"][0].update({"next_state_digest": "0" * 64}),
    lambda r: r["legal_actions"].append({"action": {"op": "teleport"}}),
    lambda r: r.update({"terminal_digest": "0" * 64}),
    lambda r: r["bundle"]["state"].update({"coins": 999}),
])
def test_forged_guidance_rejected_even_with_resealed_report(mutation):
    report = legal_action_report(export_bundle(world(), []))
    mutation(report)
    report["report_digest"] = digest({
        k: v for k, v in report.items() if k != "report_digest"
    })
    with pytest.raises(HarborError):
        verify_legal_action_report(report)


def test_terminal_hint_command_is_user_reachable_and_nonmutating():
    assert parse_command("hint") == "hint"
    output = StringIO()
    code = play_live(world(), StringIO("hint\nquit\n"), output)
    assert code == 2
    text = output.getvalue()
    assert "LEGAL NOW" in text
    assert "CHECKPOINT " in text
    assert '"tick":0' in text


def test_cli_hint_export_and_replay_verification(tmp_path):
    bundle = export_bundle(world(), demo_actions()[:-1])
    path = tmp_path / "save.json"
    path.write_bytes(canonical(bundle))
    command = [sys.executable, "-m", "scripts.game.harbor_crafting"]
    produced = subprocess.run(
        command + ["legal-actions", "--bundle", str(path)],
        capture_output=True, check=False,
    )
    assert produced.returncode == 0, produced.stderr.decode()
    report = decode(produced.stdout)
    assert len(report["legal_actions"]) >= 2
    report_file = tmp_path / "guidance.json"
    report_file.write_bytes(produced.stdout)
    checked = subprocess.run(
        command + ["verify-legal-actions", "--report", str(report_file)],
        capture_output=True, check=False,
    )
    assert checked.returncode == 0, checked.stderr.decode()
    assert decode(checked.stdout)["verified"] is True
