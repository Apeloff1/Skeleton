"""Full source continuity must never turn source designs into release proof."""
from copy import deepcopy

import pytest

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_continuity import (
    audit_catalog_continuity, inspect_continuity,
)
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError


@pytest.mark.parametrize("project", [
    "studio_puzzle_expedition_copper_mesa",
    "studio_arena_fighting_glacial_fjord",
    "studio_collaborative_robotics_echo_caverns",
])
def test_two_source_families_have_causal_scene_quest_links(project):
    report = audit_catalog_continuity(project)
    assert report["source_consistent"], report["errors"]
    assert report["quest_stage_count"] == report["scene_count"] == 3
    assert report["authored_ending_count"] == 3
    assert report["release_certified"] is False
    assert not report["native_genre_runtime_verified"]
    assert report["unbound_ending_predicates"]


def test_unknown_stage_and_duplicate_scene_are_rejected():
    docs = read_blueprint("studio_arena_fighting_glacial_fjord")
    invalid = deepcopy(docs)
    invalid["scene"]["episode_plan"][1]["quest_stage"] = "nonexistent_stage"
    report = inspect_continuity(invalid)
    assert report["status"] == "source_rejected"
    assert "scene_references_unknown_quest_stage" in report["errors"]
    invalid = deepcopy(docs)
    invalid["scene"]["episode_plan"][1]["id"] = invalid["scene"]["episode_plan"][0]["id"]
    assert "duplicate_or_missing_scene_id" in inspect_continuity(invalid)["errors"]


def test_dialogue_cast_binding_and_fake_qa_passing_are_rejected():
    docs = read_blueprint("studio_arena_fighting_glacial_fjord")
    invalid = deepcopy(docs)
    invalid["scene"]["episode_plan"][1]["dialogue_hook"] = "invisible_voice"
    assert "dialogue_hook_unowned" in inspect_continuity(invalid)["errors"]
    invalid = deepcopy(docs)
    invalid["verification"]["quality_gates"][0]["status"] = "success"
    assert "unearned_qa_gate_status" in inspect_continuity(invalid)["errors"]
    invalid = deepcopy(docs)
    invalid["verification"]["release_certified"] = True
    with pytest.raises(StudioQuestError):
        inspect_continuity(invalid)


def test_original_wave1_scene_contract_binds_to_authored_quest():
    docs = read_blueprint("studio_aerial_traversal_amber_highlands")
    report = inspect_continuity(docs)
    assert report["source_consistent"], report["errors"]
    changed = deepcopy(docs)
    changed["scene"]["episode_plan"][1]["quest"] = "fabricated_stage"
    report = inspect_continuity(changed)
    assert "scene_references_unknown_quest_stage" in report["errors"]
    changed = deepcopy(docs)
    changed["scene"]["episode_plan"][1]["objects"] = []
    assert "scene_without_interactions" in inspect_continuity(changed)["errors"]
