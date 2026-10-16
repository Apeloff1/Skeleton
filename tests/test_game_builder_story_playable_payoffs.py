"""A signed novel payoff must be a witnessed *playable* consequence."""
from __future__ import annotations

from copy import deepcopy
import json

import pytest

from skeleton.ai.game_builder.story_dramaturgy_graph import audit_threads
from skeleton.ai.game_builder.story_gameplay_bridge import review_story_gameplay
from skeleton.ai.game_builder.story_playable_payoffs import (
    PlayablePayoffError, audit_playable_payoffs,
)
from skeleton.developer.game_cli import run_game_cli
from tests.test_game_builder_story_canon_fabric import scene_source
from tests.test_game_builder_story_dramaturgy_graph import fulfilled
from tests.test_game_builder_story_gameplay_bridge import fixture


def verified(*, replay_payoff=True, branch_count=2):
    bible, scenes, world, runs, bindings = fixture("story_player_game")
    scenes.append(scene_source(bible, 2, scenes[-1]))
    for binding in bindings:
        binding["scene_sequence"] = 2 if replay_payoff else 1
        binding["source_anchor"] = "arrival_2" if replay_payoff else "visit_1"
    if branch_count == 1:
        runs[:] = runs[:1]
        bindings[:] = bindings[:1]
    dramaturgy = audit_threads(bible, scenes, [fulfilled()])
    game = review_story_gameplay(bible, scenes, world, runs, bindings)
    return dramaturgy, game, bible, scenes, world, runs, bindings


def test_actual_later_signed_payoff_requires_exact_original_game_choice():
    literary, gameplay, *_ = verified()
    report = audit_playable_payoffs(
        literary, gameplay, demand_alternative_outcomes=True,
    )
    assert report["ok"], report
    assert report["declared_dramatic_threads"] == 1
    assert report["dramatic_threads_with_played_payoff"] == 1
    assert report["all_declared_story_payoffs_executed"]
    assert report["payoffs"][0]["qualifying_branch_pairs"] == 2
    assert len(report["payoffs"][0]["executed_proofs"]) == 2
    assert report["source_replay_join_sha256"]
    assert not report["full_game_runtime_or_platform_certified"]
    assert not report["artistic_story_quality_verified"]


def test_unrelated_executed_quest_does_not_resolve_signed_story_payoff():
    literary, gameplay, *_ = verified(replay_payoff=False)
    result = audit_playable_payoffs(literary, gameplay)
    assert not result["all_declared_story_payoffs_executed"]
    assert result["dramatic_threads_with_played_payoff"] == 0
    assert result["unresolved_or_unplayed_threads"] == [
        {"thread_id": "recovered_lantern_route", "issue": "unplayed_canonical_payoff"}
    ]


def test_two_named_replays_of_one_outcome_do_not_certify_branch_divergence():
    literary, gameplay, *_ = verified(branch_count=1)
    result = audit_playable_payoffs(
        literary, gameplay, demand_alternative_outcomes=True,
    )
    assert not result["all_declared_story_payoffs_executed"]
    assert result["unresolved_or_unplayed_threads"][0]["issue"] == (
        "no_distinct_playable_consequence"
    )
    assert result["payoffs"][0]["qualifying_branch_pairs"] == 1


def test_unresolved_canonical_thread_remains_unresolved_even_with_gameplay():
    literary, gameplay, bible, scenes, *_ = verified()
    unresolved = fulfilled(state="open")
    unresolved["payoff"] = None
    literary = audit_threads(bible, scenes, [unresolved])
    result = audit_playable_payoffs(literary, gameplay)
    assert not result["all_declared_story_payoffs_executed"]
    assert result["unresolved_or_unplayed_threads"][0]["issue"] == "no_canonical_payoff"


def test_different_history_cannot_borrow_old_gameplay_receipts():
    literary, gameplay, bible, scenes, *_ = verified()
    after = scene_source(bible, 3, scenes[-1])
    newer = audit_threads(bible, [*scenes, after], [fulfilled()])
    with pytest.raises(PlayablePayoffError, match="different signed story histories"):
        audit_playable_payoffs(newer, gameplay)


def test_dossier_combines_actual_story_threads_and_playable_ending_evidence(tmp_path):
    result = run_game_cli(["init", "story-player-game", "--dir", str(tmp_path)])
    assert result["ok"], result
    root = tmp_path / "story-player-game"
    _, _, bible, scenes, world, runs, bindings = verified()
    gameplay_source = root / "design" / "story_gameplay_dossier.json"
    game_doc = {
        "schema": "skeleton.jeeves.story_gameplay_dossier.v1",
        "bible": bible, "scenes": scenes,
        "director_world": world.payload(),
        "author_review_acknowledged": True,
        "replays": runs, "bindings": bindings,
        "require_distinct_choices": True,
    }
    gameplay_source.write_text(json.dumps(game_doc), encoding="utf-8")
    original = {
        "schema": "skeleton.jeeves.direction_dossier.v1",
        "bible": bible, "scenes": scenes,
        "expert_reviews": [],
        "dramatic_threads": [fulfilled()],
        "gameplay_source": "design/story_gameplay_dossier.json",
        "payoff_alternatives_required": True,
    }
    path = root / "design" / "story_direction_packet.json"
    path.write_text(json.dumps(original), encoding="utf-8")
    audit_args = [
        "jeeves", "direction-audit", "--project", str(root),
        "--source", "design/story_direction_packet.json", "--passes", "2",
    ]
    observed = run_game_cli(audit_args)
    assert observed["ok"], observed
    proof = observed["playable_payoffs"]
    assert proof["all_declared_story_payoffs_executed"]
    assert proof["dramatic_threads_with_played_payoff"] == 1
    assert proof["requires_alternative_outcomes"]
    assert not proof["professional_emotional_impact_verified"]
    revision = run_game_cli([
        "jeeves", "direction-revision", "--project", str(root),
        "--source", "design/story_direction_packet.json",
    ])
    assert revision["ok"], revision
    assert revision["playable_payoffs"]["all_declared_story_payoffs_executed"]
    assert not revision["source_files_modified"]

    damaged = deepcopy(game_doc)
    for entry in damaged["bindings"]:
        entry["source_anchor"] = "visit_1"
        entry["scene_sequence"] = 1
    gameplay_source.write_text(json.dumps(damaged), encoding="utf-8")
    unplayed = run_game_cli(audit_args)
    assert unplayed["ok"], unplayed
    assert not unplayed["playable_payoffs"]["all_declared_story_payoffs_executed"]
    revision = run_game_cli([
        "jeeves", "direction-revision", "--project", str(root),
        "--source", "design/story_direction_packet.json",
    ])
    assert revision["ok"], revision
    assert any(x["evidence_kind"] == "unplayed_story_payoff" for x in revision["work_items"])


def test_alternative_requirement_without_real_gameplay_fails_closed(tmp_path):
    created = run_game_cli(["init", "story-player-game", "--dir", str(tmp_path)])
    assert created["ok"]
    root = tmp_path / "story-player-game"
    _, _, bible, scenes, *_ = verified()
    data = {
        "schema": "skeleton.jeeves.direction_dossier.v1",
        "bible": bible, "scenes": scenes, "expert_reviews": [],
        "dramatic_threads": [fulfilled()],
        "payoff_alternatives_required": True,
    }
    (root / "design" / "story_direction_packet.json").write_text(json.dumps(data))
    result = run_game_cli([
        "jeeves", "direction-audit", "--project", str(root),
        "--source", "design/story_direction_packet.json",
    ])
    assert not result["ok"]
    assert "requires both signed dramatic threads and real gameplay replays" in result["error"]
