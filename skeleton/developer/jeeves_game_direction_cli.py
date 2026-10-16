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
    result=report if action=="direction-audit" else revision_plan(report)
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
