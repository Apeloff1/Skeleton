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
    optional={"dramatic_threads","production_contract","shot_boards"}
    if data.get("schema")!=SCHEMA or not permitted.issubset(data) or not set(data).issubset(permitted|optional):
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
            "all_camera_and_actor_source_checks_passed": True,
            "rendered_film_quality_verified": False,
            "original_voice_performance_verified": False,
        }
        if shot_result is not None else None
    )
    result=report if action=="direction-audit" else revision_plan(report)
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
        if receipts and receipts[0]["replay_evidence_sha256"] != checked["replay_evidence_sha256"]:
            raise StoryGameBridgeError("replay results changed during scrutiny")
        receipts.append({"pass": iteration + 1,
                         "evidence_sha256": checked["replay_evidence_sha256"],
                         "canonical_quest_actions_reexecuted": True})
    checked["scrutiny_passes"] = receipts
    checked["dossier_sha256"] = source_sha
    checked["dossier_path"] = source
    checked["creator_approval_externally_verified"] = False
    return checked
