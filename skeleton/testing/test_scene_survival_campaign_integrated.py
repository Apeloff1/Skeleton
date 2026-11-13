"""Campaign author, route and interactive integration acceptance."""
import copy
import io
import json

import pytest

from skeleton.game.gameplay.scene_survival_campaign import (
    export_campaign, import_campaign, original_campaign, simulate_campaign,
    verify_campaign,
)
from skeleton.game.gameplay.scene_survival_campaign_author import (
    apply_author, new_author, preview_author, solve_author, verify_author,
)
from skeleton.game.gameplay.scene_survival_campaign_interactive import (
    play_campaign,
)
from skeleton.game.gameplay.scene_survival_campaign_route import (
    solve_campaign, verify_plan,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError


def _events(stream):
    return [json.loads(line) for line in stream.getvalue().splitlines()]


def test_author_optimistic_lease_and_earned_preview():
    source, actions = original_campaign()
    document = new_author(source)
    edit = {"kind": "set_reward", "stage_id": "quay_crossing", "value": 15}
    changed = apply_author(
        document, edit, expected_digest=document["source_digest"],
        expected_revision=0)
    assert changed["revision"] == 1
    assert verify_author(changed) == changed
    preview = preview_author(changed, actions)
    assert preview["phase"] == "won"
    assert preview["score"] == 35
    assert import_campaign(preview["bundle"])["state"]["score"] == 35
    with pytest.raises(SceneTravelError, match="stale"):
        apply_author(
            changed, edit, expected_digest=document["source_digest"],
            expected_revision=0)


def test_author_replay_rejects_forged_source_and_edit_history():
    source, _ = original_campaign()
    doc = new_author(source)
    changed = apply_author(
        doc, {"kind": "set_required_score", "value": 20},
        expected_digest=doc["source_digest"], expected_revision=0)
    forged = copy.deepcopy(changed)
    forged["source"]["required_score"] = 1
    with pytest.raises(SceneTravelError):
        verify_author(forged)
    forged = copy.deepcopy(changed)
    forged["edits"][0]["value"] = 1
    with pytest.raises(SceneTravelError):
        verify_author(forged)
    with pytest.raises(SceneTravelError):
        apply_author(
            doc, {"kind": "remove_last_stage", "stage_id": "quay_crossing"},
            expected_digest=doc["source_digest"], expected_revision=0)


def test_route_is_replay_proven_and_portable():
    source, _ = original_campaign()
    route = solve_campaign(source, max_states=1024, max_depth=32)
    assert route["status"] == "found"
    assert len(route["stages"]) == 2
    final = verify_plan(route, source=source)
    assert final["state"]["phase"] == "won"
    assert final["state"]["score"] == 30
    assert final == simulate_campaign(source, route["actions"])
    assert import_campaign(export_campaign(final)) == final
    altered = copy.deepcopy(route)
    altered["portable_checksum"] = "0" * 64
    with pytest.raises(SceneTravelError):
        verify_plan(altered, source=source)
    authored = solve_author(new_author(source), max_states=1024, max_depth=32)
    assert authored["route"] == route


def test_route_budget_exhaustion_is_not_false_impossibility():
    source, _ = original_campaign()
    limited = solve_campaign(source, max_states=1, max_depth=1)
    assert limited["status"] == "inconclusive"
    assert limited["final_state_digest"] is None
    with pytest.raises(SceneTravelError, match="not a winning witness"):
        verify_plan(limited, source=source)


def test_interactive_play_checkpoint_and_resume_without_reward_forgery():
    source, actions = original_campaign()
    from skeleton.game.gameplay.scene_tile_survival_interactive import (
        parse_player_action,
    )
    lines = []
    for action in actions:
        if action["kind"] == "rest":
            lines.append("rest")
        else:
            inner = action["action"]
            if inner["kind"] == "move":
                lines.append(inner["direction"])
            elif inner["kind"] == "collect":
                lines.append("collect " + inner["pickup_id"])
            else:
                lines.append("travel " + inner["exit_id"])
    assert all(parse_player_action(line) == action
               for line, action in zip(lines, actions))
    out = io.StringIO()
    with pytest.raises(SceneTravelError, match="input ended"):
        play_campaign(
            source, input_stream=io.StringIO("\n".join(lines[:2]) + "\n"),
            output_stream=out)
    checkpoint = _events(out)[-1]
    assert checkpoint["event"] == "checkpoint"
    assert checkpoint["reason"] == "input_eof"
    saved = checkpoint["session"]
    assert verify_campaign(saved)["state"]["score"] == 0
    resumed = play_campaign(
        session=saved, expected_source_digest=saved["source_digest"],
        input_stream=io.StringIO("\n".join(lines[2:]) + "\n"),
        output_stream=io.StringIO())
    assert resumed == simulate_campaign(source, actions)
    assert resumed["state"]["phase"] == "won"


def test_interactive_invalid_inputs_do_not_mutate_checkpoint():
    source, _ = original_campaign()
    out = io.StringIO()
    with pytest.raises(SceneTravelError, match="retries exhausted"):
        play_campaign(
            source, input_stream=io.StringIO("teleport\nrest\nfly\n"),
            output_stream=out)
    events = _events(out)
    assert events[-1]["reason"] == "invalid_input_limit"
    assert events[-1]["session"]["state"]["tick"] == 0
    with pytest.raises(SceneTravelError, match="trusted digest"):
        play_campaign(
            source, expected_source_digest="0" * 64,
            input_stream=io.StringIO(), output_stream=io.StringIO())
