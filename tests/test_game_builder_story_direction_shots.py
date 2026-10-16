"""Authoritative cinematography review over approved StoryCanon stage sources."""
from __future__ import annotations

from copy import deepcopy
import json

import pytest

from skeleton.ai.game_builder.story_canon_fabric import BIBLE, SCENE, sign
from skeleton.ai.game_builder.story_direction_shot_pipeline import (
    ShotDirectionError, audit_cinematic_direction,
)
from skeleton.developer.game_cli import run_game_cli
from tests.test_game_builder_story_canon_fabric import canonical_bible
from tests.test_game_builder_story_continuity_assurance import (
    chapter_scene, observations, original_contract,
)


def original_production(project="film_room", scenes=2):
    bible = canonical_bible()
    bible["project"] = project
    bible = sign(bible, BIBLE)
    contract = original_contract(bible)
    history = []
    boards = []
    for sequence in range(1, scenes + 1):
        source = chapter_scene(bible, sequence, history[-1] if history else None)
        history.append(source)
        shots = observations(contract, bible, source)["cinematic_shots"]
        boards.append({"scene_sequence": sequence, "shots": shots})
    return bible, contract, history, boards


def test_actual_canon_shots_measured_without_claiming_film_performance():
    bible, contract, scenes, boards = original_production()
    verified = audit_cinematic_direction(bible, contract, scenes, boards, passes=5)
    assert verified["ok"]
    assert verified["original_canon_scenes"] == 2
    assert verified["total_shots"] == 2
    assert verified["total_timeline_ms"] == 12000
    assert verified["source_spoken_lines_covered"] == 2
    assert len(verified["repeatable_pre_render_receipts"]) == 5
    assert len({x["shot_receipt_digest"] for x in
                verified["repeatable_pre_render_receipts"]}) == 1
    assert all(x["canonical_owning_film_verifier_used"] for x in
               verified["repeatable_pre_render_receipts"])
    assert verified["per_scene"][0]["median_shot_duration_ms"] == 6000
    assert not verified["actual_rendered_video_screened"]
    assert not verified["actual_voice_and_lip_sync_verified"]
    assert not verified["book_or_hollywood_professional_quality_proven"]


@pytest.mark.parametrize("mutation", [
    lambda boards: boards[0]["shots"][0].update(voice_id="swapped"),
    lambda boards: boards[0]["shots"][0].update(face_id="not_original_face"),
    lambda boards: boards[0]["shots"][0].update(start_ms=250),
    lambda boards: boards[0]["shots"][0].update(duration_ms=1),
    lambda boards: boards[0]["shots"][0].update(dialogue_ids=[]),
    lambda boards: boards[0]["shots"][0].update(lighting="unsupported lighting"),
    lambda boards: boards[0]["shots"][0].update(cut="instant_teleport"),
    lambda boards: boards[0].update(scene_sequence=2),
    lambda boards: boards.pop(),
])
def test_cinematic_tampering_and_missing_board_fail_closed(mutation):
    bible, contract, scenes, boards = original_production()
    mutation(boards)
    with pytest.raises(ValueError):
        audit_cinematic_direction(bible, contract, scenes, boards)


def test_unauthorized_story_changes_do_not_turn_into_directorial_evidence():
    bible, contract, history, boards = original_production()
    history[0]["dialogue"][0]["text"] = "Unapproved replacement line"
    with pytest.raises(ValueError):
        audit_cinematic_direction(bible, contract, history, boards)


@pytest.mark.parametrize("count", [0, 9, -1])
def test_unbounded_per_invocation_scrutiny_is_not_allowed(count):
    bible, contract, history, boards = original_production()
    with pytest.raises(ShotDirectionError):
        audit_cinematic_direction(bible, contract, history, boards, passes=count)


def test_real_multi_shot_movement_and_editorial_measures():
    bible, contract, scenes, boards = original_production(scenes=1)
    first = deepcopy(boards[0]["shots"][0])
    establish = deepcopy(first)
    establish.update({
        "id": "establish", "camera": "establishing",
        "dialogue_ids": [], "duration_ms": 1200,
    })
    spoken = deepcopy(first)
    spoken.update({
        "id": "closeup", "camera": "tracking",
        "start_ms": 1200, "duration_ms": 5400,
    })
    boards[0]["shots"] = [establish, spoken]
    report = audit_cinematic_direction(bible, contract, scenes, boards, passes=2)
    assert report["total_shots"] == 2
    assert report["moving_camera_shots"] == 1
    assert report["total_timeline_ms"] == 6600
    assert report["per_scene"][0]["cameras"] == {"establishing": 1, "tracking": 1}
    assert report["per_scene"][0]["original_actor_screen_time_ms"]["alina"] == 6600
    assert report["per_scene"][0]["spoken_lines_source_covered"] == 1


def test_full_cli_uses_signed_exact_project_packet_and_approved_shotboard(tmp_path):
    result = run_game_cli(["init", "film-room", "--dir", str(tmp_path)])
    assert result["ok"], result
    root = tmp_path / "film-room"
    bible, contract, scenes, boards = original_production("film_room", scenes=2)
    packet = {
        "schema": "skeleton.jeeves.direction_dossier.v1",
        "bible": bible, "scenes": scenes, "expert_reviews": [],
        "production_contract": contract, "shot_boards": boards,
    }
    path = root / "design" / "story_direction_packet.json"
    path.write_text(json.dumps(packet), encoding="utf-8")
    args = [
        "jeeves", "direction-shots", "--project", str(root),
        "--source", "design/story_direction_packet.json", "--passes", "3",
    ]
    ok = run_game_cli(args)
    assert ok["ok"], ok
    assert ok["scrutiny_passes"] == 3
    assert ok["total_shots"] == 2
    assert not ok["rendered_film_or_original_game_certified"]
    assert path.read_text(encoding="utf-8") == json.dumps(packet)
    packet["shot_boards"][0]["shots"][0]["voice_id"] = "imposter"
    path.write_text(json.dumps(packet), encoding="utf-8")
    denied = run_game_cli(args)
    assert not denied["ok"]


def test_story_packet_other_project_and_unrelated_cli_option_fail(tmp_path):
    result = run_game_cli(["init", "film-room", "--dir", str(tmp_path)])
    assert result["ok"], result
    root = tmp_path / "film-room"
    bible, contract, scenes, boards = original_production("wrong_project", scenes=1)
    packet = {
        "schema": "skeleton.jeeves.direction_dossier.v1",
        "bible": bible, "scenes": scenes, "expert_reviews": [],
        "production_contract": contract, "shot_boards": boards,
    }
    (root / "design" / "story_direction_packet.json").write_text(
        json.dumps(packet), encoding="utf-8",
    )
    params = ["jeeves", "direction-shots", "--project", str(root),
              "--source", "design/story_direction_packet.json"]
    wrong = run_game_cli(params)
    assert not wrong["ok"]
    assert "different story project" in wrong["error"]
    with_unrelated = run_game_cli(params + ["--factor", "3"])
    assert not with_unrelated["ok"]
