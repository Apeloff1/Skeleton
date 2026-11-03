"""Transactional editor source custody, replay and actual game preview."""
from copy import deepcopy
import json
from pathlib import Path
import pytest

from skeleton.game.gameplay.ridge_rescue.custody import digest
from skeleton.game.gameplay.ridge_rescue.workbench import (
    WorkbenchError, open_workbench, verify_workbench, edit_workbench,
    undo_workbench, export_workbench, verify_workbench_export, preview_workbench,
)
from skeleton.game.gameplay.ridge_rescue.acceptance import acceptance_actions

SOURCE = Path(__file__).resolve().parents[1] / "game/gameplay/ridge_rescue/cinder_ridge_acceptance.json"


def opened():
    return open_workbench(SOURCE.read_bytes())


def test_edit_replay_undo_and_export():
    start = opened()
    op = {"kind": "rename", "target": "world", "value": "Cinder Ridge Field Editor"}
    changed = edit_workbench(start, op, expected_head=start["head"])
    assert changed["world"]["name"] == "Cinder Ridge Field Editor"
    assert start["world"]["name"] != changed["world"]["name"]
    assert verify_workbench(changed)["revision_sha256"] == digest(changed["world"])
    assert verify_workbench_export(export_workbench(changed))["head"] == changed["head"]
    undone = undo_workbench(changed, expected_head=changed["head"])
    assert undone["world"] == start["world"]
    assert undone["operations"] == []


def test_real_edited_world_still_plays_earned_ending():
    start = opened()
    changed = edit_workbench(start, {"kind": "set-turn-budget", "target": "world", "value": 40},
                             expected_head=start["head"])
    preview = preview_workbench(changed, acceptance_actions("protect"))
    assert preview["status"] == "won:protect"
    assert preview["bundle"]["payload"]["state"]["flags"]["beacon"] is True
    assert preview["revision_sha256"] == changed["revision_sha256"]


def test_collision_and_unreachable_edits_refused():
    start = opened()
    with pytest.raises(WorkbenchError):
        edit_workbench(start, {"kind": "set-tile", "target": [0, 0], "value": "#"},
                       expected_head=start["head"])
    with pytest.raises(WorkbenchError):
        edit_workbench(start, {"kind": "move-civilian", "target": "tavi", "value": [0, 0]},
                       expected_head=start["head"])
    with pytest.raises(WorkbenchError):
        edit_workbench(start, {"kind": "set-turn-budget", "target": "world", "value": True},
                       expected_head=start["head"])


def test_stale_cas_and_tampered_history_refused():
    start = opened()
    with pytest.raises(WorkbenchError, match="stale"):
        edit_workbench(start, {"kind": "rename", "target": "world", "value": "X"},
                       expected_head="0" * 64)
    changed = edit_workbench(start, {"kind": "rename", "target": "world", "value": "Y"},
                             expected_head=start["head"])
    bad = deepcopy(changed)
    bad["operations"][0]["value"] = "X"
    bad["head"] = digest({k: v for k, v in bad.items() if k != "head"})
    with pytest.raises(WorkbenchError):
        verify_workbench(bad)


def test_rejects_forged_export_even_with_new_outer_digest():
    bundle = export_workbench(opened())
    bundle["payload"]["world"]["name"] = "Injected"
    bundle["sha256"] = digest(bundle["payload"])
    with pytest.raises(WorkbenchError):
        verify_workbench_export(bundle)


def test_preview_rejects_unearned_protect_ending():
    with pytest.raises(WorkbenchError):
        preview_workbench(opened(), [{"verb": "evacuate", "choice": "protect"}])
