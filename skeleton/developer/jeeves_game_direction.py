"""Book- and film-grade Jeeves direction evidence adapter over canonical story owners.

Does NOT replace story_canon_fabric, story_continuity_assurance, or
story_cinematic_review. Only those owners establish continuity and pre-render
cinematic validity. Numeric coverage != artistic excellence or film awards.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
from pathlib import Path
import json
import re
from typing import Any

from skeleton.ai.game_builder.story_canon_fabric import (
    verify_story_history, validate_story_bible,
)
from skeleton.ai.game_builder.story_continuity_assurance import (
    validate_contract, verify_production_history,
)
from skeleton.ai.game_builder.story_cinematic_review import (
    verify_cinematic_shots,
)
from skeleton.developer.jeeves_game_quality import _read

SCHEMA = "skeleton.jeeves.story_direction.v1"
PANEL_SCHEMA = "skeleton.jeeves.creative_review_panel.v1"
DIMENSIONS = (
    "originality", "prose_and_voice", "character_psychology", "character_arcs",
    "dialogue_and_subtext", "causality_and_payoff", "pacing_and_tension",
    "theme_and_symbolism", "world_and_canon", "branching_and_agency",
    "cinematography_and_blocking", "performance_direction",
    "sound_and_music_direction", "emotional_resonance",
)
MIN_PANEL = 3
SCORE_FLOOR = 90


class DirectionError(ValueError):
    pass


def _digest(value: object) -> str:
    return sha256(json.dumps(value,sort_keys=True,separators=(",",":"),
                            ensure_ascii=True,allow_nan=False).encode()).hexdigest()


def _load(root: Path, name: str):
    return _read(root,name,2*1024*1024)


def _manifest(root: Path, source: str):
    manifest,identity=_load(root,source)
    expected={"schema","bible","contract","scenes","shotboards","panel"}
    if set(manifest)!=expected or manifest["schema"]!=SCHEMA:
        raise DirectionError("unsupported direction manifest; explicit bible/contract/scenes/shotboards/panel required")
    if not isinstance(manifest["bible"],str):
        raise DirectionError("authored canon bible path is required")
    if manifest["contract"] is not None and not isinstance(manifest["contract"],str):
        raise DirectionError("continuity contract path invalid")
    if manifest["panel"] is not None and not isinstance(manifest["panel"],str):
        raise DirectionError("review panel path invalid")
    scenes=manifest["scenes"]
    boards=manifest["shotboards"]
    if not isinstance(scenes,list) or len(scenes)>9999 or any(
        not isinstance(x,str) for x in scenes
    ):
        raise DirectionError("scene manifest malformed or exceeds canonical 9999-scene history")
    if not isinstance(boards,list) or len(boards)>9999:
        raise DirectionError("shotboard manifest malformed")
    if len(set(scenes))!=len(scenes):
        raise DirectionError("duplicate source scene in historical sequence")
    return manifest,identity


def _panel(root: Path, name: str) -> dict[str,Any]:
    evidence,digest=_load(root,name)
    if set(evidence)!={"schema","original_project","reviews"} or evidence["schema"]!=PANEL_SCHEMA:
        raise DirectionError("invalid independent artistic review dossier")
    if evidence["original_project"] is not True:
        raise DirectionError("quality reviews only for original projects")
    reviews=evidence["reviews"]
    if not isinstance(reviews,list) or not MIN_PANEL<=len(reviews)<=12:
        raise DirectionError("top-tier artistic review needs >=3 independent panelists")
    reviewers=set()
    scores=[]
    for r in reviews:
        if not isinstance(r,dict) or set(r)!={"reviewer","role","method","scores","critique","evidence_ids"}:
            raise DirectionError("malformed director's review")
        if any(not isinstance(r[x],str) or not 8<=len(r[x])<=2400 for x in ("reviewer","role","method","critique")):
            raise DirectionError("independent reviewer identity, method and substantive critique required")
        if not isinstance(r["evidence_ids"],list) or not r["evidence_ids"] or len(r["evidence_ids"])>256 or any(
            not isinstance(x,str) or not re.fullmatch(r"[a-zA-Z0-9_./:-]{2,128}",x)
            for x in r["evidence_ids"]
        ):
            raise DirectionError("artistic opinions must cite inspectable project evidence IDs")
        norm=r["reviewer"].strip().casefold()
        if norm in reviewers:
            raise DirectionError("reviewers must have independent identities")
        reviewers.add(norm)
        dims=r["scores"]
        if not isinstance(dims,dict) or set(dims)!=set(DIMENSIONS) or any(
            type(value) is not int or not 0<=value<=100 for value in dims.values()
        ):
            raise DirectionError("all 14 creative dimensions need numeric 0..100 scores")
        scores.append(dims)
    dimension_means={
        dim:round(sum(v[dim] for v in scores)/len(scores),2) for dim in DIMENSIONS
    }
    dimension_minima={dim:min(v[dim] for v in scores) for dim in DIMENSIONS}
    qualifying=all(v>=SCORE_FLOOR for v in dimension_minima.values())
    return {
        "source_sha256":digest,"reviewers":len(reviewers),
        "mean_scores":dimension_means,"minimum_scores":dimension_minima,
        "quality_floor":SCORE_FLOOR,"panel_claims_top_tier":qualifying,
        "reviewer_independence_verified_externally":False,
        "ratings_authenticated_externally":False,
        "professional_quality_certified":False,
    }


def audit(root:Path, *, source:str="design/direction_manifest.json") -> dict[str,Any]:
    """Verify all source canon first, then report objective & claimed excellence."""
    manifest,manifest_sha=_manifest(root,source)
    bible,bible_sha=_load(root,manifest["bible"])
    validate_story_bible(bible)
    scenes=[]
    file_hashes=[]
    for path in manifest["scenes"]:
        scene,digest=_load(root,path)
        scenes.append(scene)
        file_hashes.append({"path":path,"sha256":digest})
    index=verify_story_history(bible,scenes)
    # The original GameBuilder lens already computes speaker lexical diversity,
    # repeated dialogue, causal links and character state transitions.
    # Reuse its published metrics rather than inventing an inconsistent score.
    from skeleton.ai.game_builder.story_direction_quality import evaluate_direction
    literary=evaluate_direction(bible, scenes, reviewers=None, passes=1)
    contract=None
    quality_confirmation=None
    contract_sha=None
    if manifest["contract"]:
        contract,contract_sha=_load(root,manifest["contract"])
        validate_contract(contract,bible)
        quality_confirmation=verify_production_history(bible,contract,scenes)
    elif manifest["shotboards"]:
        raise DirectionError("cinematic shotboards require approved voice/face continuity contract")
    boards={}
    for entry in manifest["shotboards"]:
        if not isinstance(entry,dict) or set(entry)!={"sequence","path"} or type(entry["sequence"]) is not int or not isinstance(entry["path"],str):
            raise DirectionError("shotboard reference needs exact scene sequence and path")
        seq=entry["sequence"]
        if seq in boards:
            raise DirectionError("duplicate cinematic shotboard for one scene")
        boards[seq]=entry["path"]
    scene_by_seq={x["sequence"]:x for x in scenes}
    if any(k not in scene_by_seq for k in boards):
        raise DirectionError("orphaned shotboard without approved story scene")
    total_lines=0
    covered_lines=0
    total_shots=0
    milliseconds=0
    shot_kinds=Counter()
    verified_shots=[]
    for seq,path in sorted(boards.items()):
        shot_doc,shot_sha=_load(root,path)
        if set(shot_doc)!={"scene_digest","shots"} or shot_doc["scene_digest"]!=scene_by_seq[seq]["digest"]:
            raise DirectionError("director cut detached from approved scene source")
        result=verify_cinematic_shots(bible,contract,scene_by_seq[seq],shot_doc["shots"])
        verified_shots.append({"sequence":seq,"path":path,"sha256":shot_sha,
                               "receipt_digest":result["digest"],
                               "shot_count":result["shot_count"],
                               "duration_ms":result["duration_ms"]})
        covered_lines+=result["spoken_lines_verified"]
        total_shots+=result["shot_count"]
        milliseconds+=result["duration_ms"]
        shot_kinds.update(s["camera"] for s in shot_doc["shots"])
    all_lines=sum(len(x["dialogue"]) for x in scenes)
    all_beats=sum(len(x["beats"]) for x in scenes)
    all_events=sum(len(x["events"]) for x in scenes)
    all_interactions=sum(len(x["interactions"]) for x in scenes)
    chapters={x.get("chapter") for x in scenes if "chapter" in x}
    acts={x["act"] for x in scenes}
    cast_used={c for x in scenes for c in x["cast"]}
    closeouts=None
    if scenes and all("chapter" in s and "storytelling" in s for s in scenes):
        from skeleton.ai.game_builder.story_chapter_context import validate_chapter_history
        plot=validate_chapter_history(scenes)
        closeouts={
            "introduced_plot_highlights":len(plot["highlights"]),
            "resolved_plot_highlights":len(plot["resolved_highlights"]),
            "unresolved_plot_highlights":sum(not v["closed"] for v in plot["highlights"].values()),
            "closed_chapters":len(plot["closed_chapters"]),
        }
    review=_panel(root,manifest["panel"]) if manifest["panel"] else None
    missing=[
        key for key,value in {
            "approved_design_bible":bible["phase"]=="design" and bible["rights_reviewed"],
            "immutable_voice_face_continuity_contract":contract is not None,
            "at_least_one_canonical_scene":bool(scenes),
            "cinematic_direction_for_every_scene":bool(scenes) and len(boards)==len(scenes),
            "independent_artistic_review_panel":review is not None,
            "all_story_highlights_closed":closeouts is not None and closeouts["unresolved_plot_highlights"]==0,
            "actual_rendered_film_review":False,
            "actor_performance_and_voice_acoustic_review":False,
            "playtester_branch_and_emotional_impact_study":False,
            "independent_market_sales_rating_corroboration":False,
        }.items() if not value
    ]
    return {
        "ok":True,"action":"direction-audit","schema":SCHEMA,
        "source":source,"manifest_sha256":manifest_sha,
        "bible_sha256":bible_sha,"canonical_history_digest":index["digest"],
        "continuity_receipt_sha256":quality_confirmation["digest"] if quality_confirmation else None,
        "continuity_contract_sha256":contract_sha,
        "accepted_canonical_scenes":len(scenes),"acts_represented":len(acts),
        "chapters_represented":len(chapters),
        "characters_in_bible":len(bible["characters"]),
        "characters_used":len(cast_used),
        "authored_beats":all_beats,"dialogue_lines":all_lines,
        "causal_events":all_events,"interactive_actions":all_interactions,
        "verified_cinematic_scenes":len(verified_shots),
        "cinematic_scene_coverage":round(len(verified_shots)/len(scenes),5) if scenes else 0,
        "spoken_dialogue_coverage":round(covered_lines/all_lines,5) if all_lines else 0,
        "shots_reviewed":total_shots,"authored_cinematic_ms":milliseconds,
        "camera_vocabulary_used":sorted(shot_kinds),
        "shotboard_evidence":verified_shots,
        "plot_closure":closeouts,
        "creative_panel":review,
        "creative_scores_operator_reported":review is not None,
        "canonical_source_replay_passed":True,
        "canonical_literary_quality_lens":{
            "source_identity":literary["source_identity"],
            "observed_story_metrics":literary["observed_story_metrics"],
            "speakers":literary["speakers"],
            "revision_work":literary["revision_work"],
            "reviewer_evidence_independently_verified":False,
        },
        "missing_qualification_gates":missing,
        "narrative_world_class_certified":False,
        "hollywood_rendered_direction_certified":False,
        "game_story_ready_for_release":False,
        "model_weights_improved":False,
    }


def workorder(root:Path, *, source:str="design/direction_manifest.json") -> dict[str,Any]:
    review=audit(root,source=source)
    cards=[]
    for key in review["missing_qualification_gates"]:
        cards.append({"priority":"P0" if key in (
            "approved_design_bible","immutable_voice_face_continuity_contract",
            "at_least_one_canonical_scene","cinematic_direction_for_every_scene",
            "all_story_highlights_closed",
        ) else "P1","gate":key,
                      "acceptance":"Provide real canonical scene receipts, independent evidence, or qualified runtime results; never lower quality bar"})
    for finding in review["canonical_literary_quality_lens"]["revision_work"]:
        cards.append({
            "priority":finding["priority"],
            "gate":"literary_"+finding["kind"],
            "acceptance":finding["why"]+"; revise with reviewed canonical approval and recheck the full history",
        })
    if review["creative_panel"] is not None:
        for name,value in review["creative_panel"]["minimum_scores"].items():
            if value<SCORE_FLOOR:
                cards.append({"priority":"P0","gate":"artistic_"+name,
                              "acceptance":f"Current panel minimum {value}; require >= {SCORE_FLOOR} for all reviewers without lowering standard"})
    return {
        "ok":True,"action":"direction-workorder","source_sha256":review["manifest_sha256"],
        "top_quality_bar":"all 14 artistic dimensions >=90 for every independent reviewer",
        "canonical_continuity_required":True,"pre_render_cinematic_proof_required":True,
        "unlimited_project_lifetime":True,"quality_downgrade_allowed":False,
        "work_items":cards,"count":len(cards),
        "director_claims_finished_game":False,
    }
