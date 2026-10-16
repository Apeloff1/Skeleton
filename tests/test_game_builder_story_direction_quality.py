"""Book/film-level source direction gate tests; independent quality never faked."""
from __future__ import annotations

from copy import deepcopy
import json

import pytest

from skeleton.ai.game_builder.story_canon_fabric import SCENE, sign
from skeleton.ai.game_builder.story_direction_quality import (
    DIMS, DirectionError, evaluate_direction, revision_plan,
)
from skeleton.developer.game_cli import run_game_cli
from tests.test_game_builder_story_canon_fabric import canonical_bible, scene_source


def scenes(n: int):
    bible=canonical_bible()
    history=[]
    for i in range(1,n+1):
        history.append(scene_source(bible,i,history[-1] if history else None))
    return bible,history


def claimed_panel(score=95):
    return [
        {"reviewer_id":"novel_editor_original","role":"novel_editor",
         "source":"editor review receipt A", "scores":{name:score for name in DIMS}},
        {"reviewer_id":"film_director_original","role":"film_director",
         "source":"director review receipt B", "scores":{name:score for name in DIMS}},
    ]


def test_canonical_signed_source_produces_causal_and_dialogue_metrics():
    bible,history=scenes(4)
    report=evaluate_direction(bible,history,passes=3)
    assert report["ok"]
    assert len(report["canonical_receipts"])==3
    assert len({r["history_digest"] for r in report["canonical_receipts"]})==1
    observed=report["observed_story_metrics"]
    assert observed["canonical_scene_count"]==4
    assert observed["dialogue_lines"]==4
    assert observed["exact_dialogue_repeat_fraction"]==0.75
    assert observed["causal_source_references"]>0
    assert observed["character_state_transitions"]==0
    assert "unproven_character_transformation" in {
        r["kind"] for r in report["revision_work"]
    }
    assert not report["hollywood_level_film_quality_proven"]
    assert not report["book_publication_quality_proven"]
    assert not report["complete_game_story_certified"]


def test_source_tampering_and_invented_links_rejected_by_canonical_verifier():
    bible,history=scenes(3)
    history[1]["dialogue"][0]["text"]="Rewritten without original approval"
    with pytest.raises((ValueError,AssertionError)):
        evaluate_direction(bible,history)
    bible,history=scenes(2)
    history[1]["dialogue"][0]["references"]=["nonexistent_story_event"]
    history[1]=sign(history[1],SCENE)
    with pytest.raises(ValueError):
        evaluate_direction(bible,history)


def test_high_review_scores_are_only_claims_not_actual_hollywood_certificate():
    bible,history=scenes(1)
    result=evaluate_direction(bible,history,reviewers=claimed_panel())
    review=result["expert_review_claims"]
    assert review["claimed_professional_threshold_met"]
    assert review["scores_by_dimension"]["thematic_coherence"]["claimed_min"]==95
    assert not review["independent_review_verified"]
    assert not result["professional_story_quality_proven"]
    assert result["quality_bars"]["every_qualitative_dimension_at_least"]==90
    assert result["quality_bars"]["quality_threshold_relaxation_allowed"] is False


@pytest.mark.parametrize("reviews",[
    [claimed_panel()[0]],
    [claimed_panel()[0],claimed_panel()[0]],
    [dict(claimed_panel()[0],scores={name:90 for name in DIMS if name!="original_voice"}),
     claimed_panel()[1]],
    [dict(claimed_panel()[0],scores={name:(89 if name=="dialogue_subtext" else 95) for name in DIMS}),
     claimed_panel()[1]],
])
def test_review_sufficiency_duplicates_and_floor_are_fail_closed(reviews):
    bible,history=scenes(1)
    if len(reviews)==2 and reviews[0]["reviewer_id"]==reviews[1]["reviewer_id"]:
        with pytest.raises(DirectionError):
            evaluate_direction(bible,history,reviewers=reviews)
        return
    if len(reviews)==2 and set(reviews[0]["scores"])!=set(DIMS):
        with pytest.raises(DirectionError):
            evaluate_direction(bible,history,reviewers=reviews)
        return
    result=evaluate_direction(bible,history,reviewers=reviews)
    assert not result["expert_review_claims"]["claimed_professional_threshold_met"]


def test_revision_plan_preserves_review_required_and_does_not_write_source():
    bible,history=scenes(4)
    before=deepcopy(history)
    audit=evaluate_direction(bible,history,passes=8)
    revision=revision_plan(audit)
    assert revision["ok"]
    assert revision["source_identity"]==audit["source_identity"]
    assert revision["numeric_quality_floor_lowered"] is False
    assert revision["source_files_modified"] is False
    assert {"professional_readthrough","film_screening","playtested_agency"}.issubset(
        {item["evidence_kind"] for item in revision["work_items"]}
    )
    assert before==history
    with pytest.raises(DirectionError):
        evaluate_direction(bible,history,passes=9)


def test_journal_cli_review_and_revision_reuse_canonical_source(tmp_path):
    init=run_game_cli(["init","writer-room","--dir",str(tmp_path)])
    assert init["ok"],init
    root=tmp_path/"writer-room"
    bible,history=scenes(3)
    data={
        "schema":"skeleton.jeeves.direction_dossier.v1",
        "bible":bible,"scenes":history,"expert_reviews":claimed_panel(95),
    }
    source=root/"design"/"story_direction_packet.json"
    source.write_text(json.dumps(data),encoding="utf-8")
    cmd=["jeeves","direction-audit","--project",str(root),
         "--source","design/story_direction_packet.json","--passes","3"]
    result=run_game_cli(cmd)
    assert result["ok"],result
    assert result["observed_story_metrics"]["canonical_scene_count"]==3
    assert len(result["canonical_receipts"])==3
    assert not result["operator_review_scores_external_verified"]
    revision=run_game_cli(["jeeves","direction-revision","--project",str(root),
                           "--source","design/story_direction_packet.json"])
    assert revision["ok"],revision
    assert revision["work_items"]
    assert source.is_file()


def test_cli_dossier_missing_or_tampered_fails_closed(tmp_path):
    init=run_game_cli(["init","story-review","--dir",str(tmp_path)])
    assert init["ok"]
    root=tmp_path/"story-review"
    dossier=root/"design"/"story_direction_packet.json"
    data={"schema":"skeleton.jeeves.direction_dossier.v1",
          "bible":canonical_bible(),"scenes":[],"expert_reviews":[]}
    dossier.write_text(json.dumps(data))
    assert run_game_cli(["jeeves","direction-audit","--project",str(root),
                         "--source","design/story_direction_packet.json"])["ok"]
    data["scenes"]=[scene_source(data["bible"])]
    data["scenes"][0]["prior_digest"]="f"*64
    dossier.write_text(json.dumps(data))
    denied=run_game_cli(["jeeves","direction-audit","--project",str(root),
                         "--source","design/story_direction_packet.json"])
    assert not denied["ok"]
    assert not run_game_cli(["jeeves","direction-audit","--project",str(root),
                             "--source","../../etc/shadow"])["ok"]
