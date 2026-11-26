"""Canonical multi-scene NPC itinerary: replay, CLI/Jeeves parity and guards."""
import json

import pytest

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_canon_proof import audit_canon_source
from skeleton.ai.game_builder.studio_ecosystem_dialogue_staging import compile_dialogue_staging
from skeleton.ai.game_builder.studio_ecosystem_dialogue_itinerary import (
    ITINERARY_SCHEMA, plan_dialogue_itinerary,
)
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError, replay_quest
from skeleton.ai.agents.jeeves.studio_walk_tool import (
    DIALOGUE_ITINERARY_REQUEST_SCHEMA, execute_dialogue_itinerary_tool,
)

PROJECT = "studio_arena_fighting_glacial_fjord"


def fixture():
    docs = read_blueprint(PROJECT)
    cards = compile_dialogue_staging(docs, [], authorized=True)["cards"]
    targets = [cards[0]["scene_id"], cards[-1]["scene_id"]]
    source = audit_canon_source(docs, authorized=True)["source_digest"]
    return docs, targets, source


def test_ordered_itinerary_replay_and_source_unchanged():
    docs, targets, source = fixture()
    original = json.dumps(docs, sort_keys=True)
    result = plan_dialogue_itinerary(
        docs, [], target_scene_ids=targets,
        expected_source_digest=source, authorized=True)
    assert result["schema"] == ITINERARY_SCHEMA
    assert len(result["hops"]) == 2
    assert result["step_count"] == len(result["steps"])
    assert result["planned_session_digest"] == result["planned_quest_receipt"]["session_digest"]
    assert replay_quest(docs, result["planned_quest_receipt"]["choices"],
                        authorized=True).digest == result["planned_session_digest"]
    assert all(not hop["scene_played_verified"] for hop in result["hops"])
    assert not result["file_write_performed"] and not result["release_certified"]
    assert json.dumps(docs, sort_keys=True) == original
    assert result == plan_dialogue_itinerary(
        docs, [], target_scene_ids=targets,
        expected_source_digest=source, authorized=True)


def test_completed_itinerary_is_idempotent():
    docs, targets, source = fixture()
    first = plan_dialogue_itinerary(
        docs, [], target_scene_ids=targets,
        expected_source_digest=source, authorized=True)
    after = plan_dialogue_itinerary(
        docs, first["planned_quest_receipt"]["choices"], target_scene_ids=targets,
        expected_source_digest=source,
        expected_session_digest=first["planned_session_digest"], authorized=True)
    assert after["step_count"] == 0
    assert after["planned_session_digest"] == first["planned_session_digest"]


@pytest.mark.parametrize("override", [
    {"target_scene_ids": []}, {"target_scene_ids": ["forged"]},
    {"target_scene_ids": ["../escape"]}, {"target_scene_ids": "forged"},
    {"target_scene_ids": [True]}, {"target_scene_ids": ["duplicate", "duplicate"]},
    {"expected_source_digest": "0" * 64},
    {"expected_session_digest": "0" * 64},
])
def test_invalid_targets_and_leases_fail_closed(override):
    docs, targets, source = fixture()
    kwargs = dict(target_scene_ids=targets, expected_source_digest=source, authorized=True)
    kwargs.update(override)
    with pytest.raises(StudioQuestError):
        plan_dialogue_itinerary(docs, [], **kwargs)


def test_operator_authority_required():
    docs, targets, source = fixture()
    with pytest.raises(PermissionError):
        plan_dialogue_itinerary(
            docs, [], target_scene_ids=targets,
            expected_source_digest=source, authorized=False)


def test_cli_and_typed_jeeves_parity(capsys):
    from scripts.studio_ecosystem_cli import main
    docs, targets, source = fixture()
    request = {"schema": DIALOGUE_ITINERARY_REQUEST_SCHEMA,
               "project_id": PROJECT, "expected_source_digest": source,
               "actions": [], "target_scene_ids": targets}
    typed = execute_dialogue_itinerary_tool(request, authorized=True)
    assert main(["--project", PROJECT, "--dialogue-stage", "--dialogue-actions", "[]",
                 "--dialogue-expected-digest", source,
                 "--dialogue-itinerary-scenes", json.dumps(targets)]) == 0
    assert json.loads(capsys.readouterr().out) == typed["detail"]
    with pytest.raises(StudioQuestError):
        execute_dialogue_itinerary_tool({**request, "unknown": 1}, authorized=True)
    with pytest.raises(SystemExit):
        main(["--project", PROJECT, "--dialogue-itinerary-scenes", "[]"])
    with pytest.raises(SystemExit):
        main(["--project", PROJECT, "--dialogue-stage",
              "--dialogue-itinerary-scenes", json.dumps(targets),
              "--dialogue-route-scene", targets[0]])


def test_private_itinerary_handoff_roundtrip_and_exclusive_write(tmp_path, capsys):
    from scripts.studio_ecosystem_cli import main
    docs, targets, source = fixture()
    output = tmp_path / "npc-itinerary"
    args = ["--project", PROJECT, "--dialogue-stage",
            "--dialogue-actions", "[]", "--dialogue-expected-digest", source,
            "--dialogue-itinerary-scenes", json.dumps(targets),
            "--output", str(output)]
    assert main(args) == 0
    written = json.loads(capsys.readouterr().out)
    assert written["file_write_performed"] is True
    assert main(["--project", PROJECT, "--dialogue-stage",
                 "--dialogue-import", str(output),
                 "--dialogue-expected-digest", source]) == 0
    restored = json.loads(capsys.readouterr().out)
    assert restored["session_digest"] == written["itinerary"]["planned_session_digest"]
    with pytest.raises(SystemExit):
        main(args)
    assert sorted(p.name for p in output.iterdir()) == ["dialogue.json", "receipt.json"]
