"""Paginated, bounded catalog-wide source-bound authored choice assurance.

This is a read-only authoring diagnostic, not native gameplay qualification.
"""
from __future__ import annotations

from typing import Any

from .studio_ecosystem_catalog import (
    StudioEcosystemError, list_blueprints, read_blueprint,
)
from .studio_ecosystem_quest import StudioQuestError
from .studio_ecosystem_walk_replay import _sha, start_walk
from .studio_ecosystem_walk_coverage import audit_walk_choice_coverage

MAX_CATALOG_AUDIT_PROJECTS = 4
MAX_CATALOG_AUDIT_REPLAY_EVENTS = 65_536


def audit_catalog_walk_choices(
    *, authorized: bool, genre: str | None = None, biome: str | None = None,
    offset: int = 0, limit: int = 2,
    expected_catalog_digest: str | None = None,
) -> dict[str, object]:
    """Audit a deterministic catalog page, with explicit incomplete results.

    The registered index is the sole project source. A changing index fails
    closed; a corrupt individual project is reported as invalid, not passed.
    The caller must page with the same catalog digest to aggregate results.
    """
    if not authorized:
        raise PermissionError("catalog choice audit requires operator authorization")
    if (type(offset) is not int or offset < 0
            or type(limit) is not int or not 1 <= limit <= MAX_CATALOG_AUDIT_PROJECTS
            or any(value is not None and
                   (not isinstance(value, str) or not value or len(value) > 96)
                   for value in (genre, biome))):
        raise StudioQuestError("invalid catalog choice audit pagination or filter")
    if expected_catalog_digest is not None and (
        type(expected_catalog_digest) is not str
        or len(expected_catalog_digest) != 64
        or any(c not in "0123456789abcdef" for c in expected_catalog_digest)
    ):
        raise StudioQuestError("invalid expected catalog digest")
    if offset and expected_catalog_digest is None:
        raise StudioQuestError("continuation requires a catalog digest")
    records = list_blueprints(genre=genre, biome=biome)
    if offset > len(records):
        raise StudioQuestError("catalog choice audit offset exceeds filtered index")
    index_digest = _sha(records)
    if expected_catalog_digest is not None and index_digest != expected_catalog_digest:
        raise StudioQuestError("catalog changed between audit pages")
    selected = records[offset:offset + limit]
    projects: list[dict[str, Any]] = []
    replay_work = 0
    for record in selected:
        project_id = record["id"]
        try:
            documents = read_blueprint(project_id)
            session = start_walk(documents, authorized=True)
            result = audit_walk_choice_coverage(
                session, documents, authorized=True,
            )
            replay_work += result["replay_work_events"]
            projects.append({
                "project_id": project_id,
                "status": "covered" if result["complete_reference_path_coverage"]
                          else "partial",
                "source_digest": session.source_digest,
                "coverage_digest": result["coverage_digest"],
                "alternatives_verified": result["alternatives_verified"],
                "alternatives_unverified": result["alternatives_unverified"],
                "stop_reason": result["stop_reason"],
            })
        except (StudioEcosystemError, StudioQuestError, ValueError, OSError):
            projects.append({
                "project_id": project_id,
                "status": "invalid_source",
                "source_digest": None,
                "coverage_digest": None,
                "alternatives_verified": 0,
                "alternatives_unverified": None,
                "stop_reason": "source_or_replay_validation_failed",
            })
    if replay_work > MAX_CATALOG_AUDIT_REPLAY_EVENTS:
        raise StudioQuestError("catalog choice audit replay budget exceeded")
    if _sha(list_blueprints(genre=genre, biome=biome)) != index_digest:
        raise StudioQuestError("catalog changed during choice audit")
    next_offset = offset + len(selected)
    if next_offset >= len(records):
        next_offset = None
    complete_page = all(row["status"] == "covered" for row in projects)
    payload: dict[str, object] = {
        "schema": "skeleton.game_builder.studio_walk_catalog_choice_audit.v1",
        "catalog_digest": index_digest,
        "genre": genre,
        "biome": biome,
        "filtered_project_count": len(records),
        "page_offset": offset,
        "page_limit": limit,
        "projects_examined": len(projects),
        "projects": projects,
        "next_offset": next_offset,
        "continuation": ({
            "schema": "skeleton.game_builder.studio_walk_catalog_cursor.v1",
            "catalog_digest": index_digest,
            "offset": next_offset,
            "limit": limit,
            "genre": genre,
            "biome": biome,
        } if next_offset is not None else None),
        "replay_work_events": replay_work,
        "complete_page_coverage": complete_page,
        "complete_catalog_coverage": bool(records) and offset == 0
                                     and next_offset is None and complete_page,
        "all_branch_combinations_verified": False,
        "external_evidence_verified": False,
        "native_genre_runtime_verified": False,
        "release_certified": False,
    }
    payload["audit_digest"] = _sha(payload)
    return payload
