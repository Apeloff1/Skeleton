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
    if data.get("schema")!=SCHEMA or set(data)!={"schema","bible","scenes","expert_reviews"}:
        raise DirectionError("signed story-direction dossier requires bible, scenes and independent review claims")
    from skeleton.developer.game_cli import _load
    project = _load(root)["name"]
    if not isinstance(data["bible"], dict) or data["bible"].get("project") != project:
        raise DirectionError("story direction bible belongs to a different active game project")
    report = evaluate_direction(
        data["bible"],data["scenes"],reviewers=data["expert_reviews"],
        passes=passes,
    )
    result=report if action=="direction-audit" else revision_plan(report)
    result["dossier_path"]=source
    result["dossier_sha256"]=sha
    result["canonical_story_source_approved_by_this_command"]=False
    result["operator_review_scores_external_verified"]=False
    result["next_canonical_owner"]="skeleton.ai.game_builder.story_workspace"
    return result
