"""Source-authored studio quests have bounded, replayable gameplay choices."""
from dataclasses import replace

import pytest

from skeleton.ai.game_builder.studio_ecosystem_quest import (
    StudioQuestError, available_stages, compile_quest_program,
    quest_progress, replay_quest, start_quest, step_quest, verify_quest_session,
    start_catalog_quest,
)


def sample():
    return {
        "quest": {
            "project_id": "studio_test_system",
            "release_certified": False,
            "stage_graph": [
                {"id": "survey", "prerequisites": [], "alternatives": ["walk", "scan"], "reward": "map"},
                {"id": "repair", "prerequisites": ["survey"], "alternatives": ["patch", "bypass"], "reward": "tool"},
                {"id": "verify", "prerequisites": ["repair"], "alternatives": ["audit", "measure"], "reward": "ledger"},
            ],
        },
        "narrative": {
            "project_id": "studio_test_system",
            "release_certified": False,
            "endings": [
                {"id": "commons", "requires": ["map", "tool", "ledger"]},
                {"id": "unverified", "requires": ["external_physically_verified"]},
            ],
        },
    }


def test_authorized_quest_choices_and_causal_progress():
    documents = sample()
    with pytest.raises(PermissionError):
        start_quest(documents, authorized=False)
    initial = start_quest(documents, authorized=True)
    assert available_stages(initial, documents) == ("survey",)
    with pytest.raises(StudioQuestError):
        step_quest(initial, documents, stage="repair", alternative="patch", authorized=True)
    s1 = step_quest(initial, documents, stage="survey", alternative="scan", authorized=True)
    with pytest.raises(StudioQuestError):
        step_quest(s1, documents, stage="survey", alternative="walk", authorized=True)
    s2 = step_quest(s1, documents, stage="repair", alternative="bypass", authorized=True)
    completed = step_quest(s2, documents, stage="verify", alternative="audit", authorized=True)
    assert replay_quest(documents, completed.choices, authorized=True) == completed
    assert quest_progress(completed, documents)["stage_completed"] == 3
    status = quest_progress(completed, documents)
    assert status["sandbox_endings_eligible"] == ["commons"]
    assert status["unmet_ending_predicates"]["unverified"] == ["external_physically_verified"]
    assert not completed.receipt()["release_certified"]
    assert not status["external_evidence_verified"]


def test_tampering_and_source_drift_fail_closed():
    docs = sample()
    start = start_quest(docs, authorized=True)
    modified = replace(start, completed=("survey",))
    with pytest.raises(StudioQuestError):
        verify_quest_session(modified, docs)
    stolen = replace(start, digest="0" * 64)
    with pytest.raises(StudioQuestError):
        available_stages(stolen, docs)
    changed = sample()
    changed["quest"]["stage_graph"][0]["reward"] = "different"
    with pytest.raises(StudioQuestError):
        quest_progress(start, changed)
    with pytest.raises(StudioQuestError):
        replay_quest(docs, (("repair", "patch"),), authorized=True)
    with pytest.raises(PermissionError):
        replay_quest(docs, (), authorized=False)


def test_bad_graph_and_unearned_release_claim_are_rejected():
    docs = sample()
    docs["quest"]["stage_graph"][0]["prerequisites"] = ["verify"]
    with pytest.raises(StudioQuestError):
        compile_quest_program(docs)
    docs = sample()
    docs["narrative"]["release_certified"] = True
    with pytest.raises(StudioQuestError):
        compile_quest_program(docs)
    docs = sample()
    docs["quest"]["stage_graph"][1]["alternatives"] = ["patch", "patch"]
    with pytest.raises(StudioQuestError):
        compile_quest_program(docs)


@pytest.mark.parametrize("project", [
    "studio_puzzle_expedition_copper_mesa",
    "studio_arena_fighting_glacial_fjord",
])
def test_real_catalog_both_stage_schemas_execute_local_choices(project):
    documents, start = start_catalog_quest(project, authorized=True)
    program = compile_quest_program(documents)
    assert len(program.stages) == 3
    session = start
    for stage in program.stages:
        assert stage.key in available_stages(session, documents)
        session = step_quest(session, documents, stage=stage.key,
                             alternative=stage.alternatives[0], authorized=True)
    verify_quest_session(session, documents)
    assert quest_progress(session, documents)["stage_completed"] == 3
    assert session.receipt()["release_certified"] is False
