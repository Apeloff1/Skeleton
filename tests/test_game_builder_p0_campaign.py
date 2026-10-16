"""P0 acceptance: authored multi-quest campaign execution is genuine, not invented."""
from __future__ import annotations

from dataclasses import replace
from copy import deepcopy
import json

import pytest

from skeleton.ai.game_builder.quest_scene_engine import DirectorError
from skeleton.ai.game_builder.quest_scene_forge import forge_director
from skeleton.ai.game_builder.quest_campaign_completion import (
    CampaignCompletionError, play_campaign, compare_campaign_branches,
)
from skeleton.ai.game_builder.quest_playthrough_journal import (
    DirectorSegmentError, replay_director_segments,
)
from skeleton.developer.game_cli import run_game_cli
from skeleton.developer.jeeves_game_p0_acceptance import GATES, assess_p0


def original_world(project="campaign_p0"):
    return forge_director(
        project, seed=41839,
        regions=("haven", "cliff", "river", "forest", "market"),
        quest_types=("main_story", "rival_story", "epilogue"),
        stages=3, placement="story",
    )


def test_entire_original_quest_chain_requires_real_actions_for_each_stage():
    world = original_world()
    witness = play_campaign(world, preference=0, segment_size=2)
    report = witness.report
    assert report["all_authored_quests_executed"]
    assert report["all_authored_stages_executed"]
    assert report["quests_completed"] == 3
    assert report["stages_completed"] == 9
    assert report["segments_verified"] > 9
    assert report["action_count"] >= 9
    assert len(report["results"]) == 9
    rechecked = replay_director_segments(world, witness.replay["segments"])
    assert rechecked.digest == report["replay_receipt_sha256"]
    assert set(rechecked.final.complete) == {quest.key for quest in world.quests}
    assert len(rechecked.final.results) == 9
    assert report["native_engine_playthrough_verified"] is False
    assert report["actual_save_file_recovery_verified"] is False
    assert report["model_training_performed"] is False


def test_same_source_two_complete_campaign_branches_have_real_different_endings():
    world = original_world()
    result = compare_campaign_branches(world, routes=2)
    assert result["ok"], result
    assert result["all_routes_completed"]
    assert result["branch_outcomes_materially_distinct"]
    assert len(result["divergent_quest_stages"]) >= 1
    assert result["route_count"] == 2
    assert result["route_reports"][0]["final_director_state_sha256"] != (
        result["route_reports"][1]["final_director_state_sha256"]
    )
    assert result["native_full_game_or_installed_app_certified"] is False


def test_alternative_route_on_one_method_only_fails_without_fabricating_branch():
    world = original_world()
    no_alternative = replace(
        world.quests[0],
        stages=tuple(replace(stage, solutions=(stage.solutions[0],))
                     for stage in world.quests[0].stages),
    )
    # Also reduce the other quests to the exact one method, so every
    # route executes the same original outcome.
    quests = (no_alternative,) + tuple(
        replace(quest, stages=tuple(replace(stage, solutions=(stage.solutions[0],))
                                    for stage in quest.stages))
        for quest in world.quests[1:]
    )
    restricted = replace(world, quests=quests)
    report = compare_campaign_branches(restricted, routes=2)
    assert report["ok"] is False
    assert report["branch_outcomes_materially_distinct"] is False
    assert report["distinct_outcome_stage_count"] == 0
    assert report["all_routes_completed"] is True


def test_dependency_cycle_is_blocked_instead_of_masquerading_as_a_win():
    world = forge_director(
        "blocked_campaign", seed=7,
        regions=("start", "north", "south", "west"),
        quest_types=("main_story", "rival_story"), stages=2,
    )
    first = replace(world.quests[0], requires_quests=(world.quests[1].key,))
    # The canonical DirectorWorld constructor already rejects the cycle.
    # A campaign never needs to override or bypass that source authority.
    with pytest.raises(DirectorError, match="dependency cycle"):
        replace(world, quests=(first, world.quests[1]))


@pytest.mark.parametrize("bad", [-1, 8, True, 1.5])
def test_invalid_route_preference_is_refused(bad):
    with pytest.raises(CampaignCompletionError, match="route preference"):
        play_campaign(original_world(), preference=bad)


def test_missing_checkpoint_or_modified_actions_fail_real_gameplay_verifier():
    world = original_world()
    witness = play_campaign(world, preference=1, segment_size=3)
    forged = deepcopy(witness.replay["segments"])
    forged[1]["start_digest"] = "0" * 64
    with pytest.raises(DirectorSegmentError, match="checkpoint"):
        replay_director_segments(world, forged)
    forged = deepcopy(witness.replay["segments"])
    forged[1]["actions"][0]["key"] = "invented_ability"
    with pytest.raises(ValueError):
        replay_director_segments(world, forged)


