"""Book/film-level source direction gate tests; independent quality never faked."""
from __future__ import annotations

from copy import deepcopy
import json

import pytest

from skeleton.ai.game_builder.story_canon_fabric import BIBLE, SCENE, sign
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


def project_scenes(project: str, n: int):
    bible = canonical_bible()
    # Canonical story identities use underscores, while workspace folder names may use hyphens.
    bible["project"] = project.replace("-", "_")
    bible = sign(bible, BIBLE)
    output = []
    for i in range(1, n+1):
        output.append(scene_source(bible, i, output[-1] if output else None))
    return bible, output


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
    bible,history=project_scenes(root.name,3)
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
    bible,_=project_scenes(root.name,0)
    data={"schema":"skeleton.jeeves.direction_dossier.v1",
          "bible":bible,"scenes":[],"expert_reviews":[]}
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



def test_direction_optin_model_brief_uses_metrics_and_no_copyrighted_scene_text(tmp_path, monkeypatch):
    from skeleton.developer import jeeves_game_authoring as authoring
    init=run_game_cli(["init","creative-studio","--dir",str(tmp_path)])
    assert init["ok"]
    root=tmp_path/"creative-studio"
    bible,history=project_scenes(root.name,2)
    original_line="The route remains ours to map."
    payload={
        "schema":"skeleton.jeeves.direction_dossier.v1",
        "bible":bible,"scenes":history,"expert_reviews":[],
    }
    packet=root/"design"/"direction.json"
    packet.write_text(json.dumps(payload),encoding="utf-8")
    observed=[]
    async def mock_inference(prompt):
        observed.append(json.loads(prompt))
        return json.dumps({
            "kind":"scene","slug":"original-mystery","title":"Original mystery",
            "summary":"Original agent pursues a meaningful difficult decision",
            "body":"The heroine makes a costly decision that changes the world and resolves a prior setup",
            "rationale":"Causal payoff, clear agency, and character change",
        }),{"provider":"fixture","model":"mock","request_id":"test"}
    monkeypatch.setattr(authoring,"_infer",mock_inference)
    generated=run_game_cli([
        "jeeves","propose","--project",str(root),"--kind","scene",
        "--brief","Original transformative scene",
        "--direction-source","design/direction.json",
    ])
    assert generated["ok"],generated
    prompt=observed[0]["authored_story_direction"]
    assert prompt["canonical_scene_count"]==2
    assert original_line not in json.dumps(observed[0])
    assert prompt["quality_floor"]==90
    digest=generated["proposal_sha256"]
    assert run_game_cli(["jeeves","review","--project",str(root),
                         "--digest",digest])["ok"]
    payload["expert_reviews"]=claimed_panel()
    packet.write_text(json.dumps(payload),encoding="utf-8")
    stale=run_game_cli(["jeeves","review","--project",str(root),"--digest",digest])
    assert not stale["ok"] and "direction dossier changed" in stale["error"]


def test_existing_v2_model_proposal_still_reviews_without_direction_packet(tmp_path, monkeypatch):
    from skeleton.developer import jeeves_game_authoring as authoring
    init=run_game_cli(["init","continuity-compat","--dir",str(tmp_path)])
    assert init["ok"]
    root=tmp_path/"continuity-compat"
    async def mock_inference(prompt):
        return json.dumps({
            "kind":"quest","slug":"original-v2","title":"New original quest",
            "summary":"The player changes a settlement through a difficult choice",
            "body":"Original narrative brief with defensible cause and consequences",
            "rationale":"A locally approved proposal only",
        }),{"provider":"fixture","model":"mock","request_id":"test"}
    monkeypatch.setattr(authoring,"_infer",mock_inference)
    result=run_game_cli(["jeeves","propose","--project",str(root),
                         "--kind","quest","--brief","Original quest"])
    assert result["ok"],result
    stored=json.loads((root/".jeeves"/"proposals"/(result["proposal_sha256"]+".json")).read_text())
    assert stored["schema"]=="skeleton.jeeves.game_proposal.v2"
    assert run_game_cli(["jeeves","review","--project",str(root),
                         "--digest",result["proposal_sha256"]])["ok"]



