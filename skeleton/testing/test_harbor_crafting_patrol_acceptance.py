"""First-playable acceptance: authored source -> runtime -> save -> package -> consequence."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from skeleton.game.gameplay.harbor_crafting import HarborError, digest
from skeleton.game.gameplay.harbor_crafting_patrol import (
    build_patrol, resume_patrol, verify_patrol,
)
from skeleton.game.gameplay.harbor_crafting_patrol_authoring import (
    edit_patrol_board, verify_patrol_revision,
)
from skeleton.game.gameplay.harbor_crafting_patrol_debrief import (
    build_patrol_debrief, verify_patrol_debrief,
)
from skeleton.game.gameplay.harbor_crafting_patrol_guidance import patrol_hints
from skeleton.game.gameplay.harbor_crafting_patrol_package import (
    build_patrol_package, play_patrol_package, verify_patrol_package,
    verify_patrol_package_play,
)

FIXTURES = Path(__file__).resolve().parents[1] / "game" / "gameplay" / "fixtures"


def fixture(name):
    return json.loads((FIXTURES / name).read_text())


def test_complete_authored_game_and_both_consequences():
    source = fixture("harbor_lantern_quay.json")
    board = fixture("harbor_lantern_quay_patrol.json")
    actions = fixture("harbor_lantern_quay_patrol_demo.json")
    debrief_board = fixture("harbor_lantern_quay_patrol_debrief.json")
    prefix = build_patrol(source, board, actions[:8])
    assert patrol_hints(prefix)["terminal"] is False
    full = resume_patrol(prefix, actions[8:],
                         expected_digest=prefix["report_digest"], require_complete=True)
    assert full == build_patrol(source, board, actions, require_complete=True)
    assert verify_patrol(full, require_complete=True)["score"] == 18
    assert full["bundle"]["state"]["ending"] == "beacon"
    package = build_patrol_package(source, board, actions, package_id="lantern_patrol")
    assert verify_patrol_package(package)["demo_score"] == 18
    play = play_patrol_package(package, actions, require_complete=True)
    assert verify_patrol_package_play(play, require_complete=True)["complete"]
    for name, epilogue in (("publish", "watch_restored"),
                           ("protect", "families_sheltered")):
        report = build_patrol_debrief(full, debrief_board, name)
        assert verify_patrol_debrief(report)["epilogue"] == epilogue


def test_editor_changes_are_replayed_and_old_source_is_immutable():
    source = fixture("harbor_lantern_quay.json")
    board = fixture("harbor_lantern_quay_patrol.json")
    actions = fixture("harbor_lantern_quay_patrol_demo.json")
    revision = edit_patrol_board(
        source, board, [{"op": "set-objective-reward", "id": "dock_manifest",
                         "value": 17}],
        expected_digest=digest(board), preview_actions=actions,
    )
    edited = verify_patrol_revision(revision)
    assert revision["preview_after"]["state"]["score"] == 24
    assert build_patrol(source, edited, actions, require_complete=True)["state"]["score"] == 24
    assert board["objectives"][1]["reward"] == 11


@pytest.mark.parametrize("tamper", [
    lambda p: p.update(demo="not_a_report"),
    lambda p: p["demo"].update(actions="not_a_list"),
    lambda p: p["manifest"][0].update(bytes=999999),
])
def test_malformed_package_fails_closed_even_with_recomputed_digest(tamper):
    source = fixture("harbor_lantern_quay.json")
    board = fixture("harbor_lantern_quay_patrol.json")
    actions = fixture("harbor_lantern_quay_patrol_demo.json")
    package = build_patrol_package(source, board, actions, package_id="lantern_patrol")
    damaged = deepcopy(package)
    tamper(damaged)
    damaged["package_digest"] = digest({k: v for k, v in damaged.items()
                                          if k != "package_digest"})
    with pytest.raises(HarborError):
        verify_patrol_package(damaged)
