"""Branch-impact matrix: all authored alternatives, source leases and CLI parity."""
import json

import pytest

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_canon_proof import audit_canon_source
from skeleton.ai.game_builder.studio_ecosystem_choice_impact_matrix import (
    CHOICE_IMPACT_SCHEMA, page_choice_impacts,
)
from skeleton.ai.game_builder.studio_ecosystem_quest import (
    StudioQuestError, replay_quest,
)
from skeleton.ai.agents.jeeves.studio_walk_tool import (
    CHOICE_IMPACT_REQUEST_SCHEMA, execute_choice_impact_tool,
)

PROJECT = "studio_arena_fighting_glacial_fjord"


def fixture():
    docs = read_blueprint(PROJECT)
    source = audit_canon_source(docs, authorized=True)["source_digest"]
    session = replay_quest(docs, [], authorized=True)
    return docs, source, session


def test_all_currently_available_alternatives_are_replayed_without_mutation():
    docs, source, session = fixture()
    before = json.dumps(docs, sort_keys=True)
    result = page_choice_impacts(
        docs, [], authorized=True, expected_source_digest=source,
        expected_session_digest=session.digest)
    assert result["schema"] == CHOICE_IMPACT_SCHEMA
    assert result["total_available_stages"] >= 1
    assert result["stages"]
    assert result["simulation_model"] == "authored_stage_reward_only"
    assert all(card["alternative_count"] == len(card["alternatives"])
               for card in result["stages"])
    assert all(not item["external_consequence_verified"]
               for card in result["stages"] for item in card["alternatives"])
    assert all(not card["alternative_specific_narrative_consequences_verified"]
               for card in result["stages"])
    assert result["file_write_performed"] is False
    assert result["release_certified"] is False
    assert json.dumps(docs, sort_keys=True) == before
    assert result == page_choice_impacts(
        docs, [], authorized=True, expected_source_digest=source,
        expected_session_digest=session.digest)


def test_mechanical_equivalence_is_not_misreported_as_story_equivalence():
    docs, source, _ = fixture()
    result = page_choice_impacts(
        docs, [], authorized=True, expected_source_digest=source)
    for card in result["stages"]:
        if card["alternative_count"] > 1:
            assert card["mechanical_outcomes_diverge"] is False
            assert len({c["mechanical_outcome_digest"]
                        for c in card["alternatives"]}) == 1


@pytest.mark.parametrize("overrides", [
    {"expected_source_digest": "0" * 64},
    {"expected_source_digest": True},
    {"expected_session_digest": "0" * 64},
    {"offset": -1}, {"offset": True}, {"offset": 1},
    {"limit": 0}, {"limit": 9}, {"limit": True},
    {"actions": [["not-a-stage", "forged"]]},
    {"actions": [True]},
])
def test_stale_leases_invalid_pages_and_forged_history_fail_closed(overrides):
    docs, source, _ = fixture()
    kwargs = dict(authorized=True, expected_source_digest=source)
    actions = overrides.get("actions", [])
    kwargs.update({key: value for key, value in overrides.items() if key != "actions"})
    with pytest.raises(StudioQuestError):
        page_choice_impacts(docs, actions, **kwargs)


def test_authority_is_not_inferred_from_caller():
    docs, source, _ = fixture()
    with pytest.raises(PermissionError):
        page_choice_impacts(
            docs, [], authorized=False, expected_source_digest=source)


def test_typed_jeeves_cli_parity_and_exclusive_modes(capsys):
    from scripts.studio_ecosystem_cli import main
    docs, source, _ = fixture()
    request = {
        "schema": CHOICE_IMPACT_REQUEST_SCHEMA,
        "project_id": PROJECT, "expected_source_digest": source,
        "actions": [], "limit": 2,
    }
    typed = execute_choice_impact_tool(request, authorized=True)
    assert main([
        "--project", PROJECT, "--choice-impact",
        "--choice-impact-expected-source", source,
        "--choice-impact-limit", "2", "--quest-actions", "[]",
    ]) == 0
    assert json.loads(capsys.readouterr().out) == typed["detail"]
    with pytest.raises(StudioQuestError):
        execute_choice_impact_tool({**request, "forged": 1}, authorized=True)
    with pytest.raises(PermissionError):
        execute_choice_impact_tool(request, authorized=False)
    with pytest.raises(SystemExit):
        main(["--project", PROJECT, "--choice-impact"])
    with pytest.raises(SystemExit):
        main(["--project", PROJECT, "--choice-impact",
              "--choice-impact-expected-source", source, "--play-quest"])