def test_production_cycle_checks_real_signed_story_and_never_invents_quality(tmp_path):
    init=run_game_cli(["init","complete-story","--dir",str(tmp_path)])
    assert init["ok"]
    root=tmp_path/"complete-story"
    policy=run_game_cli(["jeeves","production-init","--project",str(root),
                         "--target","nes","--genre","Platformer",
                         "--period","1985-1989"])
    assert policy["ok"],policy
    absent=run_game_cli(["jeeves","production-cycle","--project",str(root),
                         "--gate","story_continuity"])
    assert absent["ok"]
    assert absent["observations"][0]["outcome"]=="failed"
    bible,history=project_scenes(root.name,1)
    packet=root/"design"/"story_direction_packet.json"
    packet.write_text(json.dumps({
        "schema":"skeleton.jeeves.direction_dossier.v1",
        "bible":bible,"scenes":history,"expert_reviews":claimed_panel(),
    }),encoding="utf-8")
    reviewed=run_game_cli(["jeeves","production-cycle","--project",str(root),
                           "--gate","story_continuity","--passes","3"])
    assert reviewed["ok"],reviewed
    assert all(o["outcome"]=="blocked" for o in reviewed["observations"])
    assert not reviewed["project_complete"]
    status=run_game_cli(["jeeves","production-status","--project",str(root)])
    quality=[x for x in status["gates"] if x["gate"]=="story_continuity"][0]
    assert quality["outcome"]=="blocked"
    assert "independent" in quality["last_reason"]
    assert status["quality_floor"]==90
    assert not status["production_qualified"]



def market_work(i:int, *, year:int=2018, count:int=21) -> dict:
    return {
        "id": f"original-fixture-{i}",
        "release_year":year,
        "commercial_quantity":(9-i)*100000,
        "professional_score":97-i,
        "professional_reviews":count,
        "commercial_source":{
            "url":f"https://studio.example.org/report/{i}",
            "issuer":"Fixture audited publisher",
            "kind":"publisher_or_studio_disclosure",
            "published":"2026-10-01",
        },
        "review_source":{
            "url":f"https://critics.example.com/film/{i}",
            "issuer":"Fixture independent review archive",
            "kind":"independent_critic_aggregate",
            "published":"2026-10-02",
        },
    }


def market_packet(*, medium="novel", unit="audited_print_copies",
                  count=21) -> dict:
    return {
        "schema":"skeleton.jeeves.story_media_benchmark.v1",
        "cohorts":[{
            "medium":medium,
            "genre":"Epic drama",
            "period":"2015-2019",
            "territory":"US",
            "commercial_unit":unit,
            "works":[market_work(i,count=count) for i in range(1,9)],
        }],
    }


def test_cross_media_story_references_use_only_matching_units_and_critic_cohorts(tmp_path):
    from skeleton.ai.game_builder.story_reference_benchmark import audit_story_references
    good=audit_story_references(market_packet())
    assert good["ok"]
    assert good["cohorts"][0]["top_tier_inspiration_available"]
    assert good["cohorts"][0]["qualified_reference_count"]==2
    assert not good["external_sources_independently_fetched"]
    assert not good["professional_story_quality_proven"]
    film=audit_story_references(market_packet(medium="film",unit="ticket_admissions"))
    assert film["cohorts"][0]["qualified_reference_count"]==2
    assert film["cohorts"][0]["minimum_professional_reviews"]==15
    wrong=market_packet(medium="film",unit="audited_print_copies")
    with pytest.raises(ValueError,match="uncomparable commercial unit"):
        audit_story_references(wrong)
    too_few=market_packet(medium="film",unit="ticket_admissions",count=3)
    with pytest.raises(ValueError,match="invalid comparable"):
        audit_story_references(too_few)


def test_literary_film_market_source_is_operator_data_not_external_proof(tmp_path):
    root=tmp_path/"market-analysis"
    init=run_game_cli(["init","market-analysis","--dir",str(tmp_path)])
    assert init["ok"],init
    path=root/"design"/"story_reference_cohorts.json"
    path.write_text(json.dumps(market_packet()))
    good=run_game_cli(["jeeves","direction-benchmark","--project",str(root),
                       "--source","design/story_reference_cohorts.json"])
    assert good["ok"],good
    assert good["declared_cohorts"]==1
    assert good["qualified_cohorts"]==1
    assert not good["independent_commercial_data_verified"]
    broken=market_packet()
    broken["cohorts"][0]["works"][0]["professional_score"]=101
    path.write_text(json.dumps(broken))
    wrong=run_game_cli(["jeeves","direction-benchmark","--project",str(root),
                        "--source","design/story_reference_cohorts.json"])
    assert wrong["ok"] is False
    bad_options=run_game_cli(["jeeves","direction-benchmark","--project",str(root),
                              "--source","design/story_reference_cohorts.json",
                              "--passes","3"])
    assert not bad_options["ok"]


def test_critic_and_commercial_sources_cannot_be_self_issued(tmp_path):
    from skeleton.ai.game_builder.story_reference_benchmark import audit_story_references
    data=market_packet()
    row=data["cohorts"][0]["works"][0]
    row["review_source"]["issuer"]=row["commercial_source"]["issuer"]
    with pytest.raises(ValueError,match="independent"):
        audit_story_references(data)