def test_campaign_cli_runs_approved_local_world_and_rejects_forgery(tmp_path):
    created = run_game_cli(["init", "campaign-p0", "--dir", str(tmp_path)])
    assert created["ok"], created
    root = tmp_path / "campaign-p0"
    world = original_world("campaign_p0")
    packet = {
        "schema": "skeleton.jeeves.director_campaign_source.v1",
        "director_world": world.payload(), "author_review_acknowledged": True,
    }
    (root / "design" / "director_campaign_source.json").write_text(json.dumps(packet))
    command = [
        "jeeves", "direction-campaign", "--project", str(root),
        "--source", "design/director_campaign_source.json", "--passes", "2",
    ]
    report = run_game_cli(command)
    assert report["ok"], report
    assert report["all_routes_completed"]
    assert report["route_count"] == 2
    assert report["source_dossier_sha256"]
    assert not report["qualified_for_release"]
    saved = run_game_cli(command + ["--output", "original_campaign"])
    assert saved["ok"], saved
    assert len(saved["saved_campaigns"]) == 2
    assert all(s["ok"] for s in saved["saved_campaigns"])
    restored = run_game_cli([
        "jeeves", "direction-campaign-reopen", "--project", str(root),
        "--source", "design/director_campaign_source.json",
        "--output", "original_campaign_0",
    ])
    assert restored["ok"], restored
    assert len(restored["restored_completed_quests"]) == 3
    assert restored["native_godot_savegame_verified"] is False
    assert restored["actual_restored_state_sha256"] == (
        saved["route_reports"][0]["final_director_state_sha256"]
    )
    no_overwrite = run_game_cli(command + ["--output", "original_campaign"])
    assert not no_overwrite["ok"]
    assert "already exists" in no_overwrite["error"]
    packet["author_review_acknowledged"] = False
    (root / "design" / "director_campaign_source.json").write_text(json.dumps(packet))
    refused = run_game_cli(command)
    assert not refused["ok"]
    assert "reviewed" in refused["error"]
    packet["author_review_acknowledged"] = True
    packet["director_world"]["project_id"] = "foreign_project"
    (root / "design" / "director_campaign_source.json").write_text(json.dumps(packet))
    refused = run_game_cli(command)
    assert not refused["ok"]


def test_p0_acceptance_diagnostic_never_confuses_source_with_release(tmp_path):
    assert len(GATES) == 20
    assert len({id for id, _, _ in GATES}) == 20
    created = run_game_cli(["init", "campaign-p0", "--dir", str(tmp_path)])
    assert created["ok"], created
    root = tmp_path / "campaign-p0"
    report = run_game_cli([
        "jeeves", "p0-acceptance", "--project", str(root),
    ])
    assert report["ok"], report
    assert report["required_p0_gates"] == 20
    assert report["independently_qualified_p0_gates"] == 0
    assert report["blocked_p0_gates"] == 20
    assert report["p0_complete"] is False
    assert report["product_release_qualified"] is False
    assert report["whole_application_p0_complete"] is False
    additional = report["additional_noncompensable_app_p0"]
    assert {"CHAT-01", "CHAT-02", "CHAT-10", "DRAGON-P0", "APP-E2E"}.issubset(
        {row["id"] for row in additional}
    )
    assert all(row["state"] == "blocked_unverified" for row in additional)
    assert set(row["id"] for row in report["gates"]) == {
        "P0-" + str(n).zfill(2) for n in range(1, 21)
    }
    assert all(row["state"] == "blocked_unverified" for row in report["gates"])
    report2 = assess_p0(root)
    assert report2["p0_complete"] is False
    malicious = run_game_cli([
        "jeeves", "p0-acceptance", "--project", str(root), "--target", "ps5",
    ])
    assert not malicious["ok"]


def test_campaign_save_restores_actual_story_state_and_rejects_tampering(tmp_path):
    from skeleton.ai.game_builder.quest_campaign_save import (
        CampaignSaveError, read_campaign_save, write_campaign_save,
    )
    assert run_game_cli(["init", "campaign-p0", "--dir", str(tmp_path)])["ok"]
    root = tmp_path / "campaign-p0"
    world = original_world()
    witness = play_campaign(world, preference=1, segment_size=4)
    saved = write_campaign_save(root, "chapter_finale", world, witness)
    assert saved["ok"]
    assert saved["native_or_godot_save_certified"] is False
    state = read_campaign_save(root, "chapter_finale", world)
    assert set(state.complete) == set(q.key for q in world.quests)
    assert state.digest == witness.report["final_director_state_sha256"]
    with pytest.raises(CampaignSaveError, match="already exists"):
        write_campaign_save(root, "chapter_finale", world, witness)
    path = root / "design" / "campaign_saves" / "chapter_finale.json"
    packet = json.loads(path.read_text())
    packet["replay"]["segments"][0]["actions"][0]["key"] = "forged_action"
    path.write_text(json.dumps(packet))
    with pytest.raises(CampaignSaveError, match="receipt mismatch"):
        read_campaign_save(root, "chapter_finale", world)


def test_campaign_save_refuses_cross_project_world_and_unsafe_name(tmp_path):
    from skeleton.ai.game_builder.quest_campaign_save import (
        CampaignSaveError, read_campaign_save, write_campaign_save,
    )
    assert run_game_cli(["init", "campaign-p0", "--dir", str(tmp_path)])["ok"]
    root = tmp_path / "campaign-p0"
    world = original_world()
    witness = play_campaign(world)
    with pytest.raises(CampaignSaveError, match="invalid original save identity"):
        write_campaign_save(root, "../overwrite", world, witness)
    write_campaign_save(root, "safe", world, witness)
    foreign = original_world("foreign_project")
    with pytest.raises(CampaignSaveError, match="different original game world"):
        read_campaign_save(root, "safe", foreign)
