"""Original scene reachability, alternate endings, bounded audit honesty."""
from __future__ import annotations

import copy
import json
import pytest

from skeleton.game.gameplay.scene_travel import (
    SceneTravelError, _advance, new_session, original_demo,
    resume_session, verify_session,
)
from skeleton.game.gameplay.scene_ending_audit import (
    audit_endings, cli,
)


def test_original_world_has_replay_proven_victory_and_failure():
    world, _ = original_demo()
    result = audit_endings(world)
    assert result["coverage"] == "complete"
    assert result["endings"]["won"]["status"] == "found"
    assert result["endings"]["lost"]["status"] == "found"
    for phase in ("won", "lost"):
        witness = result["endings"][phase]["witness"]
        replay = resume_session(new_session(world), witness["actions"])
        assert verify_session(replay)["state_digest"] == witness["final_state_digest"]
        assert replay["state"]["phase"] == phase
    assert result["source_digest"] == new_session(world)["source_digest"]


def test_audit_can_resume_from_saved_state_without_rewriting_history():
    world, actions = original_demo()
    first = resume_session(new_session(world), actions[:1])
    result = audit_endings(session=first)
    witness = result["endings"]["won"]["witness"]
    assert witness is not None
    replay = resume_session(first, witness["actions"])
    assert replay["state"]["phase"] == "won"
    assert replay["journal"][0] == first["journal"][0]


def test_small_state_budget_is_inconclusive_not_unreachable():
    world, _ = original_demo()
    result = audit_endings(world, max_states=1)
    assert result["coverage"] == "inconclusive"
    assert result["budget_exhausted"]
    assert result["endings"]["won"]["status"] == "inconclusive"


def test_small_depth_is_inconclusive_not_unreachable():
    world, _ = original_demo()
    result = audit_endings(world, max_depth=1)
    assert result["coverage"] == "inconclusive"
    assert result["endings"]["won"]["status"] in ("inconclusive", "found")


def test_unreachable_authored_scene_is_reported_as_unobserved():
    world, _ = original_demo()
    extra = {
        "id": "isolated", "ending": "victory",
        "pickups": [], "exits": [],
    }
    world["scenes"].append(extra)
    result = audit_endings(world)
    assert result["coverage"] == "complete"
    assert "isolated" in result["unobserved_scenes"]


@pytest.mark.parametrize("budget", [0, True, -1, 4097])
def test_invalid_state_budget_fails_closed(budget):
    world, _ = original_demo()
    with pytest.raises(SceneTravelError, match="state budget"):
        audit_endings(world, max_states=budget)


@pytest.mark.parametrize("budget", [0, True, -1, 513])
def test_invalid_depth_budget_fails_closed(budget):
    world, _ = original_demo()
    with pytest.raises(SceneTravelError, match="depth budget"):
        audit_endings(world, max_depth=budget)


def test_tampered_resume_is_rejected_before_audit():
    world, actions = original_demo()
    session = resume_session(new_session(world), actions[:1])
    forged = copy.deepcopy(session)
    forged["state"]["inventory"] = ["master_key"]
    with pytest.raises(SceneTravelError):
        audit_endings(session=forged)


def test_cli_demo_and_main_entrypoint(capsys):
    assert cli(["--demo"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["endings"]["won"]["status"] == "found"
    from skeleton.__main__ import main
    assert main(["scene-travel", "audit", "--demo"]) == 0
    assert json.loads(capsys.readouterr().out)["schema_version"] == (
        "skeleton.scene_ending_audit.v1"
    )
