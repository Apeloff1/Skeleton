"""Read-only Jeeves story-direction transport over signed canonical chapter/canon.

No new source authority: signed original GameBuilder bible and source history
are always revalidated by the existing StoryCanon verifier. The developer
CLI never auto-approves revisions or transfers prose to model providers.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any

SCHEMA = "skeleton.jeeves.direction_dossier.v1"


def direction(root: Path, *, action: str, source: str,
              passes: int = 1) -> dict[str,Any]:
    from skeleton.developer.jeeves_game_quality import _read
    from skeleton.ai.game_builder.story_direction_quality import (
        evaluate_direction,revision_plan,DirectionError
    )
    data, sha = _read(root,source,16*1024*1024)
    permitted={"schema","bible","scenes","expert_reviews"}
    optional={"dramatic_threads","production_contract","shot_boards","gameplay_source",
              "payoff_alternatives_required"}
    if not isinstance(data, dict) or data.get("schema")!=SCHEMA or not permitted.issubset(data) or not set(data).issubset(permitted|optional):
        raise DirectionError("signed story-direction dossier requires bible, scenes and independent review claims")
    from skeleton.developer.game_cli import _load
    project = _load(root)["name"]
    # GameForge permits hyphenated workspace names, while canonical StoryCanon
    # signs normalized underscore identifiers. Keep an exact, one-way mapping;
    # no prefix, case-fold, or fuzzy cross-project comparisons.
    canonical_project = project.replace("-", "_")
    if not isinstance(data["bible"], dict) or data["bible"].get("project") != canonical_project:
        raise DirectionError("story direction bible belongs to a different active game project")
    report = evaluate_direction(
        data["bible"],data["scenes"],reviewers=data["expert_reviews"],
        passes=passes, dramatic_threads=data.get("dramatic_threads"),
    )
    has_contract = "production_contract" in data
    has_boards = "shot_boards" in data
    if has_contract != has_boards:
        raise DirectionError(
            "film direction requires production_contract and shot_boards together"
        )
    shot_result = None
    if has_contract:
        from skeleton.ai.game_builder.story_direction_shot_pipeline import (
            audit_cinematic_direction,
        )
        shot_result = audit_cinematic_direction(
            data["bible"], data["production_contract"], data["scenes"],
            data["shot_boards"], passes=passes,
        )
    report["cinematic_direction"] = (
        {
            "pre_render_source_verified": True,
            "source_identity_sha256": shot_result["source_identity_sha256"],
            "scenes": shot_result["original_canon_scenes"],
            "shots": shot_result["total_shots"],
            "timeline_ms": shot_result["total_timeline_ms"],
            "source_dialogue_lines_covered": shot_result["source_spoken_lines_covered"],
            "approximate_authored_dialogue_words": shot_result["approximate_authored_dialogue_words"],
            "dense_dialogue_shots": shot_result["dense_dialogue_shots"],
            "rapid_shots_under_750ms": shot_result["rapid_shots_under_750ms"],
            "actual_spoken_pacing_verified": False,
            "all_camera_and_actor_source_checks_passed": True,
            "rendered_film_quality_verified": False,
            "original_voice_performance_verified": False,
        }
        if shot_result is not None else None
    )
    gameplay_result = None
    if "gameplay_source" in data:
        from skeleton.ai.game_builder.story_canon_fabric import verify_story_history
        gameplay_result = gameplay(root, source=data["gameplay_source"], passes=passes)
        matching_history = verify_story_history(data["bible"], data["scenes"])
        if gameplay_result["canonical_story_digest"] != matching_history["digest"]:
            raise DirectionError("playable quest evidence belongs to a different signed narrative history")
    report["playable_story"] = (
        {
            "original_director_world_sha256": gameplay_result["director_world_digest"],
            "replay_evidence_sha256": gameplay_result["replay_evidence_sha256"],
            "replayed_quest_actions": gameplay_result["real_actions_executed"],
            "verified_recording_segments": sum(
                len(records) for records in gameplay_result["replay_segment_receipts"].values()
            ),
            "recorded_playthrough_checkpoint_heads": {
                name: records[-1]["receipt_sha256"]
                for name, records in sorted(gameplay_result["replay_segment_receipts"].items())
            },
            "bound_story_scenes": gameplay_result["source_scenes_bound"],
            "total_original_scenes": gameplay_result["source_scenes_reparsed"],
            "distinct_executed_consequences": gameplay_result["distinct_replayed_consequence_pairs"],
            "unbound_story_scene_sequences": gameplay_result["unbound_source_scene_sequences"],
            "unexecuted_quest_stage_count": len(gameplay_result["unexecuted_quest_stages"]),
            "full_game_playthrough_verified": False,
        }
        if gameplay_result is not None else None
    )
    report["gameplay_dependency"] = (
        {"path": data["gameplay_source"], "sha256": gameplay_result["dossier_sha256"]}
        if gameplay_result is not None else None
    )
    wants_payoff_alternatives = data.get("payoff_alternatives_required", False)
    if type(wants_payoff_alternatives) is not bool:
        raise DirectionError("payoff alternatives requirement must be an explicit boolean")
    if "payoff_alternatives_required" in data and (
        report.get("dramaturgy") is None or gameplay_result is None
    ):
        raise DirectionError("payoff branch scrutiny requires both signed dramatic threads and real gameplay replays")
    payoff_result = None
    if report.get("dramaturgy") is not None and gameplay_result is not None:
        from skeleton.ai.game_builder.story_playable_payoffs import audit_playable_payoffs
        payoff_result = audit_playable_payoffs(
            report["dramaturgy"], gameplay_result,
            demand_alternative_outcomes=wants_payoff_alternatives,
        )
    report["playable_payoffs"] = (
        {
            "source_replay_join_sha256": payoff_result["source_replay_join_sha256"],
            "declared_dramatic_threads": payoff_result["declared_dramatic_threads"],
            "dramatic_threads_with_played_payoff": payoff_result["dramatic_threads_with_played_payoff"],
            "unresolved_or_unplayed_threads": payoff_result["unresolved_or_unplayed_threads"],
            "all_declared_story_payoffs_executed": payoff_result["all_declared_story_payoffs_executed"],
            "requires_alternative_outcomes": payoff_result["requires_alternative_outcomes"],
            "professional_emotional_impact_verified": False,
            "full_game_runtime_verified": False,
        }
        if payoff_result is not None else None
    )
    result=report if action=="direction-audit" else revision_plan(report)
    if action=="direction-revision":
        result["playable_payoffs"] = report["playable_payoffs"]
        if payoff_result is not None:
            for missing in payoff_result["unresolved_or_unplayed_threads"]:
                result["work_items"].append({
                    "priority": "P0",
                    "evidence_kind": "unplayed_story_payoff",
                    "thread_id": missing["thread_id"],
                    "missing_evidence": missing["issue"],
                    "rewrite_goal": "Connect this signed dramatic setup/payoff to an actually replayed, distinct game consequence without changing the original canon",
                    "canonical_story_and_gameplay_recheck_required": True,
                    "automatic_source_overwrite": False,
                })
        elif report.get("dramaturgy") is not None and gameplay_result is None:
            result["work_items"].append({
                "priority": "P0",
                "evidence_kind": "missing_playable_story_replays",
                "rewrite_goal": "Supply an actual signed-story-matched, original Director replay dossier; do not infer player agency from narrative text",
                "automatic_source_overwrite": False,
            })
        result["playable_story"]=report["playable_story"]
        if gameplay_result is not None:
            for sequence in gameplay_result["unbound_source_scene_sequences"][:256]:
                result["work_items"].append({
                    "priority":"P0","evidence_kind":"unbound_story_gameplay_scene",
                    "scene_sequence":sequence,
                    "rewrite_goal":"Integrate signed scene into actual executable player choices and replay both story outcomes",
                    "must_reverify_canonical_story_history":True,
                    "automatic_source_overwrite":False,
                })
            if gameplay_result["unexecuted_quest_stages"]:
                result["work_items"].append({
                    "priority":"P0","evidence_kind":"unexecuted_gameplay_quest_stages",
                    "stage_count":len(gameplay_result["unexecuted_quest_stages"]),
                    "rewrite_goal":"Build or replay actual complete quest routes for every authored main story stage",
                    "must_reverify_canonical_story_history":True,
                    "automatic_source_overwrite":False,
                })
    if action == "direction-revision":
        result["cinematic_direction"] = report["cinematic_direction"]
        if shot_result is not None:
            for scene in shot_result["per_scene"]:
                for observation in scene["recommended_editor_review"]:
                    result["work_items"].append({
                        "priority": "P1",
                        "evidence_kind": "cinematic_editorial_review",
                        "scene_sequence": scene["scene_sequence"],
                        "source_receipt_sha256": scene["pre_render_receipt_digest"],
                        "rewrite_goal": observation,
                        "must_reverify_canonical_story_history": True,
                        "must_reverify_human_editor_and_film_direction": True,
                        "automatic_source_overwrite": False,
                    })
    result["dossier_path"]=source
    result["dossier_sha256"]=sha
    result["canonical_story_source_approved_by_this_command"]=False
    result["operator_review_scores_external_verified"]=False
    result["next_canonical_owner"]="skeleton.ai.game_builder.story_workspace"
    return result



def benchmark(root: Path, *, source: str) -> dict[str,Any]:
    from skeleton.developer.jeeves_game_quality import _read
    from skeleton.ai.game_builder.story_reference_benchmark import audit_story_references
    packet,digest=_read(root,source,2*1024*1024)
    audit=audit_story_references(packet)
    audit["source"]=source
    audit["source_sha256"]=digest
    audit["independent_commercial_data_verified"]=False
    return audit



def cinematic(root: Path, *, source: str, passes: int = 1) -> dict[str, Any]:
    """Review shotboards using the canonical production/cinematography contracts."""
    from skeleton.developer.jeeves_game_quality import _read
    from skeleton.developer.game_cli import _load
    from skeleton.ai.game_builder.story_direction_quality import DirectionError
    from skeleton.ai.game_builder.story_direction_shot_pipeline import audit_cinematic_direction

    packet, digest = _read(root, source, 16 * 1024 * 1024)
    expected = {"schema", "bible", "scenes", "expert_reviews",
                "production_contract", "shot_boards"}
    optional = {"dramatic_threads"}
    if (not isinstance(packet, dict) or
            not expected.issubset(packet) or not set(packet).issubset(expected | optional) or
            packet.get("schema") != SCHEMA):
        raise DirectionError("cinematic review needs signed story, production contract and shot boards")
    project = _load(root)["name"].replace("-", "_")
    bible = packet["bible"]
    if not isinstance(bible, dict) or bible.get("project") != project:
        raise DirectionError("cinematic direction belongs to a different story project")
    result = audit_cinematic_direction(
        bible, packet["production_contract"], packet["scenes"],
        packet["shot_boards"], passes=passes,
    )
    result["dossier_path"] = source
    result["dossier_sha256"] = digest
    result["source_review_only"] = True
    result["rendered_film_or_original_game_certified"] = False
    return result



def gameplay(root: Path, *, source: str, passes: int = 1) -> dict[str, Any]:
    """Source- and replay-bound original story-gameplay evidence; read only."""
    from skeleton.developer.jeeves_game_quality import _read
    from skeleton.developer.game_cli import _load
    from skeleton.ai.game_builder.quest_scene_forge import compile_director_blueprint
    from skeleton.ai.game_builder.story_gameplay_bridge import (
        review_story_gameplay, StoryGameBridgeError,
    )
    if type(passes) is not int or not 1 <= passes <= 8:
        raise StoryGameBridgeError("1..8 bounded replay scrutiny passes")
    document, source_sha = _read(root, source, 16 * 1024 * 1024)
    fields = {
        "schema", "bible", "scenes", "director_world", "author_review_acknowledged",
        "replays", "bindings", "require_distinct_choices",
    }
    if (not isinstance(document, dict) or set(document) != fields
        or document.get("schema") != "skeleton.jeeves.story_gameplay_dossier.v1"):
        raise StoryGameBridgeError("unrecognized signed story-to-gameplay dossier")
    if document["author_review_acknowledged"] is not True:
        raise StoryGameBridgeError("original Director blueprint needs explicit local author review acknowledgement")
    project = _load(root)["name"].replace("-", "_")
    if not isinstance(document["bible"], dict) or document["bible"].get("project") != project:
        raise StoryGameBridgeError("story game replay belongs to another game project")
    world = compile_director_blueprint(
        document["director_world"], human_reviewed=True,
    )
    receipts = []
    for iteration in range(passes):
        checked = review_story_gameplay(
            document["bible"], document["scenes"], world,
            document["replays"], document["bindings"],
            require_distinct_choices=document["require_distinct_choices"],
        )
        if receipts and receipts[0]["evidence_sha256"] != checked["replay_evidence_sha256"]:
            raise StoryGameBridgeError("replay results changed during scrutiny")
        receipts.append({"pass": iteration + 1,
                         "evidence_sha256": checked["replay_evidence_sha256"],
                         "canonical_quest_actions_reexecuted": True})
    # An externally edited dossier must never certify a replay assembled
    # from a stale in-memory snapshot while a long scrutiny run executes.
    _, final_sha = _read(root, source, 16 * 1024 * 1024)
    if final_sha != source_sha:
        raise StoryGameBridgeError("story gameplay source changed during replay scrutiny")
    checked["scrutiny_passes"] = receipts
    checked["dossier_sha256"] = source_sha
    checked["dossier_path"] = source
    checked["creator_approval_externally_verified"] = False
    return checked
