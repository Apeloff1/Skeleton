"""Evidence-bound literary and cinematic direction review over canonical story canon.

This is a *review lens*, never another canonical story/cinematic authority,
trained model, screenplay generator, IP validator or commercial success claim.
Long works are reviewed in source-bound finite slices with repeatable passes.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from hashlib import sha256
import json
import math
import re
from typing import Any

from skeleton.ai.game_builder.story_canon_fabric import (
    validate_story_bible, verify_story_history,
)
from skeleton.ai.game_builder.story_chapter_context import validate_chapter_history

SCHEMA = "skeleton.jeeves.story_direction_review.v1"
DIMS = (
    "original_voice", "character_motivation", "character_transformation",
    "cause_and_effect", "thematic_coherence", "world_consistency",
    "dialogue_subtext", "pacing_and_reversal", "emotional_resonance",
    "player_agency", "visual_storytelling", "sound_and_performance",
    "accessibility_and_localization", "ending_payoff",
)
PROFESSIONAL_FLOOR = 90
MIN_REVIEWERS = 2
_TOKEN = re.compile(r"[a-z0-9']+", re.IGNORECASE)
_WORDS = set("a an and are as at be by for from has he her his i in is it its of on or she that the their them they this to was we were will with you your".split())


class DirectionError(ValueError):
    pass


def _hash(value:object)->str:
    return sha256(json.dumps(value,sort_keys=True,ensure_ascii=True,
                             separators=(",",":"),allow_nan=False).encode()).hexdigest()


def _is_text(value:object, name:str, maximum:int=4096)->str:
    if not isinstance(value,str) or not 1<=len(value.strip())<=maximum:
        raise DirectionError("invalid authored "+name)
    return value


def _review_provenance(rows:Any, *, scenes:int) -> dict[str,Any]:
    """Review scores are human claims and explicitly *not* independently verified."""
    if rows is None:
        return {"reviewers":0,"all_dimensions_covered":False,
                "claimed_professional_threshold_met":False,
                "independent_review_verified":False,"scores_by_dimension":None}
    if not isinstance(rows,list) or len(rows)>64:
        raise DirectionError("review panel must be a bounded list")
    names=set()
    dimensions=defaultdict(list)
    for row in rows:
        if not isinstance(row,dict) or set(row)!={"reviewer_id","role","source","scores"}:
            raise DirectionError("review claim must give reviewer, professional role, evidence source and scores")
        identity=_is_text(row["reviewer_id"],"reviewer identity",100)
        if identity.casefold() in names:
            raise DirectionError("repeat reviewer cannot inflate literary or film review count")
        names.add(identity.casefold())
        if row["role"] not in ("novel_editor","screenwriter","film_director",
                               "narrative_designer","gameplay_director",
                               "sound_director","accessibility_reviewer"):
            raise DirectionError("unknown expert panel discipline")
        _is_text(row["source"],"review receipt",300)
        scores=row["scores"]
        if not isinstance(scores,dict) or set(scores)!=set(DIMS):
            raise DirectionError("review must cover all narrative and direction quality dimensions")
        for name,score in scores.items():
            if type(score) is not int or not 0<=score<=100:
                raise DirectionError("review score not an integer 0..100")
            dimensions[name].append(score)
    scored={d:{"claimed_min":min(vals),"claimed_mean":round(sum(vals)/len(vals),2)}
            for d,vals in dimensions.items()}
    enough=len(rows)>=MIN_REVIEWERS and {
        row["role"] for row in rows
    } & {"novel_editor","screenwriter"} and {
        row["role"] for row in rows
    } & {"film_director","narrative_designer","gameplay_director"}
    return {
        "reviewers":len(rows),
        "all_dimensions_covered":bool(rows),
        "claimed_professional_threshold_met":bool(enough) and all(
            all(s>=PROFESSIONAL_FLOOR for s in vals) for vals in dimensions.values()
        ),
        "independent_review_verified":False,
        "scores_by_dimension":scored if rows else None,
        "raw_scores_are_operator_supplied":True,
    }


def evaluate_direction(bible:dict[str,Any], scenes:list[dict[str,Any]], *,
                       reviewers:Any=None, passes:int=1,
                       enforce_chapter_standard:bool=True) -> dict[str,Any]:
    if type(passes) is not int or not 1<=passes<=8:
        raise DirectionError("use 1..8 scrutiny passes per resumable invocation")
    if not isinstance(scenes,list) or len(scenes)>9999:
        raise DirectionError("scene history must use the 9999-scene canonical production limit")
    validate_story_bible(bible)
    # Entire current source is reparsed using the *existing* signed canon
    # verifier; this lens cannot bless an unsigned or discontinuous scene.
    receipts=[]
    for iteration in range(passes):
        indexed=verify_story_history(bible, scenes)
        if enforce_chapter_standard and scenes and all("chapter" in s for s in scenes):
            validate_chapter_history(scenes)
        if any(("chapter" in s) != ("chapter" in scenes[0]) for s in scenes):
            raise DirectionError("chapter-scoped and legacy scenes cannot mix in one review")
        receipts.append({
            "pass":iteration+1,"history_digest":indexed["digest"],
            "scene_count":indexed["scene_count"],
            "canonical_source_reviewed":True,
            "independent_review":False,
        })
    dialogue=[]
    tokens_by_speaker=defaultdict(list)
    spoken_by_speaker=defaultdict(list)
    warnings=[]
    events_count=references=actual_transitions=interactions=0
    changes_by_character=Counter()
    beats=0
    per_scene=[]
    hooks=[]
    for item in scenes:
        values=item["dialogue"]
        lines=[]
        for row in values:
            line=row["text"]
            speaker=row["speaker"]
            normalized=" ".join(_TOKEN.findall(line.casefold()))
            spoken_by_speaker[speaker].append(normalized)
            tokens_by_speaker[speaker].extend(
                token for token in _TOKEN.findall(line.casefold())
                if token not in _WORDS
            )
            lines.append({"line_id":row["id"],"speaker":speaker})
        scene_references=sum(
            len(r.get("references",[]))
            for name in ("events","beats","dialogue","interactions")
            for r in item[name]
        )
        transitions=sum(len(e["changes"]) for e in item["events"])
        for e in item["events"]:
            for change in e["changes"]:
                changes_by_character[change["character"]]+=1
        interactions+=len(item["interactions"])
        events_count+=len(item["events"])
        beats+=len(item["beats"])
        references+=scene_references
        actual_transitions+=transitions
        per_scene.append({
            "scene_sequence":item["sequence"],"source_sha256":item["digest"],
            "dialogue_lines":len(values),"causal_references":scene_references,
            "character_state_transitions":transitions,
            "authored_beats":len(item["beats"]),
            "cinematic_shots_independently_verified":False,
            "playable_story_branch_verified":False,
        })
        if "storytelling" in item:
            hooks.append((item["sequence"],item["storytelling"]["hook"]))
    total_lines=sum(len(x) for x in spoken_by_speaker.values())
    distinct_line_count=len({l for ls in spoken_by_speaker.values() for l in ls})
    duplicate_lines=total_lines-distinct_line_count
    speaker_metrics=[]
    for speaker in sorted(spoken_by_speaker):
        lines=spoken_by_speaker[speaker]
        tokens=tokens_by_speaker[speaker]
        speaker_metrics.append({
            "speaker":speaker,"line_count":len(lines),
            "unique_line_fraction":round(len(set(lines))/len(lines),4),
            "lexical_diversity":round(len(set(tokens))/len(tokens),4) if tokens else None,
            "voice_distinctiveness_professionally_verified":False,
        })
        if len(lines)>=3 and len(set(lines))<len(lines):
            warnings.append({
                "priority":"P1","kind":"dialogue_repetition","speaker":speaker,
                "evidence_lines":len(lines)-len(set(lines)),
                "why":"Recurring exact dialogue requires deliberate motif or variation review",
            })
    if scenes and not actual_transitions:
        warnings.append({
            "priority":"P0","kind":"unproven_character_transformation",
            "evidence_scenes":[s["sequence"] for s in scenes[:16]],
            "why":"No authored character state changes yet; a completed dramatic arc cannot be inferred",
        })
    if scenes and not references:
        warnings.append({
            "priority":"P0","kind":"no_crossbeat_causality","why":"No causal reference chains recorded",
        })
    if scenes and all(not row["dialogue"] for row in scenes):
        warnings.append({
            "priority":"P1","kind":"no_dialogue","why":"Silent narrative may be intentional, but prose/voice quality cannot be judged",
        })
    if scenes and all(len(s["cast"])<=1 for s in scenes):
        warnings.append({
            "priority":"P1","kind":"no_interpersonal_scene","why":"No source evidence of interpersonal conflict or relationship variation",
        })
    if not scenes:
        warnings.append({"priority":"P0","kind":"no_signed_scenes",
                         "why":"An original story bible is not yet a produced narrative"})
    review=_review_provenance(reviewers, scenes=len(scenes))
    checked_scenes=len(scenes)
    coverage={
        "canonical_scene_count":checked_scenes,
        "planned_story_chapters":bible["story"].get("planned_chapters"),
        "planned_story_acts":bible["story"]["planned_acts"],
        "full_studio_target_scenes":9999,
        "canonical_history_fully_reparsed":True,
        "dramatic_beats":beats,
        "dialogue_lines":total_lines,
        "distinct_dialogue_lines":distinct_line_count,
        "exact_dialogue_repeat_fraction":round(duplicate_lines/total_lines,4) if total_lines else None,
        "causal_source_references":references,
        "character_state_transitions":actual_transitions,
        "characters_with_explicit_state_change":sorted(changes_by_character),
        "interactive_events_or_interactions":events_count+interactions,
        "interactive_player_choices_executed":0,
        "cinematic_frames_rendered":0,
        "professional_reader_audience_responses":0,
    }
    return {
        "ok":True,"schema":SCHEMA,"action":"direction-audit",
        "source_identity":_hash({"bible":bible["digest"],
                                  "scene_digests":[s["digest"] for s in scenes]}),
        "source_verified":True,"canonical_receipts":receipts,
        "observed_story_metrics":coverage,
        "speakers":speaker_metrics,"scene_coverage":per_scene,
        "revision_work":warnings,
        "expert_review_claims":review,
        "quality_bars":{
            "every_qualitative_dimension_at_least":PROFESSIONAL_FLOOR,
            "reference_level":"professional novel and film/story direction",
            "quality_threshold_relaxation_allowed":False,
            "minimum_professional_reviewers":MIN_REVIEWERS,
        },
        "reviewer_evidence_independently_verified":False,
        "professional_story_quality_proven":False,
        "hollywood_level_film_quality_proven":False,
        "book_publication_quality_proven":False,
        "complete_game_story_certified":False,
        "source_scrutiny_passes":passes,
        "independent_test_or_screening_performed":False,
    }


def revision_plan(review:dict[str,Any]) -> dict[str,Any]:
    if not isinstance(review,dict) or review.get("schema")!=SCHEMA:
        raise DirectionError("revision requires validated story-direction review")
    next_actions=[]
    for item in review["revision_work"]:
        kind=item["kind"]
        method={
            "dialogue_repetition":"Rewrite or justify repeating character lines with distinct subtext while preserving signed canon",
            "unproven_character_transformation":"Author motivated, causally justified state changes; re-sign sources via creator approval",
            "no_crossbeat_causality":"Create source-linked causal events and payoffs, then replay full canon history",
            "no_dialogue":"Stage a performed/interactive scene and seek real voice and editorial review",
            "no_interpersonal_scene":"Author conflicting character objectives and changing relationships",
            "no_signed_scenes":"Begin with an approved original story bible and first confirmed scene",
        }[kind]
        next_actions.append({
            "priority":item["priority"],"evidence_kind":kind,"rewrite_goal":method,
            "must_reverify_canonical_story_history":True,
            "must_reverify_human_editor_and_film_direction":True,
            "automatic_source_overwrite":False,
        })
    next_actions+=[
        {"priority":"P0","evidence_kind":"professional_readthrough",
         "rewrite_goal":"Get independent novelist/screenwriter/director critique on prose, subtext, emotional stakes and thematic integrity",
         "automatic_source_overwrite":False},
        {"priority":"P0","evidence_kind":"film_screening",
         "rewrite_goal":"Capture rendered shot/audio/acting reviews and objective timeline/lip-sync/frame evidence",
         "automatic_source_overwrite":False},
        {"priority":"P0","evidence_kind":"playtested_agency",
         "rewrite_goal":"Run branch-aware gameplay scenes and verify distinct player choice consequences",
         "automatic_source_overwrite":False},
    ]
    return {"ok":True,"schema":SCHEMA,"action":"direction-revision",
            "source_identity":review["source_identity"],
            "work_items":next_actions,
            "numeric_quality_floor_lowered":False,
            "model_retrained":False,"source_files_modified":False}
